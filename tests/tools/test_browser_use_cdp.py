"""`BrowserUseTool.run_task(cdp_url=...)` : connecte browser_use à un
navigateur DÉJÀ lancé (Lightpanda, ou tout serveur CDP) au lieu d'en
démarrer un nouveau. Vérifié directement contre les vraies classes
`browser_use` installées ici (`browser_use==0.13.10`) — jamais un double
indépendant qui pourrait diverger de la vraie API.
"""
import pytest

from tools.browser.browser_use_tool import BrowserUseTool

pytest.importorskip("browser_use", reason="browser-use n'est pas installé.")
pytest.importorskip("langchain_openai", reason="langchain-openai n'est pas installé.")


class FausseHistorique:
    def final_result(self):
        return "titre trouvé"


class FauxAgent:
    """Remplace `browser_use.Agent` — note la session reçue, ne lance rien."""

    dernier_browser_session = None

    def __init__(self, task, llm, browser_session=None, **kw):
        self.task = task
        FauxAgent.dernier_browser_session = browser_session

    async def run(self):
        return FausseHistorique()


@pytest.fixture(autouse=True)
def _brancher_faux_agent(monkeypatch):
    import browser_use

    FauxAgent.dernier_browser_session = None
    monkeypatch.setattr(browser_use, "Agent", FauxAgent)


async def test_sans_cdp_url_aucune_session_n_est_construite():
    resultat = await BrowserUseTool().run_task("visite https://example.com")

    assert resultat["status"] == "success"
    assert resultat["moteur"] == "chromium"
    assert FauxAgent.dernier_browser_session is None


async def test_avec_cdp_url_une_session_pointe_dessus():
    resultat = await BrowserUseTool().run_task(
        "visite https://example.com", cdp_url="ws://127.0.0.1:9222")

    assert resultat["status"] == "success"
    assert resultat["moteur"] == "lightpanda"
    session = FauxAgent.dernier_browser_session
    assert session is not None
    assert session.cdp_url == "ws://127.0.0.1:9222"


async def test_une_erreur_porte_quand_meme_le_moteur_tente():
    class AgentQuiLeve:
        def __init__(self, *a, **kw):
            pass

        async def run(self):
            raise RuntimeError("connexion refusée")

    import browser_use

    module_agent_backup = browser_use.Agent
    browser_use.Agent = AgentQuiLeve
    try:
        resultat = await BrowserUseTool().run_task(
            "visite https://example.com", cdp_url="ws://127.0.0.1:9222")
    finally:
        browser_use.Agent = module_agent_backup

    assert resultat["status"] == "error"
    assert resultat["moteur"] == "lightpanda"
