"""`UiGenerationAgent` — decrit -> genere -> valide -> artefact (DEC-0050).

Le connecteur (`core/connectors/ui_generate.py`) a son propre test avec le
vrai code de validation/ecriture ; celui-ci verifie uniquement que l'agent
appelle le modele, extrait le code correctement, et delegue au registre —
jamais un succes invente.
"""
from agents.ui.ui_agent import UiGenerationAgent
from core.actions.resultat import echec, succes


class ModeleDouble:
    def __init__(self, reponse="```html\n<!doctype html><body>Bonjour</body>\n```",
                disponible=True, erreur=None):
        self._reponse = reponse
        self._disponible = disponible
        self._erreur = erreur
        self.prompts = []

    async def is_available(self) -> bool:
        return self._disponible

    async def generate(self, prompt, **kw):
        self.prompts.append(prompt)
        if self._erreur is not None:
            raise self._erreur
        return self._reponse


class RegistreDouble:
    def __init__(self, reponse=None):
        self.appels = []
        self._reponse = reponse or succes(
            action="generer", cible="ui_generate", message="Interface ecrite",
            preuve="ui-x.html")

    def executer(self, connecteur, capacite, **parametres):
        self.appels.append({"connecteur": connecteur, "capacite": capacite,
                            "parametres": parametres})
        return self._reponse


class TestUiGenerationAgent:
    async def test_genere_et_delegue_au_registre(self):
        modele = ModeleDouble()
        registre = RegistreDouble()
        agent = UiGenerationAgent(provider=modele, registre=registre)

        resultat = await agent.run("un dashboard moderne pour une entreprise")

        assert resultat["status"] == "success"
        assert len(registre.appels) == 1
        appel = registre.appels[0]
        assert appel["connecteur"] == "ui_generate"
        assert appel["capacite"] == "generer"
        assert "<!doctype html>" in appel["parametres"]["code"]
        assert appel["parametres"]["framework"] == "html"

    async def test_framework_demande_est_transmis(self):
        modele = ModeleDouble(reponse="```react\nfunction App(){return <div/>}\n```")
        registre = RegistreDouble()
        agent = UiGenerationAgent(provider=modele, registre=registre)

        await agent.run("un formulaire de contact", context={"framework": "react"})

        assert registre.appels[0]["parametres"]["framework"] == "react"

    async def test_code_existant_est_transmis_au_modele_pour_iteration(self):
        modele = ModeleDouble()
        registre = RegistreDouble()
        agent = UiGenerationAgent(provider=modele, registre=registre)

        await agent.run("change le bouton en bleu",
                        context={"existant": "<!doctype html><button>x</button>"})

        assert any("<!doctype html><button>x</button>" in p for p in modele.prompts)

    async def test_sans_bloc_de_code_dans_la_reponse_echoue_honnetement(self):
        modele = ModeleDouble(reponse="Je ne peux pas generer ca, desole.")
        registre = RegistreDouble()
        agent = UiGenerationAgent(provider=modele, registre=registre)

        resultat = await agent.run("un dashboard")

        assert resultat["status"] == "error"
        assert registre.appels == []

    async def test_sans_modele_disponible_rien_n_est_tente(self):
        modele = ModeleDouble(disponible=False)
        registre = RegistreDouble()
        agent = UiGenerationAgent(provider=modele, registre=registre)

        resultat = await agent.run("un dashboard")

        assert resultat["status"] == "warning"
        assert registre.appels == []

    async def test_sans_registre_echoue_honnetement(self):
        modele = ModeleDouble()
        agent = UiGenerationAgent(provider=modele, registre=None)

        resultat = await agent.run("un dashboard")

        assert resultat["status"] == "error"

    async def test_le_modele_injoignable_echoue_honnetement(self):
        modele = ModeleDouble(erreur=ConnectionError("modele hors ligne"))
        registre = RegistreDouble()
        agent = UiGenerationAgent(provider=modele, registre=registre)

        resultat = await agent.run("un dashboard")

        assert resultat["status"] == "error"
        assert registre.appels == []

    async def test_un_refus_du_connecteur_se_lit_comme_une_erreur(self):
        modele = ModeleDouble()
        registre = RegistreDouble(reponse=echec(
            action="generer", cible="ui_generate",
            message="Ecriture refusee : script externe refuse"))
        agent = UiGenerationAgent(provider=modele, registre=registre)

        resultat = await agent.run("un dashboard")

        assert resultat["status"] == "error"
        assert "refusee" in resultat["response"]
