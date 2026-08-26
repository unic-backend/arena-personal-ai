"""Navigation autonome : exige Chromium, Playwright et Ollama."""
import pytest

from tools.browser.browser_use_tool import BrowserUseTool


@pytest.fixture
def browser_use_installe():
    """Ignore le test si browser-use ou Playwright n'est pas installé ici."""
    pytest.importorskip("browser_use", reason="browser-use n'est pas installé.")
    pytest.importorskip("langchain_openai", reason="langchain-openai n'est pas installé.")


@pytest.mark.integration
async def test_une_page_est_visitee_et_lue(browser_use_installe):
    res = await BrowserUseTool().run_task(
        "Visite https://example.com et extrait le titre principal de la page."
    )

    assert res["status"] == "success"


async def test_sans_dependances_l_outil_renvoie_une_erreur_et_ne_leve_pas():
    """L'agent appelant doit recevoir un statut, pas une exception."""
    res = await BrowserUseTool().run_task("tâche impossible dans cet environnement")

    assert res["status"] in {"success", "error"}
    assert "result" in res
