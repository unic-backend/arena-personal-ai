from core.guardian.diagnostics import (
    CATEGORIE_BUG,
    CATEGORIE_DIAGNOSTIC,
    CATEGORIE_QUALITE,
    Constat,
    SortieCommande,
    diagnostiquer_bugs,
    diagnostiquer_qualite,
)
from core.guardian.file_maintenance import FileDeMaintenance
from core.guardian.gardien import _categories_non_verifiees


def test_pytest_timeout_is_not_reported_as_clean():
    constats = diagnostiquer_bugs(
        lambda _commande: SortieCommande(-1, "", "delai depasse")
    )
    assert len(constats) == 1
    assert constats[0].categorie == CATEGORIE_DIAGNOSTIC
    assert constats[0].fichier == CATEGORIE_BUG


def test_pytest_collection_error_is_not_reported_as_clean():
    constats = diagnostiquer_bugs(
        lambda _commande: SortieCommande(2, "ERROR collecting tests/test_x.py", "")
    )
    assert constats[0].categorie == CATEGORIE_DIAGNOSTIC
    assert CATEGORIE_BUG in _categories_non_verifiees(constats)


def test_ruff_tool_error_is_not_reported_as_clean():
    constats = diagnostiquer_qualite(
        lambda _commande: SortieCommande(2, "", "ruff configuration error")
    )
    assert constats[0].categorie == CATEGORIE_DIAGNOSTIC
    assert constats[0].fichier == CATEGORIE_QUALITE


def test_ruff_invalid_json_is_not_reported_as_clean():
    constats = diagnostiquer_qualite(
        lambda _commande: SortieCommande(0, "not-json", "")
    )
    assert constats[0].categorie == CATEGORIE_DIAGNOSTIC
    assert CATEGORIE_QUALITE in _categories_non_verifiees(constats)


def test_previous_finding_can_be_kept_when_its_probe_is_unavailable(tmp_path):
    file = FileDeMaintenance(str(tmp_path / "memory.db"))
    ancien = Constat(
        categorie=CATEGORIE_BUG,
        gravite="P2",
        description="test en echec : tests/test_x.py::test_x",
        fichier="tests/test_x.py",
        preuve="AssertionError",
    )
    file.enregistrer_constats([ancien])

    indisponible = diagnostiquer_bugs(
        lambda _commande: SortieCommande(-1, "", "delai depasse")
    )
    non_verifiees = _categories_non_verifiees(indisponible)

    # C'est le contrat utilisé par Gardien : une catégorie non vérifiée ne
    # peut pas être considérée comme résolue simplement parce que son ancien
    # constat est absent du résultat courant.
    assert CATEGORIE_BUG in non_verifiees
    assert file.ouvertes()[0].etat.value == "DISCOVERED"
