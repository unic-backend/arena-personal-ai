"""Instruction système d'ARENA : ce qu'elle affirme, et ce qu'elle n'affirme plus.

Elle contenait trois valeurs figées dans le code — l'année, le président et le
premier ministre du Sénégal. Une valeur figée devient fausse sans que rien ne le
signale, et un modèle la répète avec l'assurance d'un fait vérifié.
"""
from datetime import date

import pytest

from apps.backend import main, prompts

# Ce que la version précédente affirmait en dur.
AFFIRMATIONS_RETIREES = [
    "FAITS OFFICIELS",
    "Bassirou Diomaye Faye",
    "Ousmane Sonko",
    "Année actuelle",
    "Annee actuelle",
]


@pytest.fixture
def sans_fait_enregistre(monkeypatch):
    """Mémoire vide, hormis le propriétaire."""
    monkeypatch.setattr(prompts.memory, "get_fact", lambda cle: "Saer" if cle == "owner" else None)


@pytest.fixture
def date_fixee(monkeypatch):
    def _fixer(annee, mois, jour):
        monkeypatch.setattr(prompts, "date_du_jour", lambda: date(annee, mois, jour))
    return _fixer


# --- Ce qui a disparu ----------------------------------------------------------

@pytest.mark.parametrize("affirmation", AFFIRMATIONS_RETIREES)
def test_aucun_fait_date_n_est_ecrit_en_dur(sans_fait_enregistre, affirmation):
    assert affirmation not in prompts.get_arena_system_prompt()


def test_le_code_source_ne_contient_plus_ces_valeurs():
    """Le garde-fou porte aussi sur le fichier : les retirer du prompt ne suffit pas."""
    source = (main.BASE_DIR / "apps" / "backend" / "prompts.py").read_text(encoding="utf-8")
    ligne_de_code = [
        ligne for ligne in source.splitlines()
        if "Bassirou" in ligne or "Ousmane Sonko" in ligne
    ]
    # Seule la docstring qui explique le retrait peut mentionner le sujet.
    assert ligne_de_code == []


# --- Ce qui remplace -----------------------------------------------------------

def test_la_date_est_lue_sur_la_machine_pas_ecrite(sans_fait_enregistre, date_fixee):
    date_fixee(2030, 3, 15)

    prompt = prompts.get_arena_system_prompt()

    assert "15/03/2030" in prompt
    assert "2026" not in prompt


def test_la_date_reelle_apparait_par_defaut(sans_fait_enregistre):
    prompt = prompts.get_arena_system_prompt()

    assert date.today().strftime("%d/%m/%Y") in prompt


def test_le_modele_est_prevenu_que_la_date_ne_suffit_pas(sans_fait_enregistre):
    prompt = prompts.get_arena_system_prompt()

    assert "ne te donne aucune connaissance des evenements recents" in prompt
    assert "ne reponds pas" in prompt
    assert "verifier sur le web" in prompt


def test_le_proprietaire_est_nomme(sans_fait_enregistre):
    assert "Saer" in prompts.get_arena_system_prompt()


# --- Faits enregistrés par le propriétaire -------------------------------------

def test_un_fait_absent_n_apparait_pas(sans_fait_enregistre):
    prompt = prompts.get_arena_system_prompt()

    assert "President de la Republique" not in prompt
    assert "Faits enregistres" not in prompt


def test_un_fait_enregistre_apparait_avec_sa_reserve(monkeypatch):
    valeurs = {"owner": "Saer", "president": "Une personne nommee par le proprietaire"}
    monkeypatch.setattr(prompts.memory, "get_fact", lambda cle: valeurs.get(cle))

    prompt = prompts.get_arena_system_prompt()

    assert "Une personne nommee par le proprietaire" in prompt
    assert "ils peuvent avoir change depuis" in prompt


def test_seuls_les_faits_reellement_enregistres_sont_listes(monkeypatch):
    valeurs = {"owner": "Saer", "premier_ministre": "Valeur enregistree"}
    monkeypatch.setattr(prompts.memory, "get_fact", lambda cle: valeurs.get(cle))

    prompt = prompts.get_arena_system_prompt()

    assert "Premier ministre" in prompt
    assert "President de la Republique" not in prompt
