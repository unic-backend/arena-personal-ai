"""La mentalité d'Usman : ce qu'il s'interdit avant de chercher à être utile.

Sept règles, et **chacune vient d'un défaut réel de cette plateforme** — pas
d'une bonne intention générale. C'est ce qui les rend défendables : on peut
nommer le jour où l'absence de la règle a coûté quelque chose au propriétaire.

Ce que ce fichier mesure, et ce qu'il ne mesure pas — la distinction est
importante et elle est écrite ici plutôt que supposée :

- **Mesuré** : les sept règles sont présentes, une seule fois, et arrivent
  jusqu'aux trois chemins de réponse. C'est structurel, donc vérifiable sans
  modèle.
- **Non mesuré** : que le modèle les *suive*. Aucun modèle ne tourne en CI
  (`docs/DECISIONS.md`, DEC-0022 : le modèle tourne chez le propriétaire).
  Prétendre le contraire serait exactement la règle 2.

Un test qui vérifie qu'une instruction existe ne prouve pas qu'elle change un
comportement. Il prouve seulement qu'elle ne peut pas disparaître en silence —
et c'est déjà ce qui manquait.
"""
from pathlib import Path

import pytest

from apps.backend.prompts import (
    DISCIPLINE,
    get_arena_system_prompt,
    prompt_avec_methode,
)

RACINE = Path(__file__).resolve().parent.parent

#: Ce que chaque règle interdit, et le mot qui la rend reconnaissable dans le
#: prompt. Écrit ici plutôt que recopié du prompt : si les deux divergent, le
#: test tombe — c'est le but.
REGLES = {
    "1": "verifie",
    "2": "capacite",
    "3": "ratee",
    "4": "inconnu",
    "5": "plausible",
    "6": "corrige",
    "7": "prevu",
}


@pytest.fixture(scope="module")
def prompt():
    return get_arena_system_prompt()


@pytest.mark.parametrize("numero,mot", list(REGLES.items()))
def test_chaque_regle_est_dans_le_prompt(prompt, numero, mot):
    lignes = prompt.splitlines()
    depart = [i for i, x in enumerate(lignes) if x.strip().startswith(f"{numero}.")]

    assert depart, f"la regle {numero} a disparu du prompt"
    # Le bloc va de la ligne numerotee a la suivante. Un `split("6.")` sur tout
    # le prompt tombait d'abord sur la DATE (« 03/09/2026. ») et mesurait le
    # mauvais morceau — un test qui passe pour de mauvaises raisons est pire
    # qu'un test absent.
    debut = depart[0]
    suivante = [i for i in range(debut + 1, len(lignes))
                if lignes[i].strip()[:2] in {f"{n}." for n in "123456789"}]
    bloc = "\n".join(lignes[debut:(suivante[0] if suivante else len(lignes))]).lower()
    assert mot in bloc, f"la regle {numero} ne parle plus de « {mot} »"


def test_les_sept_regles_sont_la_et_pas_une_de_plus(prompt):
    """Une huitième règle ajoutée sans mesure diluerait les sept autres.

    La discipline tient parce que chaque ligne peut nommer le jour où son
    absence a coûté quelque chose. Une règle sans mesure est une bonne manière,
    et les bonnes manières s'accumulent jusqu'à ce que plus personne ne les lise.
    """
    numeros = [x.strip()[0] for x in prompt.splitlines()
               if x.strip()[:2] in {f"{n}." for n in "123456789"}]

    assert numeros == list("1234567")


def test_la_discipline_arrive_jusquau_prompt_compose():
    """**La garde qui compte.** Trois chemins de réponse composent le prompt
    (PWA, `/api/chat`, passerelle OpenAI) et passent tous par
    `prompt_avec_methode`. Une discipline présente dans le prompt de base mais
    perdue à la composition ne serait suivie nulle part.
    """
    compose = prompt_avec_methode("comment poser du BA13 ?", "PLAQUISTE")

    for numero in REGLES:
        assert f"{numero}." in compose, (
            f"la regle {numero} n'arrive pas jusqu'au prompt reellement envoye")


def test_la_methode_dun_specialiste_ne_peut_pas_effacer_la_discipline():
    """La méthode vient APRÈS les règles de la plateforme : elle précise
    comment travailler, elle n'efface rien de ce qu'ARENA s'interdit."""
    base = get_arena_system_prompt()
    compose = prompt_avec_methode("fais-moi un devis", "PLAQUISTE")

    assert compose.startswith(base), (
        "la methode passe avant la discipline : elle pourrait la contredire")


def test_chaque_regle_porte_sa_mesure_dans_le_code():
    """Une règle dont on ne peut pas nommer la mesure se fait retirer par le
    prochain qui la trouve moralisatrice — et il aura raison.

    Le commentaire au-dessus de `DISCIPLINE` doit citer des dates réelles.
    """
    source = (RACINE / "apps" / "backend" / "prompts.py").read_text(encoding="utf-8")
    entete = source.split("DISCIPLINE = [")[0][-2000:]

    assert "03/09/2026" in entete, "la discipline ne cite aucune mesure datee"
    assert entete.count("Regle") >= 4, (
        "moins de quatre regles nomment le defaut qui les justifie")


def test_le_prompt_ne_promet_pas_ce_quil_ne_sait_pas_faire(prompt):
    """La règle 2 s'applique au prompt lui-même.

    Un prompt qui annoncerait « je peux tout faire » enseignerait au modèle
    exactement ce que la règle 2 lui interdit.
    """
    interdits = ("je peux tout", "aucune limite", "toujours capable",
                 "je sais tout", "illimite")
    minuscule = prompt.lower()

    for phrase in interdits:
        assert phrase not in minuscule, f"le prompt promet « {phrase} »"


def test_la_discipline_survit_a_labsence_de_faits_enregistres(monkeypatch):
    """Les faits du propriétaire sont optionnels ; la discipline ne l'est pas.

    Sans cette garde, un propriétaire dont la mémoire est vide recevrait un
    modèle sans aucune règle — et c'est le cas d'une machine neuve.
    """
    from apps.backend import prompts

    monkeypatch.setattr(prompts.memory, "get_fact", lambda *a, **k: None)
    prompt = prompts.get_arena_system_prompt()

    for numero in REGLES:
        assert f"{numero}." in prompt


def test_la_liste_est_partagee_et_non_recopiee():
    """`DISCIPLINE` est composée depuis une seule liste. Deux copies — une dans
    le prompt, une dans un test — divergeraient au premier changement."""
    assert isinstance(DISCIPLINE, list)
    assert all(isinstance(ligne, str) for ligne in DISCIPLINE)

    prompt = get_arena_system_prompt()
    for ligne in DISCIPLINE:
        assert ligne in prompt
