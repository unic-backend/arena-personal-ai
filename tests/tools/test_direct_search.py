"""Recherche web : sort réellement sur Internet, donc marquée `integration`."""
import pytest

from tools.search.web_search_tool import WebSearchTool


@pytest.mark.integration
def test_une_recherche_renvoie_des_resultats_exploitables():
    resultats = WebSearchTool().search("actualites Senegal tech innovation", max_results=3)

    if not resultats:
        pytest.skip("Aucun résultat : moteur de recherche inaccessible depuis cette machine.")
    assert all({"title", "href", "body"} <= set(r) for r in resultats)


def test_une_recherche_qui_echoue_renvoie_une_liste_vide_pas_une_exception(monkeypatch):
    """Hors ligne, l'outil doit rendre la main, pas faire tomber l'agent qui l'appelle."""
    outil = WebSearchTool()
    monkeypatch.setattr(
        "builtins.__import__",
        lambda nom, *a, **k: (_ for _ in ()).throw(ImportError("ddgs indisponible"))
        if nom == "ddgs" else __import__(nom, *a, **k),
    )

    assert outil.search("peu importe") == []
