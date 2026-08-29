"""Parler a un serveur MCP qui ne parle QUE sur son entree/sortie standard.

`core/mcp/transport.py` sait joindre WanGP : un serveur HTTP, avec un port et
une session qui voyage dans un en-tete. OpenTakeoff (chapitre metre) est
different par construction — lu dans son propre code (`mcp/server.ts`,
`mcp/Dockerfile`) : `StdioServerTransport` uniquement, aucun mode HTTP. Le
proprietaire du depot le dit explicitement dans sa documentation : « Never
point a client config at `npm start` — npm's banner goes to stdout, which is
the MCP wire. » Le protocole EST le flux du processus.

Deux chemins existaient : etendre `ClientMcp` pour parler les deux transports
a la fois, au risque de rendre un module simple illisible, ou ecrire le second
transport a cote, sur le meme contrat de reponse. Le second a ete choisi —
`Reponse` (de `core.mcp.transport`) n'est pas duplique, il est reutilise :
c'est le meme protocole JSON-RPC, seul le tuyau change.

**Trois regles, qui sont les memes que le transport HTTP pour la meme raison :**

1. **Une panne est un etat, jamais une exception qui remonte.** `node`
   absent, le dossier du serveur absent, un processus qui se termine tout
   seul : tout devient un `Reponse` avec sa raison.

2. **La session est un processus, pas un identifiant.** Sans port ni jeton de
   session a transporter, le processus lui-meme EST la session : tant qu'il
   vit, `load_plan` puis `set_scale` puis `detect_rooms` partagent le meme
   etat. Il nait a `ouvrir()`, il meurt a `fermer()`. Un appelant qui garde le
   client au-dela de son usage garde un processus Node vivant pour rien.

3. **Une notification n'est pas une reponse.** Le serveur ecrit des messages
   sans `id` entre deux reponses (ex. `notifications/resources/list_changed`
   apres `load_plan`). Chaque appel lit jusqu'a trouver SON `id`, jamais la
   premiere ligne venue — une mesure faite sur ce serveur reel l'a confirme :
   la premiere ligne apres `load_plan` etait cette notification, pas son
   resultat.
"""
import json
import logging
import os
import selectors
import subprocess
import time
import uuid
from types import TracebackType
from typing import Any, Dict, List, Optional, Type

from core.mcp.transport import VERSION_PROTOCOLE, Reponse

logger = logging.getLogger("usman.mcp.stdio")

#: Delai total accorde a un appel (poignee de main comprise si necessaire).
#: Plus genereux que le transport HTTP : ouvrir un plan PDF fait tourner un
#: moteur de geometrie, pas repondre a une requete web.
DELAI_SECONDES = 60.0

#: Delai laisse au processus pour se terminer proprement avant d'etre tue.
DELAI_ARRET_SECONDES = 5.0


class ClientMcpStdio:
    """Un client MCP minimal, en stdio : lance un processus, lui parle, l'arrete.

    S'utilise comme gestionnaire de contexte pour que le processus ne survive
    jamais a son appelant :

        with ClientMcpStdio(["node", "dist/server.js"], dossier="...") as client:
            client.appeler("load_plan", {"path": "..."})
    """

    def __init__(self, commande: List[str], dossier: str,
                 delai: float = DELAI_SECONDES) -> None:
        self.commande = commande
        self.dossier = dossier
        self.delai = delai
        self._processus: Optional[subprocess.Popen] = None
        self._selecteur: Optional[selectors.BaseSelector] = None
        self._echec_ouverture: str = ""
        #: Octets lus mais pas encore coupes en lignes. Lire au niveau du
        #: descripteur (`os.read`) plutot que via `TextIOWrapper.readline()`
        #: est deliberement plus bas niveau : un `readline()` bufferise peut
        #: avaler plusieurs lignes d'un coup dans SON tampon a lui, invisible
        #: au `select()` qui suit — mesure sur ce module (deux lignes ecrites
        #: par le faux serveur de test dans le meme appel systeme), `select()`
        #: attendait alors le delai complet pour une ligne deja arrivee.
        self._tampon: bytes = b""

    def __enter__(self) -> "ClientMcpStdio":
        poignee = self.ouvrir()
        if not poignee.ok:
            self._echec_ouverture = poignee.raison
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]],
                 exc: Optional[BaseException], tb: Optional[TracebackType]) -> None:
        self.fermer()

    # --- Cycle de vie du processus ----------------------------------------------

    def ouvrir(self) -> Reponse:
        """Lance le processus et fait la poignee de main. Rejouee : sans effet."""
        if self._processus is not None:
            return Reponse(ok=True)
        try:
            self._processus = subprocess.Popen(
                self.commande, cwd=self.dossier,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,  # le serveur y ecrit des avertissements sans consequence
                # Octets bruts (pas `text=True`) : la lecture passe par
                # `os.read()` sur le descripteur, jamais par le tampon interne
                # d'un `TextIOWrapper` — voir la note sur `self._tampon`.
            )
            self._selecteur = selectors.DefaultSelector()
            self._selecteur.register(self._processus.stdout.fileno(), selectors.EVENT_READ)
        except (OSError, FileNotFoundError) as erreur:
            self._processus = None
            self._selecteur = None
            logger.info("Lancement impossible (%s dans %s) : %s",
                        self.commande, self.dossier, erreur)
            return Reponse(ok=False, raison=f"{type(erreur).__name__}: {erreur}")

        poignee = self._poster({
            "jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "initialize",
            "params": {
                "protocolVersion": VERSION_PROTOCOLE,
                "capabilities": {},
                "clientInfo": {"name": "ARENA", "version": "1"},
            },
        })
        if not poignee.ok:
            self.fermer()
            return poignee
        self._notifier({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return poignee

    def fermer(self) -> None:
        """Arrete le processus. N'echoue jamais — un processus deja mort n'est pas une erreur."""
        if self._selecteur is not None:
            try:
                self._selecteur.close()
            except Exception:  # noqa: BLE001 - fermeture, pas une operation qui doit lever
                pass
            self._selecteur = None
        processus, self._processus = self._processus, None
        if processus is None:
            return
        try:
            if processus.stdin:
                processus.stdin.close()
            processus.terminate()
            processus.wait(timeout=DELAI_ARRET_SECONDES)
        except Exception:  # noqa: BLE001 - au pire, on tue
            try:
                processus.kill()
                processus.wait(timeout=DELAI_ARRET_SECONDES)
            except Exception:  # noqa: BLE001 - le processus ne repond plus, rien de plus a faire
                pass

    # --- Protocole ----------------------------------------------------------------

    def outils(self) -> Reponse:
        """La liste des outils annonces par le serveur."""
        return self._poster({"jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "tools/list"})

    def appeler(self, nom: str, arguments: Optional[Dict[str, Any]] = None) -> Reponse:
        """Appelle un outil. Le processus doit deja etre ouvert (voir `ouvrir`)."""
        if self._processus is None:
            return Reponse(ok=False, raison=self._echec_ouverture or "session non ouverte")
        return self._poster({
            "jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "tools/call",
            "params": {"name": nom, "arguments": arguments or {}},
        })

    # --- Bas niveau -----------------------------------------------------------------

    def _notifier(self, corps: Dict[str, Any]) -> None:
        """Envoie un message sans reponse attendue (pas d'`id`)."""
        if self._processus is None or self._processus.stdin is None:
            return
        try:
            self._processus.stdin.write((json.dumps(corps) + "\n").encode("utf-8"))
            self._processus.stdin.flush()
        except Exception as erreur:  # noqa: BLE001 - une panne est un etat
            logger.info("Notification MCP impossible : %s", erreur)

    def _ligne_suivante(self, limite: float) -> Optional[bytes]:
        """Une ligne (sans le `\\n`), en lisant au niveau du descripteur.

        Rend `None` si le delai est depasse, le processus est mort, ou le
        flux s'est ferme sans plus rien envoyer.
        """
        processus = self._processus
        fd = processus.stdout.fileno()
        while b"\n" not in self._tampon:
            restant = limite - time.monotonic()
            if restant <= 0:
                return None
            evenements = self._selecteur.select(timeout=restant) if self._selecteur else []
            if not evenements:
                if processus.poll() is not None:
                    return None
                continue
            morceau = os.read(fd, 65536)
            if not morceau:
                return None  # flux ferme
            self._tampon += morceau
        ligne, _, self._tampon = self._tampon.partition(b"\n")
        return ligne

    def _poster(self, corps: Dict[str, Any]) -> Reponse:
        """Envoie un message JSON-RPC et lit jusqu'a la reponse portant son `id`."""
        processus = self._processus
        if processus is None or processus.stdin is None or processus.stdout is None:
            return Reponse(ok=False, raison=self._echec_ouverture or "processus indisponible")
        try:
            processus.stdin.write((json.dumps(corps) + "\n").encode("utf-8"))
            processus.stdin.flush()
        except Exception as erreur:  # noqa: BLE001 - une panne est un etat
            logger.info("Appel MCP impossible (stdin) : %s", erreur)
            return Reponse(ok=False, raison=f"{type(erreur).__name__}: {erreur}")

        limite = time.monotonic() + self.delai
        while True:
            ligne = self._ligne_suivante(limite)
            if ligne is None:
                if processus.poll() is not None:
                    return Reponse(ok=False, raison=f"processus termine (code {processus.returncode})")
                return Reponse(ok=False, raison=f"delai depasse ({self.delai:g}s)")
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                charge = json.loads(ligne)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue  # une ligne qui n'est pas du JSON-RPC n'est pas notre reponse
            if charge.get("id") != corps.get("id"):
                continue  # une notification, ou la reponse d'un autre appel
            if "error" in charge:
                erreur = charge["error"] or {}
                return Reponse(ok=False, raison=str(erreur.get("message") or erreur))
            return Reponse(ok=True, resultat=charge.get("result") or {})
