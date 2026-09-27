"""Ce qui sort de la synthese web est relu contre ce qui y est entre (DEC-0150).

Nuit du 26 au 27/09/2026 : six PR ont resserre ce qui ENTRE dans la synthese
(sujet, evenement, extraction). Rien ne relisait ce qui en SORT, et la
synthese pouvait consulter un collegue — qui repond de sa memoire, pas du web.
"""
from agents.fresh_info.fresh_info_agent import FreshInfoAgent
from core.agent.base_agent import BaseAgent
from core.agent.capacites import RegistreCapacites
from core.agent.verification_synthese import elements_sans_source

#: La fiche de match reelle de la production (PR #350), reduite a l'essentiel.
FICHE = ("LaLiga - 19 septembre 2026\nSevilla 1-3 Barcelona\n"
         "Y. Fofana (19')\nRaphinha (22', 52', 69')\nStade Ramon Sanchez-Pizjuan")
QUESTION = "Qui sont les buteurs du match Séville Barcelone 3-1 ?"


class _Recherche:
    def search(self, query, max_results=5, recent=False):
        return [{"title": "Sevilla - Barcelona", "href": "https://foot.test/match", "body": ""}]


class _Lecture:
    async def fetch(self, url):
        return {"status": "FETCHED", "url": url, "title": "Sevilla - Barcelona",
                "text": FICHE, "truncated": False}


class _Modele:
    def __init__(self, reponse):
        self.reponse = reponse
        self.appels = []

    async def generate(self, prompt, system_prompt=None, **options):
        self.appels.append({"prompt": prompt, "system_prompt": system_prompt})
        return self.reponse


def _agent(reponse):
    modele = _Modele(reponse)
    return FreshInfoAgent(provider=modele, search_tool=_Recherche(), fetcher=_Lecture()), modele


# --- Le controle lui-meme ----------------------------------------------------

def test_un_buteur_invente_et_sa_minute_sont_signales():
    reponse = ("Le FC Barcelone a gagné 3-1 à Séville [1]. Buteurs : Raphinha "
               "(22', 52') et Lewandowski (80') [1].")

    assert elements_sans_source(reponse, [QUESTION, FICHE]) == ["Lewandowski", "80"]


def test_une_reponse_fidele_ne_declenche_rien():
    """Noms traduits (Séville/Sevilla), score dans l'autre sens, date au
    format francais, citations et debut de phrase courant : rien a signaler."""
    reponse = ("Selon la source [1], Barcelone a battu Séville 3-1 le 19/09/2026. "
               "Les buteurs : Raphinha (22', 52', 69') pour Barcelone et "
               "Y. Fofana (19') pour Séville [1].")

    assert elements_sans_source(reponse, [QUESTION, FICHE]) == []


def test_un_score_different_est_signale_meme_inverse_dans_la_source():
    assert elements_sans_source("Score final : 2-1 pour Barcelone [1].",
                                [QUESTION, FICHE]) == ["2-1"]


# --- Dans l'agent -------------------------------------------------------------

async def test_la_reponse_web_porte_le_signalement_sans_etre_reecrite():
    inventee = "Buteurs : Raphinha (22') et Lewandowski (80') [1]."
    agent, _ = _agent(inventee)

    resultat = await agent.run(QUESTION)

    assert resultat["response"].startswith(inventee), "la reponse n'est jamais reecrite"
    assert "Verification automatique" in resultat["response"]
    assert resultat["sans_source"] == ["Lewandowski", "80"]


async def test_une_reponse_web_fidele_reste_telle_quelle():
    fidele = "Raphinha (22', 52', 69') et Y. Fofana (19') [1]."
    agent, _ = _agent(fidele)

    resultat = await agent.run(QUESTION)

    assert resultat["response"] == fidele
    assert resultat["sans_source"] == []


async def test_la_synthese_web_ne_consulte_aucun_collegue():
    """Avec toute une equipe inscrite, la synthese n'en recoit meme pas la
    consigne : un collegue repondrait de sa memoire, pas du web."""
    appels = []

    class _Collegue(BaseAgent):
        async def run(self, user_input, context=None):
            appels.append(user_input)
            return {"status": "success", "response": "Lewandowski a marque"}

    agent, modele = _agent("Raphinha (22') [1].")
    registre = RegistreCapacites()
    registre.enregistrer_agent(agent)
    registre.enregistrer_agent(_Collegue("RechercheAgent", "recherche", _Modele("ok")))

    await agent.run(QUESTION)

    synthese = modele.appels[-1]
    assert "Tu fais partie d'une equipe" not in (synthese["system_prompt"] or "")
    assert "[[COLLEGUE" not in (synthese["system_prompt"] or "")
    assert appels == []
