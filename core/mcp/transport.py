"""Parler a un serveur MCP en streamable-HTTP, sans dependance nouvelle.

ARENA a besoin d'atteindre WanGP (Wan2GP), qui expose ses capacites par un
serveur MCP. Deux chemins existaient : ajouter le SDK `mcp` aux dependances, ou
ecrire le strict necessaire du protocole. Le SDK a ete ecarte — `requirements.txt`
vient de casser la CI sur un conflit de versions, et le proprietaire ne peut rien
tester cette semaine. Ce module n'utilise que `httpx`, deja present.

**Ce qu'il fait** : la poignee de main MCP (`initialize`, `notifications/initialized`),
puis `tools/list` et `tools/call`. Rien d'autre. Ce qui n'est pas la n'existe pas.

**Trois regles :**

1. **Une panne est un etat, jamais une exception qui remonte.** Un serveur
   absent, un JSON illisible, une erreur JSON-RPC : tout devient un `Reponse`
   avec sa raison. Une generation video ne doit pas faire tomber une
   conversation.

2. **Le chemin d'acces est un reglage, pas une supposition.** FastMCP sert
   `/mcp` par defaut, mais ce defaut appartient au SDK de WanGP, pas a ARENA. Il
   se change par configuration, sans toucher au code — si un jour il differe, un
   reglage suffit au lieu d'une correction.

3. **La reponse peut arriver en JSON ou en flux d'evenements.** Les deux sont
   lus. Un serveur qui repond en `text/event-stream` n'est pas une panne.
"""
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("usman.mcp.transport")

#: Version du protocole annoncee a la poignee de main.
VERSION_PROTOCOLE = "2025-06-18"

#: Delai d'attente par defaut. Une generation video ne s'attend pas ici : elle
#: rend un identifiant de tache, et c'est la file de travaux qui patiente.
DELAI_SECONDES = 30.0


@dataclass
class Reponse:
    """Ce qu'un appel MCP a rendu, ou pourquoi il n'a rien rendu."""

    ok: bool
    resultat: Dict[str, Any] = field(default_factory=dict)
    raison: str = ""

    @property
    def contenu_texte(self) -> str:
        """Le texte des blocs `content`, concatene. Vide si le serveur n'en a pas."""
        morceaux = []
        for bloc in self.resultat.get("content") or []:
            if isinstance(bloc, dict) and bloc.get("type") == "text":
                morceaux.append(str(bloc.get("text", "")))
        return "\n".join(morceaux)

    @property
    def erreur_applicative(self) -> Optional[str]:
        """Le message d'une erreur APPLICATIVE (`isError`), ou `None`.

        MCP distingue deux echecs, et `ok` n'en couvre qu'un : `ok=False` dit
        que le transport n'a pas abouti ; `ok=True, isError=True` dit que
        l'outil, lui, a refuse — et pourquoi. Mesure sur le serveur
        OpenTakeoff reel : un outil inconnu et une feuille non chargee rendent
        tous deux `ok=True, isError=True`.

        Ecrit ici parce que **deux** connecteurs posent la question et qu'un
        seul la posait. Mesure du 01/09/2026 : WanGP repondant « VRAM
        insuffisante : modele non charge » faisait rendre `SUCCESS` a ARENA,
        avec « WanGP a repondu » — le message reel jete.
        """
        if not isinstance(self.resultat, dict) or not self.resultat.get("isError"):
            return None
        return self.contenu_texte or "erreur non precisee"

    def donnees(self) -> Any:
        """Le JSON porte par la reponse, quand le serveur en renvoie un.

        MCP rend souvent le resultat structure dans `structuredContent`, et une
        version texte a cote. On prend le structure quand il existe ; sinon on
        tente de lire le texte comme du JSON. Un texte qui n'est pas du JSON est
        rendu tel quel — ce n'est pas une panne, c'est une reponse en prose.
        """
        structure = self.resultat.get("structuredContent")
        if structure is not None:
            return structure
        texte = self.contenu_texte
        if not texte:
            return None
        try:
            return json.loads(texte)
        except (json.JSONDecodeError, TypeError):
            return texte


def _charge(reponse: httpx.Response) -> Optional[Dict[str, Any]]:
    """Lit une reponse JSON ou un flux d'evenements. `None` si rien d'exploitable."""
    type_contenu = (reponse.headers.get("content-type") or "").lower()
    if "text/event-stream" in type_contenu:
        for ligne in reponse.text.splitlines():
            if ligne.startswith("data:"):
                try:
                    return json.loads(ligne[5:].strip())
                except json.JSONDecodeError:
                    continue
        return None
    try:
        return reponse.json()
    except (json.JSONDecodeError, ValueError):
        return None


class ClientMcp:
    """Un client MCP minimal, en streamable-HTTP.

    La session est etablie a la premiere utilisation et reutilisee : refaire la
    poignee de main a chaque appel couterait un aller-retour pour rien.
    """

    def __init__(self, base_url: str, chemin: str = "/mcp",
                 delai: float = DELAI_SECONDES, client: Optional[httpx.Client] = None) -> None:
        self.url = f"{base_url.rstrip('/')}{chemin if chemin.startswith('/') else '/' + chemin}"
        self.delai = delai
        self._client = client
        self._session: Optional[str] = None

    # --- Bas niveau -------------------------------------------------------------

    def _entetes(self) -> Dict[str, str]:
        entetes = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": VERSION_PROTOCOLE,
        }
        if self._session:
            entetes["Mcp-Session-Id"] = self._session
        return entetes

    def _poster(self, corps: Dict[str, Any]) -> Reponse:
        """Envoie un message JSON-RPC. Aucune exception ne sort d'ici."""
        client = self._client or httpx.Client(timeout=self.delai)
        ferme = self._client is None
        try:
            reponse = client.post(self.url, json=corps, headers=self._entetes())
            session = reponse.headers.get("mcp-session-id")
            if session:
                self._session = session
            if reponse.status_code >= 400:
                return Reponse(ok=False, raison=f"HTTP {reponse.status_code}")
            if corps.get("id") is None:
                return Reponse(ok=True)  # notification : pas de reponse attendue
            charge = _charge(reponse)
            if charge is None:
                return Reponse(ok=False, raison="reponse illisible")
            if "error" in charge:
                erreur = charge["error"] or {}
                return Reponse(ok=False, raison=str(erreur.get("message") or erreur))
            return Reponse(ok=True, resultat=charge.get("result") or {})
        except Exception as erreur:  # noqa: BLE001 — une panne est un etat
            logger.info("Appel MCP impossible (%s) : %s", self.url, erreur)
            return Reponse(ok=False, raison=f"{type(erreur).__name__}: {erreur}")
        finally:
            if ferme:
                client.close()

    # --- Protocole ---------------------------------------------------------------

    def ouvrir(self) -> Reponse:
        """Poignee de main. Rejouee seulement si aucune session n'est etablie."""
        if self._session:
            return Reponse(ok=True)
        reponse = self._poster({
            "jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "initialize",
            "params": {
                "protocolVersion": VERSION_PROTOCOLE,
                "capabilities": {},
                "clientInfo": {"name": "ARENA", "version": "1"},
            },
        })
        if reponse.ok:
            self._poster({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return reponse

    def outils(self) -> Reponse:
        """La liste des outils annonces par le serveur."""
        ouverture = self.ouvrir()
        if not ouverture.ok:
            return ouverture
        return self._poster({"jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "tools/list"})

    def appeler(self, nom: str, arguments: Optional[Dict[str, Any]] = None) -> Reponse:
        """Appelle un outil. Le serveur choisit ce qu'il rend ; on ne suppose rien."""
        ouverture = self.ouvrir()
        if not ouverture.ok:
            return ouverture
        return self._poster({
            "jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "tools/call",
            "params": {"name": nom, "arguments": arguments or {}},
        })
