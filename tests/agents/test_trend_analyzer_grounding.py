"""La synthese de tendances s'en tient aux resultats web (DEC-0159).

Mesure du 28/09/2026 : pour « idees de videos droles », la recherche rend
quatre pages TikTok « discover » presque vides ; la consigne demandait
« 3 tendances » sans exiger de source, la synthese pouvait consulter un
collegue, et rien ne relisait la reponse.
"""
from agents.trend_analyzer.trend_analyzer_agent import TrendAnalyzerAgent
from core.agent.base_agent import BaseAgent
from core.agent.capacites import RegistreCapacites

RESULTATS = [
    {"title": "Senegal Comedy | TikTok", "href": "https://www.tiktok.com/discover/senegal-comedy",
     "body": "Sketchs de Kouthia et parodies de lutte."},
]


class _Recherche:
    def search(self, query, max_results=4, recent=False):
        return RESULTATS


class _Modele:
    def __init__(self, reponse):
        self.reponse = reponse
        self.appels = []

    async def generate(self, prompt, system_prompt=None, **options):
        self.appels.append({"prompt": prompt, "system_prompt": system_prompt})
        return self.reponse


def _agent(reponse):
    modele = _Modele(reponse)
    agent = TrendAnalyzerAgent(provider=modele)
    agent.search_tool = _Recherche()
    return agent, modele


async def test_la_consigne_exige_une_source_par_tendance():
    agent, modele = _agent("Les parodies de lutte [1].")

    resultat = await agent.run("idées de vidéos drôles")

    consigne = modele.appels[-1]["prompt"]
    assert "[1] Senegal Comedy" in consigne
    assert "N'ajoute aucun chiffre, nom" in consigne
    assert resultat["sources"] == [{"title": "Senegal Comedy | TikTok",
                                    "url": "https://www.tiktok.com/discover/senegal-comedy"}]


async def test_une_tendance_inventee_est_signalee_sans_reecrire():
    inventee = "Le défi #DakarDance de Wally Seck cumule 12 millions de vues."
    agent, _ = _agent(inventee)

    resultat = await agent.run("idées de vidéos drôles")

    assert resultat["response"].startswith(inventee)
    assert "Verification automatique" in resultat["response"]
    assert "Wally" in " ".join(resultat["sans_source"])


async def test_une_synthese_fidele_reste_telle_quelle():
    fidele = "Les sketchs de Kouthia et les parodies de lutte [1]."
    agent, _ = _agent(fidele)

    resultat = await agent.run("idées de vidéos drôles")

    assert resultat["response"] == fidele
    assert resultat["sans_source"] == []


async def test_la_synthese_ne_consulte_aucun_collegue():
    appels = []

    class _Collegue(BaseAgent):
        async def run(self, user_input, context=None):
            appels.append(user_input)
            return {"status": "success", "response": "tendance de memoire"}

    agent, modele = _agent("Les parodies de lutte [1].")
    registre = RegistreCapacites()
    registre.enregistrer_agent(agent)
    registre.enregistrer_agent(_Collegue("RechercheAgent", "recherche", _Modele("ok")))

    await agent.run("idées de vidéos drôles")

    assert "[[COLLEGUE" not in (modele.appels[-1]["system_prompt"] or "")
    assert appels == []
