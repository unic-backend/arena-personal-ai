"""La boucle qui replanifie — et qui s'arrête, toujours.

Ce que ces tests gardent, dans l'ordre d'importance :

1. **un plan qui échoue est refait**, et le nouveau plan voit la raison réelle
   de l'échec — c'est la capacité qui n'existait pas (audit du 12/09/2026,
   section D) ;
2. **aucune sortie sans raison d'arrêt**, y compris quand le planificateur
   lève, rend une liste vide, ou propose sans fin le même plan raté ;
3. **un budget dépassé arrête avant d'agir** — un plan trop gros n'est pas
   exécuté à moitié.
"""
import asyncio

import pytest

from core.execution.boucle import (
    BoucleAgentique,
    Budget,
    Observation,
    RaisonDArret,
)
from core.execution.coordination import Etape


def etape_qui_echoue(nom: str, message: str = "service indisponible") -> Etape:
    def _echouer():
        raise RuntimeError(message)
    return Etape(nom=nom, appel=_echouer)


def etape_qui_reussit(nom: str, valeur: str = "ok") -> Etape:
    return Etape(nom=nom, appel=lambda: valeur)


def jamais_atteint(resultat, acquis):
    return False, "l'objectif n'est jamais declare atteint dans ce test"


def atteint_si(nom_etape: str):
    """Évaluateur DÉTERMINISTE : l'objectif est atteint quand cette étape a réussi."""
    def _evaluer(resultat, acquis):
        if nom_etape in acquis:
            return True, f"« {nom_etape} » a produit un resultat"
        return False, f"« {nom_etape} » n'a rien produit"
    return _evaluer


# --- 1. Ce qui n'existait pas : replanifier après observation ------------------

class TestLePlanSeRefaitApresObservation:

    @pytest.mark.asyncio
    async def test_un_plan_qui_echoue_est_refait_et_le_second_aboutit(self):
        """Le cas de la mission : plan A échoue → comprendre → plan B → vérifier."""
        plans = []

        def planifier(objectif, observations):
            plans.append(len(observations))
            if not observations:
                return [etape_qui_echoue("chemin_a")]
            return [etape_qui_reussit("chemin_b", "la reponse")]

        etat = await BoucleAgentique(
            objectif="trouver la reponse",
            planifier=planifier,
            evaluer=atteint_si("chemin_b"),
        ).executer()

        assert etat.atteint
        assert etat.raison_d_arret is RaisonDArret.OBJECTIF_ATTEINT
        assert [o.plan for o in etat.tours] == [["chemin_a"], ["chemin_b"]]
        assert etat.replanifications == 1
        assert etat.acquis["chemin_b"] == "la reponse"

    @pytest.mark.asyncio
    async def test_le_replanificateur_voit_la_RAISON_de_l_echec(self):
        """Sans la raison, « replanifier » n'est qu'un second essai au hasard."""
        vues = []

        def planifier(objectif, observations):
            for obs in observations:
                vues.extend(raison for _, raison in obs.echouees)
            if not observations:
                return [etape_qui_echoue("appel_api", "HTTP 503 chez le fournisseur")]
            return [etape_qui_reussit("repli_local")]

        await BoucleAgentique(
            objectif="obtenir la donnee", planifier=planifier,
            evaluer=atteint_si("repli_local"),
        ).executer()

        assert any("503" in v for v in vues), (
            f"la raison reelle n'a pas atteint le replanificateur : {vues}")

    @pytest.mark.asyncio
    async def test_l_etat_vit_en_python_pas_dans_du_texte(self):
        """Règle 1 : les comptes viennent de l'exécution, pas d'un résumé."""
        def planifier(objectif, observations):
            return [] if observations else [etape_qui_reussit("a"), etape_qui_echoue("b")]

        etat = await BoucleAgentique(
            objectif="mesurer", planifier=planifier, evaluer=jamais_atteint,
        ).executer()

        rendu = etat.to_dict()
        assert rendu["etapes_consommees"] == 2
        assert rendu["tours"][0]["reussies"] == ["a"]
        assert rendu["tours"][0]["echouees"][0]["etape"] == "b"
        assert "RuntimeError" in rendu["tours"][0]["echouees"][0]["raison"]


# --- 2. La boucle s'arrête, toujours, et dit pourquoi -------------------------

class TestElleSArreteToujours:

    @pytest.mark.asyncio
    async def test_un_planificateur_obstine_ne_boucle_pas_a_l_infini(self):
        """Le même plan raté, proposé sans fin : c'est le budget qui tranche."""
        appels = []

        def planifier(objectif, observations):
            appels.append(1)
            return [etape_qui_echoue("toujours_le_meme")]

        etat = await BoucleAgentique(
            objectif="insister", planifier=planifier, evaluer=jamais_atteint,
            budget=Budget(tours_max=3, etapes_max=99),
        ).executer()

        assert etat.raison_d_arret is RaisonDArret.BUDGET_TOURS
        assert len(appels) == 3, "le plafond de tours n'a pas tenu"
        assert len(etat.tours) == 3

    @pytest.mark.asyncio
    async def test_un_planificateur_qui_leve_n_emporte_pas_la_boucle(self):
        def planifier(objectif, observations):
            raise ValueError("le modele de planification est injoignable")

        etat = await BoucleAgentique(
            objectif="planifier l'impossible", planifier=planifier,
            evaluer=jamais_atteint,
        ).executer()

        assert etat.raison_d_arret is RaisonDArret.PLANIFICATION_EN_ECHEC
        assert etat.tours == []

    @pytest.mark.asyncio
    async def test_un_plan_vide_est_une_reponse_valable(self):
        """« Je n'ai pas d'autre idée » arrête proprement, sans échec fabriqué."""
        etat = await BoucleAgentique(
            objectif="chercher", planifier=lambda o, obs: [],
            evaluer=jamais_atteint,
        ).executer()

        assert etat.raison_d_arret is RaisonDArret.PLAN_VIDE
        assert not etat.atteint

    @pytest.mark.asyncio
    @pytest.mark.parametrize("planificateur,attendu", [
        (lambda o, obs: [], RaisonDArret.PLAN_VIDE),
        (lambda o, obs: [etape_qui_echoue("x")], RaisonDArret.BUDGET_TOURS),
        (lambda o, obs: [etape_qui_reussit("x")], RaisonDArret.OBJECTIF_ATTEINT),
    ])
    async def test_aucune_sortie_sans_raison_d_arret(self, planificateur, attendu):
        """Règle 2 : il n'existe aucun chemin qui sorte sans raison."""
        etat = await BoucleAgentique(
            objectif="sortir", planifier=planificateur, evaluer=atteint_si("x"),
            budget=Budget(tours_max=2, etapes_max=10),
        ).executer()

        assert etat.raison_d_arret is not None
        assert etat.raison_d_arret is attendu


# --- 3. Les budgets arrêtent AVANT d'agir -------------------------------------

class TestLesBudgetsArretentAvantDAgir:

    @pytest.mark.asyncio
    async def test_un_plan_trop_gros_n_est_pas_execute_a_moitie(self):
        """Règle 4 : un demi-plan n'est pas le plan proposé."""
        executees = []

        def tracee(nom):
            return Etape(nom=nom, appel=lambda: executees.append(nom))

        etat = await BoucleAgentique(
            objectif="trop d'etapes",
            planifier=lambda o, obs: [tracee("a"), tracee("b"), tracee("c")],
            evaluer=jamais_atteint,
            budget=Budget(etapes_max=2),
        ).executer()

        assert etat.raison_d_arret is RaisonDArret.BUDGET_ETAPES
        assert executees == [], "des etapes ont tourne malgre le budget depasse"
        assert etat.etapes_consommees == 0

    @pytest.mark.asyncio
    async def test_le_budget_de_temps_arrete_avant_de_replanifier(self):
        async def lente():
            await asyncio.sleep(0.15)
            return "fini"

        def planifier(objectif, observations):
            return [Etape(nom=f"lente_{len(observations)}", appel=lente)]

        etat = await BoucleAgentique(
            objectif="prendre son temps", planifier=planifier,
            evaluer=jamais_atteint,
            budget=Budget(secondes_max=0.2, tours_max=50, etapes_max=50),
        ).executer()

        assert etat.raison_d_arret is RaisonDArret.BUDGET_TEMPS
        assert etat.secondes >= 0.2

    @pytest.mark.asyncio
    async def test_le_plafond_d_outils_lit_un_compteur_REEL(self):
        compteur = {"n": 0}

        def planifier(objectif, observations):
            return [Etape(nom=f"outil_{len(observations)}",
                          appel=lambda: compteur.__setitem__("n", compteur["n"] + 2))]

        etat = await BoucleAgentique(
            objectif="appeler des outils", planifier=planifier,
            evaluer=jamais_atteint,
            budget=Budget(appels_outils_max=3, tours_max=20, etapes_max=20),
            compteur_outils=lambda: compteur["n"],
        ).executer()

        assert etat.raison_d_arret is RaisonDArret.BUDGET_OUTILS
        assert etat.appels_outils is not None and etat.appels_outils >= 3

    @pytest.mark.asyncio
    async def test_sans_compteur_les_appels_valent_None_jamais_zero(self):
        """Règle 5 : « aucun appel » et « je ne compte pas » sont deux états."""
        etat = await BoucleAgentique(
            objectif="ne rien compter",
            planifier=lambda o, obs: [etape_qui_reussit("x")],
            evaluer=atteint_si("x"),
        ).executer()

        assert etat.appels_outils is None
        assert etat.to_dict()["appels_outils"] is None

    @pytest.mark.asyncio
    async def test_un_compteur_casse_n_arrete_pas_la_boucle(self):
        def casse():
            raise OSError("compteur illisible")

        etat = await BoucleAgentique(
            objectif="compteur casse",
            planifier=lambda o, obs: [etape_qui_reussit("x")],
            evaluer=atteint_si("x"),
            budget=Budget(appels_outils_max=1),
            compteur_outils=casse,
        ).executer()

        assert etat.atteint
        assert etat.appels_outils is None


# --- 4. Le budget est écrit, jamais deviné ------------------------------------

class TestLeBudgetRefuseCeQuiNeBouclePas:

    @pytest.mark.parametrize("kwargs", [
        {"etapes_max": 0}, {"tours_max": 0}, {"secondes_max": 0},
        {"appels_outils_max": -1},
    ])
    def test_un_budget_absurde_est_refuse_a_la_construction(self, kwargs):
        with pytest.raises(ValueError):
            Budget(**kwargs)

    def test_une_boucle_sans_objectif_est_refusee(self):
        with pytest.raises(ValueError):
            BoucleAgentique(objectif="   ", planifier=lambda o, obs: [],
                            evaluer=jamais_atteint)


# --- 5. Ce que l'état rend lisible --------------------------------------------

def test_le_rendu_montre_l_arret_et_les_budgets():
    obs = Observation(tour=1, plan=["a"], echouees=[("a", "RuntimeError: non")])
    assert "echouee" in obs.rendre()
    assert "RuntimeError" in obs.rendre()
