"""`/api/briefing` — le briefing du matin de JARVIS (DEC-0166).

Branche les rubriques de `core/briefing/briefing.py` sur les capacites deja
construites par `apps/backend/runtime.py` : l'agenda (connecteur Google
Calendar), l'agent courrier, et la recherche web pour la meteo et les
actualites. Rien n'est cherche ici autrement qu'a travers elles.

**Chaque matin, seul** : a l'heure `BRIEFING_HEURE` (07:00 par defaut, `off`
pour couper), le serveur compose le briefing et le garde. Demande ensuite
— « Jarvis, mon briefing » ou `GET /api/briefing` —, il est rendu tout de
suite. Au-dela de `VALIDITE`, ou sans briefing du jour, il est recompose.
"""
import asyncio
import logging
import os
from datetime import datetime, time, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends

from apps.backend.runtime import email_agent, fresh_agent, memory, registre
from apps.backend.security import limiter_debit, verify_api_key
from core.briefing.briefing import (
    INCONNU,
    Briefing,
    Rubrique,
    composer_briefing,
    rubrique_agenda,
    rubrique_d_agent,
)

logger = logging.getLogger("usman.backend.briefing")

router = APIRouter()

#: Un briefing plus vieux est recompose : a midi, celui de 7 h a vieilli.
VALIDITE = timedelta(hours=3)

_dernier: Optional[Briefing] = None


def heure_du_briefing() -> Optional[time]:
    """`BRIEFING_HEURE` (« 07:00 »), ou None si coupe ou illisible — une heure
    mal ecrite coupe le briefing automatique et le dit, jamais « minuit »."""
    brut = os.getenv("BRIEFING_HEURE", "07:00").strip().lower()
    if brut in ("", "off", "non", "0"):
        return None
    try:
        heures, minutes = brut.split(":")
        return time(int(heures), int(minutes))
    except ValueError:
        logger.warning("BRIEFING_HEURE illisible (%r) : briefing automatique coupe.", brut)
        return None


def _sources() -> Dict[str, Any]:
    """Les rubriques, dans l'ordre ou elles se lisent. Construites a l'appel :
    la ville et le pays viennent de la memoire du proprietaire, qui change."""
    ville = memory.get_fact("ville")
    pays = memory.get_fact("pays")

    async def agenda() -> Rubrique:
        debut = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        resultat = await asyncio.to_thread(
            registre.executer, "calendrier", "lire", debut=debut, fin=debut + timedelta(days=1))
        return rubrique_agenda(resultat)

    async def courrier() -> Rubrique:
        return rubrique_d_agent("Courrier", await email_agent.run("trie mon courrier", {}))

    async def meteo() -> Rubrique:
        if not ville:
            # Chercher « la meteo » sans lieu rendrait celle d'une ville au
            # hasard des moteurs : on dit ce qui manque.
            return Rubrique("Meteo", INCONNU,
                            "Ville inconnue : enregistre le fait « ville » dans ta memoire "
                            "(par exemple « ville : Dakar »).")
        question = f"Quel temps fait-il à {ville} aujourd'hui ?"
        return rubrique_d_agent("Meteo", await fresh_agent.run(question))

    async def actualites() -> Rubrique:
        lieu = f" au {pays}" if pays else ""
        question = f"Quelles sont les actualités du jour{lieu} ?"
        return rubrique_d_agent("Actualites", await fresh_agent.run(question))

    return {"Agenda": agenda, "Courrier": courrier, "Meteo": meteo, "Actualites": actualites}


async def briefing_du_jour(forcer: bool = False) -> Briefing:
    """Le briefing du jour : celui deja compose s'il est recent, sinon un neuf."""
    global _dernier
    maintenant = datetime.now()
    if (not forcer and _dernier is not None and _dernier.jour == maintenant.date()
            and maintenant - _dernier.compose_a < VALIDITE):
        return _dernier
    _dernier = await composer_briefing(_sources(), maintenant)
    return _dernier


def briefing_deja_compose() -> Optional[Briefing]:
    """Le briefing compose AUJOURD'HUI, s'il existe — sans jamais en composer.

    C'est ce que l'application interroge a l'ouverture (DEC-0168) : elle ne
    doit pas declencher quatre recherches parce qu'on a ouvert l'ecran. Pas de
    limite de trois heures ici : celui de 7 h reste le briefing du jour a midi,
    et son heure de composition s'affiche avec lui."""
    if _dernier is not None and _dernier.jour == datetime.now().date():
        return _dernier
    return None


def secondes_avant(heure: time, maintenant: datetime) -> float:
    """Jusqu'a la prochaine occurrence de `heure` — demain si elle est passee."""
    cible = datetime.combine(maintenant.date(), heure)
    if cible <= maintenant:
        cible += timedelta(days=1)
    return (cible - maintenant).total_seconds()


async def planifier_le_briefing() -> None:
    """Chaque jour a `BRIEFING_HEURE`, compose et garde le briefing.

    Tourne tant que le serveur tourne ; annulee a l'arret. Un echec est
    journalise et n'arrete pas la boucle : le briefing du lendemain aura lieu.
    """
    heure = heure_du_briefing()
    if heure is None:
        logger.info("Briefing automatique coupe (BRIEFING_HEURE).")
        return
    logger.info("Briefing automatique chaque jour a %s.", heure.strftime("%H:%M"))
    while True:
        await asyncio.sleep(secondes_avant(heure, datetime.now()))
        try:
            await briefing_du_jour(forcer=True)
            logger.info("Briefing du matin compose.")
        except Exception as erreur:  # noqa: BLE001 — la boucle survit a un matin rate
            logger.warning("Briefing du matin en echec : %s", erreur)


@router.get("/api/briefing",
            dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def lire_briefing(forcer: bool = False, seulement_pret: bool = False) -> Dict[str, Any]:
    """Le briefing du jour, en texte et par rubrique.

    `seulement_pret` rend celui deja compose aujourd'hui, ou `{"pret": false}` :
    rien n'est compose pour repondre a cette question."""
    if seulement_pret:
        briefing = briefing_deja_compose()
        if briefing is None:
            return {"pret": False}
    else:
        briefing = await briefing_du_jour(forcer=forcer)
    return {"pret": True, "texte": briefing.en_texte(), **briefing.en_dict()}
