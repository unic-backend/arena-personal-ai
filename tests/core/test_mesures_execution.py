"""Les mesures : un chiffre, ou `UNKNOWN`. Jamais un chiffre plausible.

Le test que la phase doit passer est
`test_une_scene_impossible_ne_produit_aucun_chiffre` : quand la scene ne peut
pas tourner, il ne reste ni duree, ni verdict de budget, ni zero.
"""
import asyncio

import pytest

from core.execution.mesures import (
    ETAT_INDISPONIBLE,
    ETAT_MESURE,
    ETAT_NON_LANCE,
    VERDICT_DANS_LE_BUDGET,
    VERDICT_HORS_BUDGET,
    VERDICT_NON_MESURE,
    Mesure,
    Rapport,
    chronometrer,
    non_lancee,
    resume_chiffre,
)
from core.execution.voies import Voie

# --- Le test que la phase doit passer ------------------------------------------

async def test_une_scene_impossible_ne_produit_aucun_chiffre():
    def tombe():
        raise ConnectionError("ollama serve n'est pas lance")

    mesure = await chronometrer("question simple", Voie.LEGERE, tombe)

    assert mesure.etat == ETAT_INDISPONIBLE
    assert mesure.secondes is None, "pas de zero par defaut"
    assert mesure.verdict == VERDICT_NON_MESURE, "une absence n'est pas dans le budget"
    assert "ollama serve" in mesure.detail
    assert "UNKNOWN" in mesure.rendre()


# --- La construction refuse les etats incoherents -------------------------------

def test_une_mesure_sans_duree_ne_se_construit_pas():
    with pytest.raises(ValueError, match="pas une mesure"):
        Mesure(nom="simple", voie=Voie.LEGERE, etat=ETAT_MESURE)


def test_une_absence_porteuse_de_duree_ne_se_construit_pas():
    with pytest.raises(ValueError, match="n'a pas de duree"):
        Mesure(nom="simple", voie=Voie.LEGERE, etat=ETAT_INDISPONIBLE, secondes=0.0)


def test_zero_est_une_mesure_pas_une_absence():
    mesure = Mesure(nom="instantane", voie=Voie.INSTANTANEE, etat=ETAT_MESURE, secondes=0.0)

    assert mesure.secondes == 0.0
    assert mesure.verdict == VERDICT_DANS_LE_BUDGET
    assert "UNKNOWN" not in mesure.rendre()


# --- Le chronometre --------------------------------------------------------------

async def test_un_appel_synchrone_est_chronometre():
    mesure = await chronometrer("outil", Voie.LEGERE, lambda: sum(range(1000)))

    assert mesure.etat == ETAT_MESURE
    assert mesure.secondes is not None and mesure.secondes >= 0.0
    assert len(mesure.echantillons) == 1


async def test_un_appel_asynchrone_est_chronometre():
    async def dormir():
        await asyncio.sleep(0.01)

    mesure = await chronometrer("premier jeton", Voie.LEGERE, dormir)

    assert mesure.etat == ETAT_MESURE
    assert mesure.secondes >= 0.01


async def test_la_duree_retenue_est_la_mediane_des_repetitions():
    mesure = await chronometrer("recuperation", Voie.LEGERE, lambda: None, repetitions=5)

    assert len(mesure.echantillons) == 5
    assert mesure.secondes == pytest.approx(sorted(mesure.echantillons)[2])


async def test_mesurer_zero_fois_est_refuse():
    with pytest.raises(ValueError, match="ne mesure rien"):
        await chronometrer("simple", Voie.LEGERE, lambda: None, repetitions=0)


# --- Le verdict face au budget ----------------------------------------------------

def test_une_duree_au_dela_de_la_cible_est_hors_budget():
    lente = Mesure(nom="simple", voie=Voie.LEGERE, etat=ETAT_MESURE, secondes=30.0)

    assert lente.verdict == VERDICT_HORS_BUDGET


def test_une_scene_non_lancee_reste_au_rapport():
    mesure = non_lancee("recherche web", Voie.RECHERCHE, "aucun fournisseur configure")

    assert mesure.etat == ETAT_NON_LANCE
    assert mesure.verdict == VERDICT_NON_MESURE
    assert "aucun fournisseur configure" in mesure.rendre()


# --- Le rapport -------------------------------------------------------------------

def test_le_rapport_montre_les_lignes_manquantes():
    rapport = Rapport()
    rapport.ajouter(Mesure(nom="simple", voie=Voie.LEGERE, etat=ETAT_MESURE, secondes=1.0))
    rapport.ajouter(non_lancee("recherche web", Voie.RECHERCHE, "hors ligne"))

    rendu = rapport.rendre()

    assert "recherche web" in rendu, "ce qui manque ne disparait pas du tableau"
    assert "UNKNOWN" in rendu
    assert "1 mesuree(s), 1 UNKNOWN" in rendu
    assert len(rapport.manquantes) == 1


def test_un_rapport_vide_le_dit():
    assert Rapport().rendre() == "Aucune scene declaree."


def test_le_resume_d_une_campagne_sans_mesure_est_none():
    manquantes = [non_lancee("recherche web", Voie.RECHERCHE, "hors ligne")]

    assert resume_chiffre(manquantes) is None, "zero donnerait un chiffre a montrer"


def test_le_resume_ignore_les_scenes_non_mesurees():
    mesures = [
        Mesure(nom="a", voie=Voie.LEGERE, etat=ETAT_MESURE, secondes=2.0),
        Mesure(nom="b", voie=Voie.LEGERE, etat=ETAT_MESURE, secondes=4.0),
        non_lancee("c", Voie.RECHERCHE, "hors ligne"),
    ]

    assert resume_chiffre(mesures) == 3.0
