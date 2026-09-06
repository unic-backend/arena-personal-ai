"""`BrowserAgent` : la navigation passe par le registre/les permissions,
jamais `BrowserUseTool` en direct (DEC-0059 — le défaut corrigé)."""
from agents.browser.browser_agent import BrowserAgent


class ModeleDouble:
    async def generate(self, prompt: str, **kw) -> str:
        return "réponse"

    async def is_available(self) -> bool:
        return True


class RegistreDouble:
    def __init__(self, reponse=None):
        self.appels = []
        self._reponse = reponse or {
            "statut": "SUCCESS", "message": "Navigation terminée (Chromium (Playwright)) : titre trouvé",
            "detail": {"moteur": "chromium", "resultat": "titre trouvé", "repli": False},
        }

    def executer(self, nom, capacite, **parametres):
        self.appels.append((nom, capacite, parametres))
        return self._reponse


class TestSansRegistre:
    async def test_sans_registre_echoue_honnetement_jamais_de_navigation_directe(self):
        agent = BrowserAgent(provider=ModeleDouble(), registre=None)

        resultat = await agent.run("visite https://example.com")

        assert resultat["status"] == "error"
        assert "registre" in resultat["response"].lower()


class TestAvecRegistre:
    async def test_la_navigation_passe_par_le_registre(self):
        registre = RegistreDouble()
        agent = BrowserAgent(provider=ModeleDouble(), registre=registre)

        resultat = await agent.run("visite https://example.com et lis le titre")

        assert resultat["status"] == "success"
        assert resultat["moteur"] == "chromium"
        assert registre.appels == [
            ("browser", "naviguer", {"tache": "visite https://example.com et lis le titre"})]

    def test_jamais_browserusetool_appele_en_direct(self):
        """Le défaut corrigé : plus aucun import direct de BrowserUseTool
        dans l'agent — tout passe par le registre."""
        import agents.browser.browser_agent as module
        with open(module.__file__, encoding="utf-8") as f:
            contenu = f.read()
        assert "import BrowserUseTool" not in contenu
        assert "self.browser_tool" not in contenu

    async def test_un_echec_du_connecteur_est_rapporte(self):
        registre = RegistreDouble(reponse={
            "statut": "FAILED", "message": "Navigation impossible : chromium introuvable",
        })
        agent = BrowserAgent(provider=ModeleDouble(), registre=registre)

        resultat = await agent.run("visite https://example.com")

        assert resultat["status"] == "error"
        assert "chromium introuvable" in resultat["response"]

    async def test_une_confirmation_en_attente_n_est_pas_un_echec(self):
        registre = RegistreDouble(reponse={
            "statut": "NEEDS_CONFIRMATION", "message": "Prêt : navigation. Risque MEDIUM.",
        })
        agent = BrowserAgent(provider=ModeleDouble(), registre=registre)

        resultat = await agent.run("visite https://example.com")

        assert resultat["status"] == "success"
        assert "attente" in resultat["response"].lower() or "confirmation" in resultat["response"].lower() or "Prêt" in resultat["response"]
