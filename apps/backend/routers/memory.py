"""`/api/memory` — la memoire canonique d'ARENA, exposee par HTTP.

Mission ARENA x AI MEMORY VAULT (11/09/2026, DEC-0090). Meme discipline que
`conversations.py`/`executive.py` : deux protections (`verify_api_key`,
`limiter_debit`), et la route ne fait QUE deleguer a
`core/memory/personnelle.py::MemoirePersonnelle` (via le singleton
`memoire_personnelle` de `apps/backend/runtime.py`) — jamais une seconde
logique de memoire, jamais une seconde regle de gouvernance. Le meme service
que le serveur MCP (`core/mcp/memory_server.py`) : un client HTTP et un
client MCP voient EXACTEMENT la meme memoire, la meme gouvernance
(`Etat.ACTIF` par defaut, `Nature.INFERENCE` a la creation).

**Ce qui differe de `core/mcp/memory_server.py`** : ici, `verify_api_key`
protege un vrai reseau (le tunnel Cloudflare de `scripts/lancer_arena.ps1`,
DEC-0089) — la meme cle que le reste de la passerelle, jamais une seconde
cle inventee pour la memoire seule.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from apps.backend.runtime import memoire_personnelle
from apps.backend.security import limiter_debit, verify_api_key
from core.memory.contradiction import LIMITE_PAR_DEFAUT
from core.memory.contradiction import rapport as rapport_contradictions
from core.memory.import_conversations import FormatImportInconnu, importer_dans_la_memoire
from core.memory.personnelle import Nature, TypeSouvenir
from core.memory.recuperation import BUDGET_PAR_DEFAUT, recuperer

logger = logging.getLogger("usman.backend.memory")

router = APIRouter()

_PROTECTIONS = [Depends(verify_api_key), Depends(limiter_debit)]


class CreationSouvenir(BaseModel):
    contenu: str = Field(min_length=1)
    type: str
    source: str
    projet: Optional[str] = None
    importance: float = 0.5
    sensible: bool = False


class ChangementEtat(BaseModel):
    source: str = Field(min_length=1)


def _type_depuis_texte(type_texte: str) -> TypeSouvenir:
    try:
        return TypeSouvenir(type_texte.upper())
    except ValueError as erreur:
        valides = ", ".join(t.value for t in TypeSouvenir)
        raise HTTPException(
            status_code=422, detail=f"Type inconnu ({type_texte!r}). Valides : {valides}.",
        ) from erreur


@router.get("/api/memory", dependencies=_PROTECTIONS)
async def lister(
    projet: Optional[str] = None,
    type: Optional[str] = None,
    limite: int = Query(default=50, ge=1, le=500),
    inclure_rejetes: bool = False,
    inclure_archives: bool = False,
) -> List[Dict[str, Any]]:
    """Les souvenirs actifs (et rejetes/archives si demande explicitement)."""
    type_souvenir = _type_depuis_texte(type) if type else None
    souvenirs = memoire_personnelle.souvenirs(
        type=type_souvenir, projet=projet, limite=limite,
        inclure_rejetes=inclure_rejetes, inclure_archives=inclure_archives,
    )
    return [s.to_dict() for s in souvenirs]


@router.get("/api/memory/search", dependencies=_PROTECTIONS)
async def chercher(
    q: str = Query(min_length=1),
    projet: Optional[str] = None,
    budget_caracteres: int = Query(default=BUDGET_PAR_DEFAUT, ge=100, le=20_000),
) -> List[Dict[str, Any]]:
    """Recherche pertinente et bornee (§10) — jamais toute la memoire."""
    resultats = recuperer(memoire_personnelle, q, budget_caracteres=budget_caracteres, projet=projet)
    return [{**r.souvenir.to_dict(), "score": r.score, "pourquoi": r.pourquoi()} for r in resultats]


# ATTENTION A L'ORDRE : cette route doit rester AVANT `/api/memory/{identifiant}`.
# FastAPI resout dans l'ordre de declaration ; placee apres, « contradictions »
# serait lu comme un identifiant de souvenir et la route rendrait un 404.
# `tests/test_memory_router.py` epingle ce point precis.
@router.get("/api/memory/contradictions", dependencies=_PROTECTIONS)
async def lister_contradictions(
    projet: Optional[str] = None,
    limite: int = Query(default=LIMITE_PAR_DEFAUT, ge=1, le=5_000),
) -> Dict[str, Any]:
    """Ce que la memoire croit et qui ne peut pas etre vrai ensemble.

    ARENA **rapporte** le conflit et n'en tranche aucun : les deux souvenirs
    reviennent entiers, avec leur source, leur nature et leur date, et
    `resolue_par` vaut toujours `null`. Choisir un tarif a la place du
    proprietaire serait indiscernable du bon tant qu'une facture n'arrive pas.

    La reponse porte toujours `portee` : la detection est numerique, la
    negation n'en fait pas partie, et « 0 contradiction » ne veut donc pas dire
    « memoire coherente ».
    """
    return rapport_contradictions(memoire_personnelle, projet=projet, limite=limite)


@router.get("/api/memory/{identifiant}", dependencies=_PROTECTIONS)
async def lire(identifiant: str) -> Dict[str, Any]:
    souvenir = memoire_personnelle.lire(identifiant)
    if souvenir is None:
        raise HTTPException(status_code=404, detail="Souvenir introuvable.")
    return souvenir.to_dict()


@router.post("/api/memory", dependencies=_PROTECTIONS)
async def creer(demande: CreationSouvenir) -> Dict[str, Any]:
    """Cree un souvenir CANDIDAT — toujours `Nature.INFERENCE`, jamais un fait
    direct : un appelant HTTP externe n'obtient jamais un fait sans passer par
    `/approve` (meme regle que le serveur MCP)."""
    try:
        souvenir = memoire_personnelle.retenir(
            contenu=demande.contenu, type=_type_depuis_texte(demande.type),
            nature=Nature.INFERENCE, source=demande.source, projet=demande.projet,
            importance=demande.importance, sensible=demande.sensible,
        )
    except ValueError as erreur:
        raise HTTPException(status_code=422, detail=str(erreur)) from erreur
    return souvenir.to_dict()


@router.post("/api/memory/{identifiant}/approve", dependencies=_PROTECTIONS)
async def approuver(identifiant: str, demande: ChangementEtat) -> Dict[str, Any]:
    souvenir = memoire_personnelle.confirmer(identifiant, source=demande.source)
    if souvenir is None:
        raise HTTPException(status_code=404, detail="Souvenir introuvable.")
    return souvenir.to_dict()


@router.post("/api/memory/{identifiant}/reject", dependencies=_PROTECTIONS)
async def rejeter(identifiant: str, demande: ChangementEtat) -> Dict[str, Any]:
    souvenir = memoire_personnelle.rejeter(identifiant, source=demande.source)
    if souvenir is None:
        raise HTTPException(status_code=404, detail="Souvenir introuvable.")
    return souvenir.to_dict()


@router.post("/api/memory/{identifiant}/archive", dependencies=_PROTECTIONS)
async def archiver(identifiant: str, demande: ChangementEtat) -> Dict[str, Any]:
    souvenir = memoire_personnelle.archiver(identifiant, source=demande.source)
    if souvenir is None:
        raise HTTPException(status_code=404, detail="Souvenir introuvable.")
    return souvenir.to_dict()


@router.post("/api/memory/{identifiant}/reactivate", dependencies=_PROTECTIONS)
async def reactiver(identifiant: str, demande: ChangementEtat) -> Dict[str, Any]:
    souvenir = memoire_personnelle.reactiver(identifiant, source=demande.source)
    if souvenir is None:
        raise HTTPException(status_code=404, detail="Souvenir introuvable.")
    return souvenir.to_dict()


@router.delete("/api/memory/{identifiant}", dependencies=_PROTECTIONS)
async def supprimer(identifiant: str) -> Dict[str, str]:
    if not memoire_personnelle.supprimer(identifiant):
        raise HTTPException(status_code=404, detail="Souvenir introuvable.")
    return {"status": "deleted", "id": identifiant}


@router.get("/api/memory/export/all", dependencies=_PROTECTIONS)
async def exporter() -> Dict[str, Any]:
    """Tout ce que le coffre contient (actifs, rejetes, archives) — le
    proprietaire garde la propriete de sa memoire (§20).

    Distinction explicite, jamais implicite : `contenu_chiffre` dit si CE
    souvenir precis est sensible. Un export n'est PAS lui-meme chiffre — le
    proprietaire qui veut une sauvegarde chiffree protege le FICHIER
    d'export a son tour (l'API ne pretend jamais offrir un chiffrement
    qu'elle n'applique pas)."""
    souvenirs = memoire_personnelle.souvenirs(
        limite=100_000, inclure_perimes=True, inclure_rejetes=True, inclure_archives=True,
    )
    return {
        "export_chiffre": False,
        "avertissement": (
            "Cet export est en clair (les souvenirs sensibles sont dechiffres "
            "s'ils sont lisibles) : protege ce fichier toi-meme si tu le stockes."
        ),
        "souvenirs": [s.to_dict() for s in souvenirs],
    }


@router.post("/api/memory/import", dependencies=_PROTECTIONS)
async def importer(
    fichier: UploadFile = File(...),
    source: str = "import_center",
    projet: Optional[str] = None,
) -> Dict[str, Any]:
    """IMPORT -> PARSE -> CANDIDAT -> DEDUPLICATION -> `Nature.INFERENCE`.
    Jamais canonique tant que le proprietaire n'a pas approuve (§18)."""
    contenu = await fichier.read()
    try:
        resultat = importer_dans_la_memoire(
            memoire_personnelle, fichier.filename or "import", contenu, source=source, projet=projet,
        )
    except FormatImportInconnu as erreur:
        raise HTTPException(status_code=400, detail=str(erreur)) from erreur
    return {
        "format_detecte": resultat.format_detecte,
        "crees": [s.to_dict() for s in resultat.crees],
        "doublons_ignores": resultat.doublons_ignores,
        "refuses": [{"extrait": extrait, "raison": raison} for extrait, raison in resultat.refuses],
    }
