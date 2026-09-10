"""Navigation autonome : exige Chromium, Playwright et Ollama."""
import pytest

from tools.browser.browser_use_tool import (
    BrowserUseTool,
    _premiere_action,
    _statut_pour_action,
)


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


class TestSensitiveDataExigeAllowedDomains:
    """Mission Fuji-Web §13/§14 : `browser_use` avertit lui-meme qu'un
    identifiant fourni sans domaines restreints peut fuiter vers un site
    malveillant par injection de prompt. Ce test ne depend d'AUCUN paquet
    tiers : le refus a lieu avant le moindre import de `browser_use`."""

    async def test_refuse_sans_allowed_domains(self):
        res = await BrowserUseTool().run_task(
            "tâche", sensitive_data={"x_password": "secret-ne-jamais-voir"})

        assert res["status"] == "error"
        assert "allowed_domains" in res["error"]
        # La garantie qui compte : le secret n'apparait NULLE PART dans la
        # reponse, meme dans le message d'erreur.
        assert "secret-ne-jamais-voir" not in str(res)


class TestStatutParAction:
    """Le mappage action -> etat operationnel (mission §23) : jamais le
    raisonnement du modele, un statut concis seulement."""

    @pytest.mark.parametrize("action,attendu", [
        ("navigate", "NAVIGATING"),
        ("click", "CLICKING"),
        ("input", "TYPING"),
        ("select_dropdown", "TYPING"),
        ("upload_file", "UPLOADING"),
        ("wait", "WAITING"),
        ("extract", "READING_PAGE"),
        ("done", "COMPLETED"),
    ])
    def test_actions_connues(self, action, attendu):
        assert _statut_pour_action(action) == attendu

    def test_action_inconnue_reste_en_cours_jamais_devinee(self):
        assert _statut_pour_action("une_action_qui_n_existe_pas") == "EN_COURS"

    def test_action_absente_reste_en_cours(self):
        assert _statut_pour_action(None) == "EN_COURS"


class TestPremiereAction:
    def test_extrait_le_nom_de_la_premiere_action(self):
        class FauxeAction:
            def model_dump(self, exclude_unset=True):
                return {"click": {"uid": "3"}}

        class FauxAgentOutput:
            action = [FauxeAction()]

        assert _premiere_action(FauxAgentOutput()) == "click"

    def test_aucune_action_rend_none(self):
        class FauxAgentOutput:
            action = []

        assert _premiere_action(FauxAgentOutput()) is None
