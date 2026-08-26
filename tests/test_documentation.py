"""La documentation dit-elle encore la vérité sur le code ?

Ces tests existent parce que le défaut le plus durable relevé par les audits du
26/08/2026 n'était pas dans le code : `docs/ROADMAP.md` cochait trois livrables
qui n'existaient pas. Une case cochée à tort empêche quiconque d'y revenir.
"""
import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
DOCS = RACINE / "docs"
WORKLOG = RACINE / "documents" / "USMAN_ENGINEERING_WORKLOG.md"

# Affirmations retirées le 26/08/2026 parce qu'elles étaient fausses.
# Si l'une revient cochée, c'est que le piège a été reposé.
AFFIRMATIONS_RETIREES = [
    "[x] Bac à sable Docker actif",
    "[x] Secrets déplacés vers `.env` et renouvelés",
    "[x] Dépôt Git assaini, dépendances complètes, tests fiables",
]


def fichiers_documentation():
    yield from DOCS.glob("*.md")
    yield WORKLOG
    yield RACINE / "README.md"


def test_le_carnet_de_bord_existe():
    assert WORKLOG.exists(), "documents/USMAN_ENGINEERING_WORKLOG.md est le point d'entrée"


@pytest.mark.parametrize("affirmation", AFFIRMATIONS_RETIREES)
def test_les_affirmations_fausses_ne_reviennent_pas(affirmation):
    roadmap = (DOCS / "ROADMAP.md").read_text(encoding="utf-8")

    assert affirmation not in roadmap, (
        f"'{affirmation}' avait été cochée sans vérification. "
        "Ne la recocher qu'après avoir exécuté la vérification correspondante."
    )


def test_next_steps_ne_decrit_plus_la_phase_0():
    contenu = (DOCS / "NEXT_STEPS.md").read_text(encoding="utf-8")

    assert "Créer README.md" not in contenu
    assert (RACINE / "README.md").exists()


def test_le_rapport_de_travail_n_est_pas_duplique():
    assert not (RACINE / "RAPPORT_TRAVAIL.txt").exists(), (
        "Le rapport ne doit exister qu'une fois, dans docs/."
    )
    assert (DOCS / "RAPPORT_TRAVAIL.txt").exists()


def test_aucun_secret_en_clair_dans_la_documentation():
    """Un document qui décrit une fuite ne doit pas la reproduire.

    La valeur cherchée n'est volontairement pas écrite d'un seul tenant : ce
    fichier deviendrait sinon lui-même une fuite, et ferait échouer le scan de
    secrets à venir (T-03). Cette rechute s'est déjà produite deux fois.
    """
    motif = re.compile("arena-saer" + r"-2026")
    coupables = [
        str(f.relative_to(RACINE))
        for f in fichiers_documentation()
        if f.exists() and motif.search(f.read_text(encoding="utf-8"))
    ]

    assert coupables == [], f"valeur de clé écrite en clair dans : {coupables}"


def test_les_fichiers_cites_par_la_documentation_existent():
    """Un chemin cité entre accents graves doit correspondre à un fichier réel."""
    motif = re.compile(r"`([\w./-]+\.(?:py|yaml|yml|md|txt|toml|html|lock))`")
    ignores = {
        ".env",  # jamais versionné, par construction
        "requirements.lock.txt",
    }
    manquants = []
    for doc in fichiers_documentation():
        if not doc.exists():
            continue
        for chemin in set(motif.findall(doc.read_text(encoding="utf-8"))):
            if chemin in ignores or "/" not in chemin:
                continue
            if not (RACINE / chemin).exists():
                manquants.append(f"{doc.relative_to(RACINE)} → {chemin}")

    assert manquants == [], "chemins cités mais introuvables :\n  " + "\n  ".join(manquants)
