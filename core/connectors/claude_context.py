"""Connecteur Claude Context — recherche sémantique de code, par son propre
serveur MCP, jamais son code importé.

**Ce que ce connecteur donne à ARENA** (mission « intégration unifiée »,
06/09/2026, § « comprehension du code ») : répondre à « où est implémentée
cette fonction ? », « où se trouve la logique d'authentification ? » sans
ouvrir aveuglément des dizaines de fichiers. `core/connectors/graphify.py`
(DEC-0046) répond déjà à des questions STRUCTURELLES (qui hérite de quoi,
plus court chemin) par lecture directe (tree-sitter, sans modèle) ; Claude
Context répond à des questions en LANGAGE NATUREL par similarité vectorielle
— deux mécanismes distincts, jamais fusionnés. `core/connectors/txtai_search.py`
(DEC-0051) est le troisième voisin le plus proche et reste différent lui
aussi : son index est ÉPHÉMÈRE (construit et jeté à chaque appel, sur des
documents FOURNIS, plafonné à 200) — Claude Context, lui, tient un index
PERSISTANT du dépôt avec réindexation incrémentale (arbre de Merkle) : c'est
la capacité qu'aucun des deux autres ne rend, celle qui manquait vraiment.

**Licence, vérifiée en clonant le dépôt réel** (jamais son README seul) :
`zilliztech/claude-context`, MIT (`LICENSE` lu directement). Rien n'empêchait
d'importer son code — la raison de ne pas le faire est architecturale, pas
légale : c'est un projet TypeScript/Node.js, ARENA est Python. Son propre
serveur MCP (`@zilliz/claude-context-mcp`, `packages/mcp/src/index.ts`,
transport `StdioServerTransport`) est la frontière déjà prévue par le projet
lui-même pour un client externe — même transport, même patron que
`core/connectors/opentakeoff.py` (Node.js lui aussi, MCP stdio,
`core/mcp/stdio_transport.py` réutilisé sans une ligne de plus).

**Local-first forcé PAR LA STRUCTURE, pas par confiance** (DEC-0002).
Claude Context accepte quatre fournisseurs d'embeddings (OpenAI, VoyageAI,
Gemini, Ollama) et sa documentation présente OpenAI comme le choix par
défaut, avec un vecteur cloud à la clé. Ce connecteur ne laisse jamais ce
choix filtrer depuis l'environnement hérité : `_environnement()` construit
l'environnement du sous-processus en partant de `os.environ` (pour que
`npx`/`node` résolvent leur PATH), puis **écrase** `EMBEDDING_PROVIDER` à
`"Ollama"` — un `OPENAI_API_KEY` présent ailleurs sur la machine, pour un
usage sans rapport, ne peut donc jamais faire router un seul embedding vers
un service cloud à travers ce connecteur. `MILVUS_ADDRESS` et
`EMBEDDING_MODEL` restent des réglages, jamais une supposition : aucune
valeur par défaut n'est fournie pour l'un ou l'autre — un Milvus local
existe, mais son adresse n'est jamais devinée.

**Trois règles, mêmes qu'OpenTakeoff (`core/connectors/opentakeoff.py`) :**

1. **La sonde interroge le serveur.** Elle demande la liste des outils et
   vérifie que `search_code` y est. Un `npx` qui répond sur autre chose
   qu'un serveur Claude Context ne prouverait rien de plus qu'un port ouvert.
2. **Le processus ne survit jamais à l'appel.** `ClientMcpStdio` est ouvert
   et fermé dans le même `_executer` — jamais un `npx` qui traîne entre
   deux demandes (même choix qu'OpenTakeoff, section 4 de sa docstring).
3. **Indexer et vider l'index restent des écritures locales et rebâtissables**
   (comme `graphify.construire`, DEC-0046) : `ALLOWED` sous `WRITE_FILES`,
   jamais une confirmation par appel — l'index se reconstruit, il ne
   s'envoie nulle part.
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from core.mcp.stdio_transport import ClientMcpStdio, Reponse

logger = logging.getLogger("usman.connecteurs.claude_context")

#: Le binaire npx a lancer. Reglable : sa machine peut en avoir plusieurs
#: (nvm, volta...), meme raison que NODE_BIN dans opentakeoff.py.
NPX_BIN = os.getenv("CLAUDE_CONTEXT_NPX_BIN", "npx").strip() or "npx"

#: Le paquet MCP officiel, publie par Zilliz. Version figee via @latest
#: comme documente par le projet lui-meme (packages/mcp/README.md) : pas de
#: version choisie ici, l'installateur du proprietaire fixera la sienne s'il
#: veut l'epingler.
PAQUET_MCP = os.getenv("CLAUDE_CONTEXT_PACKAGE", "@zilliz/claude-context-mcp@latest").strip()

CE_QUI_MANQUE = (
    "Claude Context a besoin de trois reglages, aucun n'a de defaut : "
    "CLAUDE_CONTEXT_MILVUS_ADDRESS (un Milvus auto-heberge, ex. "
    "http://127.0.0.1:19530 - jamais Zilliz Cloud par defaut), "
    "CLAUDE_CONTEXT_EMBEDDING_MODEL (un modele reellement tire dans Ollama, "
    "ex. nomic-embed-text), et node/npx installes. "
    "OLLAMA_BASE_URL (la meme variable que le reste d'ARENA) est optionnelle "
    "(defaut Ollama : http://127.0.0.1:11434)."
)

DUREE_SONDE_SECONDES = 60.0

#: L'outil sans lequel ce connecteur n'a pas de raison d'exister.
OUTIL_RECHERCHER = "search_code"


def _milvus_address() -> str:
    return os.getenv("CLAUDE_CONTEXT_MILVUS_ADDRESS", "").strip()


def _embedding_model() -> str:
    return os.getenv("CLAUDE_CONTEXT_EMBEDDING_MODEL", "").strip()


def _pret() -> bool:
    return bool(_milvus_address() and _embedding_model())


def _environnement() -> Dict[str, str]:
    """L'environnement du sous-processus : jamais celui du parent tel quel.

    `EMBEDDING_PROVIDER` est ECRASE a "Ollama" — jamais lu depuis
    l'environnement herite, jamais laisse a une valeur par defaut du projet
    (qui pointe vers OpenAI). C'est la garde structurelle de ce module,
    verifiee par sabotage (`tests/core/test_connecteur_claude_context.py`).
    """
    environnement = dict(os.environ)
    environnement["EMBEDDING_PROVIDER"] = "Ollama"
    # Meme variable et meme defaut que `core/memory/semantique.py::OLLAMA_URL`
    # — jamais une deuxieme adresse Ollama inventee pour ce seul connecteur.
    environnement["OLLAMA_HOST"] = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()
    environnement["EMBEDDING_MODEL"] = _embedding_model()
    environnement["MILVUS_ADDRESS"] = _milvus_address()
    jeton = os.getenv("CLAUDE_CONTEXT_MILVUS_TOKEN", "").strip()
    if jeton:
        environnement["MILVUS_TOKEN"] = jeton
    # Aucun watcher de fichier ni synchronisation en arriere-plan : le
    # processus ne survit pas a l'appel (regle 2), un polling de fond n'a
    # donc aucun effet utile et ne ferait que retarder l'arret propre.
    environnement["CLAUDE_CONTEXT_BACKGROUND_SYNC"] = "false"
    environnement["CLAUDE_CONTEXT_TRIGGER_WATCHER"] = "false"
    return environnement


def _commande() -> List[str]:
    return [NPX_BIN, "-y", PAQUET_MCP]


def _erreur_outil(reponse: Reponse) -> Optional[str]:
    return reponse.erreur_applicative


class ConnecteurClaudeContext(Connecteur):
    """Recherche sémantique de code, via le serveur MCP officiel de Claude Context."""

    service = "claude_context"
    nom = "claude_context"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a: float = 0.0

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "indexer": Capacite(
                nom="indexer", action="index",
                description="Indexe (ou re-indexe) un dossier de code pour la recherche sémantique.",
                ecriture=True),
            "rechercher": Capacite(
                nom="rechercher", action="read",
                description="Cherche du code par une question en langage naturel, dans un dossier déjà indexé.",
                ecriture=False),
            "vider_index": Capacite(
                nom="vider_index", action="index",
                description="Supprime l'index d'un dossier — reconstructible par une nouvelle indexation.",
                ecriture=True),
            "etat_indexation": Capacite(
                nom="etat_indexation", action="read",
                description="L'avancement ou l'état de l'indexation d'un dossier.",
                ecriture=False),
        }

    def authentifier(self) -> bool:
        """Vrai : un processus local, sans identifiant a presenter — Milvus
        auto-heberge et Ollama local n'en demandent aucun a ce connecteur."""
        return True

    # --- Sante --------------------------------------------------------------------

    def sonder(self) -> Sante:
        import time
        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante

        if not _pret():
            sante = Sante(
                etat=EtatSante.NON_CONFIGURE,
                message="CLAUDE_CONTEXT_MILVUS_ADDRESS ou CLAUDE_CONTEXT_EMBEDDING_MODEL absent.",
                ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        else:
            with ClientMcpStdio(_commande(), dossier=".", environnement=_environnement()) as client:
                reponse = client.outils()
            if reponse.ok:
                nombre = len(reponse.resultat.get("tools", []))
                noms = {str((o or {}).get("name") or "")
                        for o in (reponse.resultat.get("tools") or [])}
                if OUTIL_RECHERCHER not in noms:
                    sante = Sante(
                        etat=EtatSante.EN_PANNE,
                        message=f"Claude Context repond mais n'annonce pas {OUTIL_RECHERCHER} ({nombre} outil(s) vus).",
                        mesure_le=_maintenant())
                else:
                    sante = Sante(etat=EtatSante.OPERATIONNEL,
                                 message=f"Claude Context repond : {nombre} outil(s) annonce(s).",
                                 mesure_le=_maintenant())
            else:
                sante = Sante(
                    etat=EtatSante.EN_PANNE,
                    message=f"Claude Context ne repond pas : {reponse.raison}",
                    mesure_le=_maintenant())

        self._sante = sante
        self._sante_mesuree_a = maintenant
        return sante

    # --- Execution ------------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        if not _pret():
            return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=CE_QUI_MANQUE)

        chemin = str(parametres.get("chemin") or "").strip()
        if not chemin:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucun chemin de dossier fourni : rien à indexer ni chercher.")
        if not Path(chemin).is_absolute():
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Le chemin doit être absolu : « {chemin} » ne l'est pas.")
        if not Path(chemin).is_dir():
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Aucun dossier à ce chemin : {chemin}")

        with ClientMcpStdio(_commande(), dossier=chemin, environnement=_environnement()) as client:
            if capacite.nom == "indexer":
                return self._indexer(client, chemin, parametres)
            if capacite.nom == "rechercher":
                return self._rechercher(client, chemin, parametres)
            if capacite.nom == "vider_index":
                return self._vider_index(client, chemin)
            return self._etat_indexation(client, chemin)

    def _indexer(self, client: ClientMcpStdio, chemin: str, parametres: Dict[str, Any]) -> ResultatAction:
        arguments: Dict[str, Any] = {"path": chemin}
        if parametres.get("force"):
            arguments["force"] = True
        if parametres.get("extensions_supplementaires"):
            arguments["customExtensions"] = list(parametres["extensions_supplementaires"])
        if parametres.get("motifs_ignores"):
            arguments["ignorePatterns"] = list(parametres["motifs_ignores"])

        reponse = client.appeler("index_codebase", arguments)
        erreur = _erreur_outil(reponse)
        if not reponse.ok or erreur:
            return echec(action="indexer", cible=self.nom,
                         message=f"Indexation refusée : {erreur or reponse.raison}")

        return succes(action="indexer", cible=self.nom,
                      message=f"Indexation lancée pour {chemin}.",
                      preuve=chemin, donnees=reponse.donnees())

    def _rechercher(self, client: ClientMcpStdio, chemin: str, parametres: Dict[str, Any]) -> ResultatAction:
        requete = str(parametres.get("requete") or "").strip()
        if not requete:
            return echec(action="rechercher", cible=self.nom,
                         message="Aucune question fournie : rien à chercher.")

        arguments: Dict[str, Any] = {"path": chemin, "query": requete}
        if parametres.get("limite"):
            arguments["limit"] = int(parametres["limite"])
        if parametres.get("extensions"):
            arguments["extensionFilter"] = list(parametres["extensions"])

        reponse = client.appeler("search_code", arguments)
        erreur = _erreur_outil(reponse)
        if not reponse.ok or erreur:
            if "not indexed" in (erreur or "").lower() or "index" in (erreur or "").lower():
                return non_configure(
                    action="rechercher", cible=self.nom,
                    ce_qui_manque=f"{chemin} n'est pas encore indexé — appeler « indexer » d'abord.")
            return echec(action="rechercher", cible=self.nom,
                         message=f"Recherche refusée : {erreur or reponse.raison}")

        donnees = reponse.donnees()
        resultats = donnees if isinstance(donnees, list) else (donnees or {}).get("results", [])
        return succes(action="rechercher", cible=self.nom,
                      message=f"{len(resultats)} résultat(s) pour « {requete} » dans {chemin}.",
                      preuve=f"{len(resultats)} résultat(s)",
                      resultats=resultats, chemin=chemin, requete=requete)

    def _vider_index(self, client: ClientMcpStdio, chemin: str) -> ResultatAction:
        reponse = client.appeler("clear_index", {"path": chemin})
        erreur = _erreur_outil(reponse)
        if not reponse.ok or erreur:
            return echec(action="vider_index", cible=self.nom,
                         message=f"Suppression refusée : {erreur or reponse.raison}")
        return succes(action="vider_index", cible=self.nom,
                      message=f"Index supprimé pour {chemin}.", preuve=chemin)

    def _etat_indexation(self, client: ClientMcpStdio, chemin: str) -> ResultatAction:
        reponse = client.appeler("get_indexing_status", {"path": chemin})
        erreur = _erreur_outil(reponse)
        if not reponse.ok or erreur:
            return echec(action="etat_indexation", cible=self.nom,
                         message=f"État introuvable : {erreur or reponse.raison}")
        donnees = reponse.donnees() or {}
        return succes(action="etat_indexation", cible=self.nom,
                      message=f"État d'indexation de {chemin} : {donnees}",
                      preuve=chemin, etat=donnees)
