"""Boucle agentique : memoire des echecs et anti-repetition.

Ces tests couvrent les deux ajouts du 13/09/2026 :
- `echecs_cumules` : la memoire des echecs est tenue, tour apres tour.
- `anti_repetition` : un plan identique au precedent, sans succes, arrete
  la boucle — mais seulement quand le drapeau est pose.

Aucun test n'appelle de modele : les planificateurs et evaluateurs sont
des fonctions locales, deterministes.

Note sur le format des raisons : `Coordination` prefixe chaque raison
d'echec par le type de l'exception (`RuntimeError: boum`, pas `boum`).
C'est volontaire — un message sans son type est plus dur a diagnostiquer.
Les tests ci-dessous verifient donc ce format reel, pas un format plus
court qu'on aurait souhaite.
"""
from core.execution.boucle import (
    BoucleAgentique,
    Budget,
    RaisonDArret,
)
from core.execution.coordination import Etape

#: La raison telle que `Coordination` la stocke : type + message.
RAISON_BOUM = "RuntimeError: boum"


def _etape_ok(nom: str):
    async def appel():
        return f"{nom}:ok"
    return Etape(nom, appel)


def _etape_ko(nom: str, raison: str = "boum"):
    def appel():
        raise RuntimeError(raison)
    return Etape(nom, appel, essais_max=1)


# --- Memoire des echecs -----------------------------------------------------


async def test_echecs_cumules_accumulent_les_raisons():
    """Trois tours, une etape qui echoue a chaque fois : trois raisons."""

    def planifier(objectif, tours):
        return [_etape_ko("fragile")]

    def evaluer(resultat, acquis):
        return False, "pas atteint"

    boucle = BoucleAgentique(
        objectif="tester la memoire",
        planifier=planifier,
        evaluer=evaluer,
        budget=Budget(tours_max=3, etapes_max=9),
    )
    etat = await boucle.executer()

    assert etat.raison_d_arret is RaisonDArret.BUDGET_TOURS
    assert "fragile" in etat.echecs_cumules
    assert etat.echecs_cumules["fragile"] == [RAISON_BOUM] * 3


async def test_etapes_recalcitrantes_ne_garde_que_2_fois_et_plus():
    """Une etape qui echoue une seule fois n'est pas recalcitrante."""

    compteur = {"n": 0}

    def planifier(objectif, tours):
        compteur["n"] += 1
        if compteur["n"] == 1:
            return [_etape_ko("instable")]
        return [_etape_ok("stable")]

    def evaluer(resultat, acquis):
        return "stable" in acquis, "ok"

    boucle = BoucleAgentique(
        objectif="mesurer la recalcitance",
        planifier=planifier,
        evaluer=evaluer,
        budget=Budget(tours_max=4),
    )
    etat = await boucle.executer()

    assert etat.raison_d_arret is RaisonDArret.OBJECTIF_ATTEINT
    # Un echec unique : pas recalcitrante.
    assert etat.etapes_recalcitrantes == {}
    # Mais la trace est bien la, avec le format reel.
    assert etat.echecs_cumules.get("instable") == [RAISON_BOUM]


async def test_observation_porte_les_echecs_cumules():
    """Chaque Observation voit l'historique jusqu'a elle incluse."""

    def planifier(objectif, tours):
        return [_etape_ko("A")]

    def evaluer(resultat, acquis):
        return False, "non"

    boucle = BoucleAgentique(
        objectif="verifier la visibilite",
        planifier=planifier,
        evaluer=evaluer,
        budget=Budget(tours_max=2, etapes_max=4),
    )
    etat = await boucle.executer()

    assert len(etat.tours) == 2
    # Tour 1 : l'echec du tour 1 est deja visible.
    assert etat.tours[0].echecs_cumules == {"A": [RAISON_BOUM]}
    # Tour 2 : les echecs des tours 1 ET 2 sont la.
    assert etat.tours[1].echecs_cumules == {"A": [RAISON_BOUM, RAISON_BOUM]}


# --- Anti-repetition --------------------------------------------------------


async def test_anti_repetition_arrete_sur_plan_identique():
    """Meme plan, objectif non atteint, drapeau pose : arret immediat."""

    def planifier(objectif, tours):
        return [_etape_ok("A")]

    def evaluer(resultat, acquis):
        return False, "pas encore"

    boucle = BoucleAgentique(
        objectif="boucler proprement",
        planifier=planifier,
        evaluer=evaluer,
        budget=Budget(tours_max=5),
        anti_repetition=True,
    )
    etat = await boucle.executer()

    assert etat.raison_d_arret is RaisonDArret.PLAN_REPETE
    # Un seul tour consomme : le second a ete refuse avant execution.
    assert len(etat.tours) == 1


async def test_anti_repetition_desactivee_par_defaut():
    """Sans le drapeau, comportement historique : on epuise le budget de tours."""

    def planifier(objectif, tours):
        return [_etape_ok("A")]

    def evaluer(resultat, acquis):
        return False, "non"

    boucle = BoucleAgentique(
        objectif="comportement historique",
        planifier=planifier,
        evaluer=evaluer,
        budget=Budget(tours_max=3),
    )
    etat = await boucle.executer()

    assert etat.raison_d_arret is RaisonDArret.BUDGET_TOURS
    assert len(etat.tours) == 3


async def test_anti_repetition_ne_declenche_pas_si_objectif_atteint():
    """Repeter un plan qui a atteint l'objectif n'est pas une repetition."""

    appels = {"n": 0}

    def planifier(objectif, tours):
        appels["n"] += 1
        if appels["n"] == 1:
            return [_etape_ok("A")]
        return [_etape_ok("A")]

    def evaluer(resultat, acquis):
        return True, "ok"

    boucle = BoucleAgentique(
        objectif="repetition legitime",
        planifier=planifier,
        evaluer=evaluer,
        budget=Budget(tours_max=5),
        anti_repetition=True,
    )
    etat = await boucle.executer()

    # L'objectif etant atteint au tour 1, on ne va meme pas au tour 2.
    assert etat.raison_d_arret is RaisonDArret.OBJECTIF_ATTEINT
    assert len(etat.tours) == 1


async def test_anti_repetition_laisse_passer_un_plan_different():
    """Un plan different apres un echec n'est pas une repetition."""

    tours_planifies = {"n": 0}

    def planifier(objectif, tours):
        tours_planifies["n"] += 1
        if tours_planifies["n"] == 1:
            return [_etape_ok("A")]
        return [_etape_ok("B")]

    def evaluer(resultat, acquis):
        return "B" in acquis, "ok" if "B" in acquis else "pas encore"

    boucle = BoucleAgentique(
        objectif="varier les plans",
        planifier=planifier,
        evaluer=evaluer,
        budget=Budget(tours_max=4),
        anti_repetition=True,
    )
    etat = await boucle.executer()

    assert etat.raison_d_arret is RaisonDArret.OBJECTIF_ATTEINT
    assert len(etat.tours) == 2


# --- Trace serialisable ------------------------------------------------------


async def test_etat_boucle_to_dict_expose_les_echecs():
    """`to_dict()` expose echecs_cumules et etapes_recalcitrantes quand utiles."""

    def planifier(objectif, tours):
        return [_etape_ko("A")]

    def evaluer(resultat, acquis):
        return False, "non"

    boucle = BoucleAgentique(
        objectif="serialisation",
        planifier=planifier,
        evaluer=evaluer,
        budget=Budget(tours_max=2, etapes_max=4),
    )
    etat = await boucle.executer()

    d = etat.to_dict()
    assert "echecs_cumules" in d
    assert "A" in d["echecs_cumules"]
    assert d["echecs_cumules"]["A"] == [RAISON_BOUM, RAISON_BOUM]
    assert d["etapes_recalcitrantes"] == {"A": 2}
