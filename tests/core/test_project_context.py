import pytest

from core.context import projet


@pytest.fixture
def memoire(tmp_path, monkeypatch):
    for nom in {*projet.TOUJOURS, "ARCHITECTURE.md", "DEPENDENCIES.md", "DECISIONS.md", "COMPLETED_SYSTEMS.md", "CHANGELOG.md"}:
        (tmp_path / nom).write_text(f"contenu {nom}", encoding="utf-8")
    monkeypatch.setattr(projet, "MEMOIRE_PROJET", tmp_path)
    return tmp_path

def test_contexte_minimal_ne_charge_pas_tout(memoire):
    contexte = projet.charger_contexte_projet("corriger la couleur du bouton")
    assert contexte.fichiers == projet.TOUJOURS
    assert "DECISIONS.md" not in contexte.contenu

def test_architecture_charge_les_details_pertinents(memoire):
    contexte = projet.charger_contexte_projet("integrer un agent MCP dans l'architecture")
    assert "ARCHITECTURE.md" in contexte.fichiers
    assert "DEPENDENCIES.md" in contexte.fichiers
    assert "CHANGELOG.md" not in contexte.fichiers

def test_budget_est_strict(memoire):
    contexte = projet.charger_contexte_projet("architecture", budget_caracteres=25)
    assert contexte.caracteres <= 25
    assert contexte.tronque is True

def test_budget_invalide_est_refuse():
    with pytest.raises(ValueError):
        projet.charger_contexte_projet("test", budget_caracteres=0)


def test_recherche_projet_retrouve_une_decision_avec_provenance(memoire):
    (memoire / "DECISIONS.md").write_text(
        "# Decisions\n## Stockage\nUtiliser SQLite pour le journal des actions.\n"
        "## Video\nWanGP reste un service externe.",
        encoding="utf-8",
    )
    resultats = projet.rechercher_contexte_projet("quel stockage SQLite pour le journal ?")
    assert resultats
    assert resultats[0].fichier == "DECISIONS.md"
    assert resultats[0].titre == "Stockage"
    assert "SQLite" in resultats[0].contenu


def test_resolution_combine_gouvernance_et_recherche_sans_doublon(memoire):
    (memoire / "DECISIONS.md").write_text(
        "# Decisions\n## Connecteurs\nUn service tiers reste derriere un connecteur.",
        encoding="utf-8",
    )
    resolution = projet.resoudre_contexte_projet(
        "integrer un connector en respectant la decision existante",
        budget_caracteres=10_000,
    )
    cles = [(entree.fichier, entree.titre) for entree in resolution.entrees]
    assert len(cles) == len(set(cles))
    assert any(fichier == "DECISIONS.md" for fichier, _ in cles)
    assert any(fichier == "ARCHITECTURE.md" for fichier, _ in cles)


def test_resolution_respecte_un_budget_strict(memoire):
    resolution = projet.resoudre_contexte_projet("architecture", budget_caracteres=10)
    assert resolution.caracteres <= 10
    assert resolution.tronque is True


def test_recherche_vide_ne_fabrique_pas_de_contexte(memoire):
    assert projet.rechercher_contexte_projet("zyxwv introuvable") == ()
