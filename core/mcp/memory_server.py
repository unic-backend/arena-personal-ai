"""Le serveur MCP d'ARENA — la memoire canonique, exposee a un client MCP
compatible (Claude Desktop, Cursor, un autre outil MCP).

Mission ARENA x AI MEMORY VAULT (11/09/2026, DEC-0090). `core/mcp/` ne
contenait jusqu'ici qu'un CLIENT (`transport.py`/`stdio_transport.py` :
ARENA parle a WanGP ou OpenTakeoff). Ceci est le premier SERVEUR MCP
d'ARENA — expose une seule capacite (la memoire), jamais un second registre
ou un second moteur de permissions : les six outils appellent directement
`core/memory/personnelle.py::MemoirePersonnelle`, le meme objet que le reste
du depot, jamais une copie.

AI Memory Vault (`mcp_server/server.py`, audit complet ->
`docs/audits/ai_memory_vault_audit.md`) a servi de reference pour le CHOIX
des six outils (`search_memory`, `create_memory`, `list_memory`,
`approve_memory`, `reject_memory`, `delete_memory`) — jamais pour leur code :
leur serveur fait un aller-retour HTTP vers son propre backend FastAPI ; ici,
le serveur MCP et le backend ARENA partagent le MEME fichier SQLite
(`PRAGMA journal_mode=WAL`, ajoute a `MemoirePersonnelle._connexion` pour
cette raison precise — deux processus qui l'ecrivent en meme temps), jamais
un second saut reseau pour la meme donnee.

**Pourquoi aucune cle d'API ici, contrairement a AI Memory Vault** : leur
serveur MCP parle a leur backend par HTTP, donc a besoin d'une cle pour
franchir ce reseau. Le serveur ici lit directement le fichier SQLite
d'ARENA — celui qui peut LANCER ce processus a deja, par construction, un
acces filesystem identique au fichier lui-meme. Ajouter une cle d'API
verifiee dans le meme processus qui detient deja les deux cles serait un
theatre de securite, pas une frontiere reelle. La vraie frontiere est
`USMAN_MEMORY_VAULT_PASSPHRASE` (chiffrement au repos, `sensible=True`
seulement) et le systeme de fichiers lui-meme (qui peut lire
`data/database/memory.db`).

**Gouvernance, jamais contournee** : `create_memory` ecrit toujours
`Nature.INFERENCE` — un client MCP externe ne peut jamais faire passer une
affirmation directement pour un `FAIT` (§9 de la mission, meme regle que
l'import de conversations, `core/memory/import_conversations.py`).
`search_memory`/`list_memory` ne rendent, par defaut, que les souvenirs
`Etat.ACTIF` (deja le defaut de `MemoirePersonnelle.souvenirs()`) : un
souvenir rejete reste invisible d'un client MCP comme il l'est du reste
d'ARENA.

Lancement (le meme fichier que le backend, jamais une base separee) :

    python -m core.mcp.memory_server

Variables d'environnement (les memes que le reste de la memoire, aucune
nouvelle convention) :

    USMAN_MEMORY_DB_PATH            (defaut : data/database/memory.db)
    USMAN_MEMORY_VAULT_PASSPHRASE   (optionnelle — voir chiffrement.py)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from mcp.server.mcpserver import MCPServer

from core.memory.chiffrement import Coffre
from core.memory.personnelle import (
    MemoirePersonnelle,
    Nature,
    Souvenir,
    TypeSouvenir,
)
from core.memory.recuperation import BUDGET_PAR_DEFAUT, recuperer

logger = logging.getLogger("usman.mcp.memory_server")

VARIABLE_DB_PATH = "USMAN_MEMORY_DB_PATH"
DB_PATH_PAR_DEFAUT = "data/database/memory.db"

mcp = MCPServer("ARENA Memory")


def _construire_memoire() -> MemoirePersonnelle:
    chemin = os.environ.get(VARIABLE_DB_PATH, DB_PATH_PAR_DEFAUT)
    return MemoirePersonnelle(db_path=chemin, coffre=Coffre.depuis_environnement())


# Une seule instance pour la duree du processus — comme `memoire_personnelle`
# dans `apps/backend/runtime.py`, jamais reconstruite a chaque appel d'outil.
_memoire: Optional[MemoirePersonnelle] = None


def _obtenir_memoire() -> MemoirePersonnelle:
    global _memoire
    if _memoire is None:
        _memoire = _construire_memoire()
    return _memoire


def _type_depuis_texte(type_texte: str) -> TypeSouvenir:
    try:
        return TypeSouvenir(type_texte.upper())
    except ValueError as erreur:
        valides = ", ".join(t.value for t in TypeSouvenir)
        raise ValueError(f"Type inconnu ({type_texte!r}). Valides : {valides}.") from erreur


def _souvenir_vers_dict(souvenir: Souvenir) -> Dict[str, Any]:
    return souvenir.to_dict()


@mcp.tool()
def search_memory(query: str, projet: Optional[str] = None,
                   budget_caracteres: int = BUDGET_PAR_DEFAUT) -> List[Dict[str, Any]]:
    """Cherche dans la memoire ACTIVE d'ARENA, par pertinence — jamais tout le
    coffre (§10 : correspondance + importance + recence + fenetre temporelle,
    dans un budget dur de caracteres). Un souvenir rejete n'apparait jamais ici."""
    resultats = recuperer(_obtenir_memoire(), query, budget_caracteres=budget_caracteres,
                           projet=projet)
    return [
        {**_souvenir_vers_dict(r.souvenir), "score": r.score, "pourquoi": r.pourquoi()}
        for r in resultats
    ]


@mcp.tool()
def create_memory(contenu: str, type: str, source: str = "mcp-client",
                   projet: Optional[str] = None) -> Dict[str, Any]:
    """Cree un souvenir CANDIDAT (`Nature.INFERENCE`) pour revue par le
    proprietaire. Jamais directement un fait — voir `approve_memory`."""
    memoire = _obtenir_memoire()
    souvenir = memoire.retenir(
        contenu=contenu, type=_type_depuis_texte(type), nature=Nature.INFERENCE,
        source=source, projet=projet,
    )
    return _souvenir_vers_dict(souvenir)


@mcp.tool()
def list_memory(projet: Optional[str] = None, inclure_rejetes: bool = False,
                 limite: int = 50) -> List[Dict[str, Any]]:
    """Liste les souvenirs actifs (et rejetes si demande explicitement)."""
    memoire = _obtenir_memoire()
    return [
        _souvenir_vers_dict(s)
        for s in memoire.souvenirs(projet=projet, limite=limite, inclure_rejetes=inclure_rejetes)
    ]


@mcp.tool()
def approve_memory(id: str, source: str = "mcp-client") -> Dict[str, Any]:
    """Approuve un souvenir : le seul chemin par lequel une INFERENCE devient
    un FAIT (`MemoirePersonnelle.confirmer`)."""
    memoire = _obtenir_memoire()
    souvenir = memoire.confirmer(id, source=source)
    if souvenir is None:
        raise ValueError(f"Aucun souvenir avec l'identifiant {id!r}.")
    return _souvenir_vers_dict(souvenir)


@mcp.tool()
def reject_memory(id: str, source: str = "mcp-client") -> Dict[str, Any]:
    """Rejette un souvenir : exclu de la lecture par defaut, jamais detruit."""
    memoire = _obtenir_memoire()
    souvenir = memoire.rejeter(id, source=source)
    if souvenir is None:
        raise ValueError(f"Aucun souvenir avec l'identifiant {id!r}.")
    return _souvenir_vers_dict(souvenir)


@mcp.tool()
def delete_memory(id: str) -> Dict[str, str]:
    """Suppression reelle et definitive. Voir `MemoirePersonnelle.supprimer`
    pour pourquoi rien d'autre n'a besoin d'etre purge (aucun index separe)."""
    memoire = _obtenir_memoire()
    if not memoire.supprimer(id):
        raise ValueError(f"Aucun souvenir avec l'identifiant {id!r}.")
    return {"status": "deleted", "id": id}


if __name__ == "__main__":
    mcp.run()
