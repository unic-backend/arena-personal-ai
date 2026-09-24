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
