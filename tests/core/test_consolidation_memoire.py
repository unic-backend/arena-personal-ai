"""La consolidation : dire une chose une fois, sans en perdre aucune.

Le test que la phase doit passer est
`test_une_supposition_ne_rejoint_jamais_un_fait` : deux souvenirs au contenu
identique mais de natures differentes restent deux souvenirs. Les regrouper
ferait d'une deduction d'ARENA une chose que le proprietaire a dite.
"""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from core.memory.consolidation import (
    empreinte,
    grouper,
    resumer,
    taille,
)
from core.memory.personnelle import MemoirePersonnelle, Nature, TypeSouvenir
from core.memory.recuperation import MARQUE_SUPPOSITION

MAINTENANT = datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc)
PHRASE = "Plafond BA13 de 40 m2 pose a Medina."


@pytest.fixture
def memoire(tmp_path):
    return MemoirePersonnelle(db_path=str(tmp_path / "memoire.db"))


@pytest.fixture
def retenir(memoire):
    """Retient un souvenir et lui donne l'age demande."""
    def _retenir(contenu, jours=0, **remplacements):
        valeurs = {
            "type": TypeSouvenir.EPISODIQUE, "nature": Nature.FAIT,
            "source": "devis UC-2026-0804-FG2",
        }
        valeurs.update(remplacements)
        souvenir = memoire.retenir(contenu=contenu, **valeurs)
        date = (MAINTENANT - timedelta(days=jours)).isoformat(timespec="seconds")
        with sqlite3.connect(memoire.db_path) as connexion:
            connexion.execute("UPDATE souvenirs SET cree_le = ? WHERE identifiant = ?",
                              (date, souvenir.identifiant))
        return memoire.lire(souvenir.identifiant)
    return _retenir


# --- Le test que la phase doit passer ------------------------------------------

def test_une_supposition_ne_rejoint_jamais_un_fait(memoire, retenir):
    # Meme contenu, meme source, meme projet : la nature est la SEULE difference.
    # Sans cette egalite partout ailleurs, le test passerait pour une autre raison
    # que celle qu'il pretend prouver.
    retenir(PHRASE, nature=Nature.FAIT, source="planning du chantier")
    retenir(PHRASE, nature=Nature.INFERENCE, source="planning du chantier")

    resume = resumer(memoire, maintenant=MAINTENANT)

    assert len(resume.groupes) == 2, "deux natures, deux souvenirs"
    natures = {groupe.nature for groupe in resume.groupes}
    assert natures == {Nature.FAIT, Nature.INFERENCE}

    rendu = resume.rendre()
    lignes_marquees = [ligne for ligne in rendu.split("\n") if MARQUE_SUPPOSITION in ligne]
    assert len(lignes_marquees) == 1, "la supposition est marquee, le fait ne l'est pas"


def test_deux_fois_la_meme_phrase_ne_font_qu_une_ligne(memoire, retenir):
    retenir(PHRASE, jours=10)
    retenir(PHRASE, jours=2)

    resume = resumer(memoire, maintenant=MAINTENANT)

    assert len(resume.groupes) == 1
    assert resume.groupes[0].occurrences == 2
    assert resume.doublons_rassembles == 1
    assert "(vu 2 fois)" in resume.rendre()
    assert resume.lus == 2, "les deux souvenirs existent toujours, rien n'est efface"


def test_le_representant_est_le_plus_ancien(memoire, retenir):
    ancien = retenir(PHRASE, jours=120)
    retenir(PHRASE, jours=1)

    resume = resumer(memoire, maintenant=MAINTENANT)

    assert resume.groupes[0].representant.identifiant == ancien.identifiant


# --- Ce qui ne se regroupe pas --------------------------------------------------

def test_deux_projets_ne_se_melangent_pas(memoire, retenir):
    retenir(PHRASE, projet="Medina")
    retenir(PHRASE, projet="Fast Group")

    resume = resumer(memoire, maintenant=MAINTENANT)

    assert len(resume.groupes) == 2


def test_deux_sources_ne_se_melangent_pas(memoire, retenir):
    retenir(PHRASE, source="devis UC-2026-0804-FG2")
    retenir(PHRASE, source="conversation du 12 aout")

    resume = resumer(memoire, maintenant=MAINTENANT)

    assert len(resume.groupes) == 2, "deux origines sont deux preuves"


def test_la_ponctuation_et_les_accents_ne_font_pas_deux_souvenirs(memoire, retenir):
    retenir("Plafond BA13 de 40 m2 pose a Medina.")
    retenir("plafond ba13 de 40 m2 pose a Médina")

    resume = resumer(memoire, maintenant=MAINTENANT)

    assert len(resume.groupes) == 1


def test_un_chiffre_different_est_un_autre_souvenir(memoire, retenir):
    retenir("Plafond BA13 de 40 m2 pose a Medina.")
    retenir("Plafond BA13 de 41 m2 pose a Medina.")

    assert empreinte("Plafond BA13 de 40 m2.") != empreinte("Plafond BA13 de 41 m2.")
    assert len(resumer(memoire, maintenant=MAINTENANT).groupes) == 2


# --- L'importance, le temps, le budget ------------------------------------------

def test_l_importance_du_groupe_est_le_maximum(memoire, retenir):
    faible = retenir(PHRASE, jours=5, importance=0.3)
    fort = retenir(PHRASE, jours=1, importance=0.9)

    groupe = grouper([faible, fort])[0]

    assert groupe.importance == 0.9
    assert groupe.occurrences == 2, "la repetition se compte, elle ne gonfle pas l'importance"


def test_un_contexte_temporaire_perime_n_est_pas_resume(memoire, retenir):
    retenir("Le client rappelle cet apres-midi.",
            nature=Nature.CONTEXTE_TEMPORAIRE, duree_heures=1)

    plus_tard = datetime.now(timezone.utc) + timedelta(hours=3)
    resume = resumer(memoire, maintenant=plus_tard)

    assert resume.groupes == []
    assert "Rien en memoire" in resume.rendre()


def test_le_budget_n_est_jamais_depasse(memoire, retenir):
    for numero in range(12):
        retenir(f"Chantier numero {numero} livre en aout.", jours=numero)

    resume = resumer(memoire, budget_caracteres=200, maintenant=MAINTENANT)

    assert taille(resume.groupes) <= 200
    assert resume.ecartes_budget > 0, "le test ne prouve rien si tout tenait deja"
    assert resume.groupes, "un budget serre garde le plus important, il ne rend pas vide"


def test_une_memoire_vide_le_dit(memoire):
    resume = resumer(memoire, projet="Medina", maintenant=MAINTENANT)

    assert resume.groupes == []
    assert resume.rendre() == "Rien en memoire sur Medina."
