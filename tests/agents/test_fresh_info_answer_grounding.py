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


# --- Les barrieres de pertinence reconnaissent une source dans une autre langue

async def test_un_suivi_accepte_une_source_anglaise_du_bon_match():
    """Mesure du 27/09/2026 sur les barrieres de #347/#349 : l'ancre francaise
    « barcelone » et l'indice « séville » ne reconnaissaient pas une page qui
    ecrit « Barcelona » et « Sevilla ». Le suivi « Qui sont les buteurs ? »
    etait refuse comme hors sujet alors que la source etait la bonne."""

    class _RechercheEn:
        def search(self, query, max_results=5, recent=False):
            return [{"title": "Sevilla 1-3 Barcelona", "href": "https://espn.test/m", "body": ""}]

    class _LectureEn:
        async def fetch(self, url):
            return {"status": "FETCHED", "url": url, "title": "Sevilla 1-3 Barcelona",
                    "text": "LaLiga. Sevilla 1-3 Barcelona. Goals: Y. Fofana 19', "
                            "Raphinha 22', 52', 69'.", "truncated": False}

    class _ModeleSuivi:
        async def generate(self, prompt, system_prompt=None, **options):
            if "Réécris" in prompt:
                return "Qui sont les buteurs du dernier match du FC Barcelone ?"
            return "Raphinha (22', 52', 69') et Y. Fofana (19') [1]."

    agent = FreshInfoAgent(provider=_ModeleSuivi(), search_tool=_RechercheEn(),
                           fetcher=_LectureEn())
    historique = [
        {"role": "user", "content": "Quel a été le dernier match du FC Barcelone ?"},
        {"role": "assistant", "content": "Le FC Barcelone a gagné 3-1 à Séville [1]."},
    ]

    resultat = await agent.run("Qui sont les buteurs ?",
                               context={"history": historique, "history_authoritative": True})

    assert resultat["status"] == "success", resultat["response"]
    assert resultat["response"].startswith("Raphinha")


def test_une_ancre_ne_reconnait_pas_un_autre_mot():
    from core.agent.verification_synthese import terme_present

    assert terme_present("barcelone", "Sevilla 1-3 Barcelona")
    assert terme_present("séville", "Sevilla 1-3 Barcelona")
    assert not terme_present("barcelone", "Hockey : les Canadiens battent Boston")
    assert not terme_present("real", "Realite virtuelle")
    assert terme_present("3-1", "score 3-1") and not terme_present("3-1", "score 2-1")


def test_la_fiche_de_match_d_une_page_anglaise_garde_ses_buteurs():
    """Meme defaut dans l'extraction de #350 : les entites de la question
    (« Séville », « Barcelone ») ne reperaient pas la fiche d'une page qui
    ecrit « Sevilla » et « Barcelona » ; le classement ligne a ligne
    supprimait alors la ligne du buteur, qui ne partage aucun mot."""
    remplissage = "\n".join(f"Actualite du club numero {i} sans rapport." for i in range(40))
    page = (f"{remplissage}\nSevilla\n1 - 3\nBarcelona\nY. Fofana (19')\n"
            f"Raphinha (22', 52', 69')\n{remplissage}")

    extrait = FreshInfoAgent.extraire_pertinent(
        page, "Qui sont les buteurs du match Séville Barcelone ?", 400)

    assert "Y. Fofana" in extrait and "Raphinha" in extrait
