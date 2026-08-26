"""Agent d'information fraîche : chercher, lire, citer — ou refuser.

Rien ne sort sur le réseau : la recherche et la lecture sont doublées.
"""
import pytest

from agents.fresh_info.fresh_info_agent import FreshInfoAgent


def resultat(n: int) -> dict:
    return {"title": f"Titre {n}", "href": f"https://exemple.test/{n}", "body": f"resume {n}"}


SANS_VALEUR = object()   # distingue « non precise » de « volontairement vide »


def page_lue(n: int, texte=SANS_VALEUR, titre=SANS_VALEUR) -> dict:
    return {
        "status": "FETCHED",
        "url": f"https://exemple.test/{n}",
        "title": f"Page {n}" if titre is SANS_VALEUR else titre,
        "text": f"Contenu complet de la page {n}." if texte is SANS_VALEUR else texte,
        "truncated": False,
    }


def page_ratee(n: int, raison: str = "code HTTP 404") -> dict:
    return {
        "status": "FAILED", "url": f"https://exemple.test/{n}",
        "reason": raison, "text": "", "title": None,
    }


class RechercheDoublee:
    def __init__(self, resultats):
        self.resultats = resultats
        self.requetes = []

    def search(self, query, max_results=5):
        self.requetes.append((query, max_results))
        return self.resultats[:max_results]


class LectureDoublee:
    def __init__(self, par_url):
        self.par_url = par_url
        self.urls_lues = []

    async def fetch(self, url):
        self.urls_lues.append(url)
        reponse = self.par_url.get(url)
        if isinstance(reponse, BaseException):
            raise reponse
        return reponse or page_ratee(0, "inconnue")


@pytest.fixture
def agent_factory(provider_factory):
    def _creer(resultats, pages, reponse_ia="Python 3.14 est la derniere version [1].", **kw):
        recherche = RechercheDoublee(resultats)
        lecture = LectureDoublee(pages)
        agent = FreshInfoAgent(
            provider=provider_factory(reponse_ia),
            search_tool=recherche, fetcher=lecture, **kw,
        )
        agent.recherche, agent.lecture = recherche, lecture
        return agent
    return _creer


# --- Chemin nominal ------------------------------------------------------------

async def test_la_reponse_est_accompagnee_de_ses_sources(agent_factory):
    agent = agent_factory(
        [resultat(1), resultat(2)],
        {"https://exemple.test/1": page_lue(1), "https://exemple.test/2": page_lue(2)},
    )

    res = await agent.run("Quelle est la derniere version de Python ?")

    assert res["status"] == "success"
    assert res["sources_count"] == 2
    assert [s["url"] for s in res["sources"]] == [
        "https://exemple.test/1", "https://exemple.test/2",
    ]
    assert [s["index"] for s in res["sources"]] == [1, 2]


async def test_le_contenu_lu_arrive_dans_le_prompt_pas_le_resume_du_moteur(agent_factory):
    """C'est toute la différence avec l'existant : on envoie la page, pas son résumé."""
    agent = agent_factory(
        [resultat(1)],
        {"https://exemple.test/1": page_lue(1, texte="Le texte reel de la page.")},
    )

    await agent.run("question")

    prompt = agent.provider.appels[0]["prompt"]
    assert "Le texte reel de la page." in prompt
    assert "resume 1" not in prompt


async def test_les_sources_sont_numerotees_dans_le_prompt(agent_factory):
    agent = agent_factory(
        [resultat(1), resultat(2)],
        {"https://exemple.test/1": page_lue(1), "https://exemple.test/2": page_lue(2)},
    )

    await agent.run("question")

    prompt = agent.provider.appels[0]["prompt"]
    assert "[1] Page 1" in prompt
    assert "[2] Page 2" in prompt
    assert "https://exemple.test/2" in prompt


async def test_le_modele_recoit_la_consigne_de_ne_pas_deviner(agent_factory):
    agent = agent_factory([resultat(1)], {"https://exemple.test/1": page_lue(1)})

    await agent.run("question")

    prompt = agent.provider.appels[0]["prompt"]
    assert "UNIQUEMENT sur les sources" in prompt
    assert "dis-le clairement au lieu de deviner" in prompt


# --- Refus : le point de la conception -----------------------------------------

async def test_sans_resultat_de_recherche_le_modele_n_est_pas_appele(agent_factory):
    agent = agent_factory([], {})

    res = await agent.run("question sans reponse")

    assert res["status"] == "warning"
    assert res["sources"] == []
    assert agent.provider.appels == []


async def test_sans_page_lisible_le_modele_n_est_pas_appele(agent_factory):
    """Une réponse inventée coûte plus cher qu'une absence de réponse."""
    agent = agent_factory(
        [resultat(1), resultat(2)],
        {"https://exemple.test/1": page_ratee(1), "https://exemple.test/2": page_ratee(2, "type non lisible")},
    )

    res = await agent.run("question")

    assert res["status"] == "warning"
    assert agent.provider.appels == []
    assert "je ne reponds pas de memoire" in res["response"]
    assert "code HTTP 404" in res["response"]
    assert "type non lisible" in res["response"]


async def test_une_page_vide_ne_compte_pas_comme_une_source(agent_factory):
    agent = agent_factory([resultat(1)], {"https://exemple.test/1": page_lue(1, texte="   ")})

    res = await agent.run("question")

    assert res["status"] == "warning"
    assert agent.provider.appels == []


async def test_une_seule_page_lisible_suffit(agent_factory):
    agent = agent_factory(
        [resultat(1), resultat(2)],
        {"https://exemple.test/1": page_ratee(1), "https://exemple.test/2": page_lue(2)},
    )

    res = await agent.run("question")

    assert res["status"] == "success"
    assert res["sources_count"] == 1
    assert res["unreadable"] == [
        {"url": "https://exemple.test/1", "reason": "code HTTP 404"}
    ]


async def test_une_lecture_qui_leve_n_interrompt_pas_l_agent(agent_factory):
    agent = agent_factory(
        [resultat(1), resultat(2)],
        {"https://exemple.test/1": RuntimeError("reseau coupe"),
         "https://exemple.test/2": page_lue(2)},
    )

    res = await agent.run("question")

    assert res["status"] == "success"
    assert res["unreadable"][0]["reason"] == "RuntimeError"


# --- Budget de contexte --------------------------------------------------------

async def test_le_contexte_envoye_reste_dans_le_budget(agent_factory):
    """num_ctx vaut 4096 jetons : cinq pages entières feraient déborder le contexte."""
    # « @ » n'apparait nulle part ailleurs dans le prompt : « x » etait present
    # dans « exemple.test » et faussait le compte.
    pages = {f"https://exemple.test/{n}": page_lue(n, texte="@" * 50_000) for n in (1, 2, 3)}
    agent = agent_factory([resultat(1), resultat(2), resultat(3)], pages,
                          budget_caracteres=3000)

    await agent.run("question")

    prompt = agent.provider.appels[0]["prompt"]
    assert prompt.count("@") == 3000, "le budget doit etre reparti exactement"
    assert len(prompt) < 4000, "le prompt entier doit rester compact"


async def test_le_budget_est_reparti_entre_les_sources(agent_factory):
    pages = {f"https://exemple.test/{n}": page_lue(n, texte="@" * 50_000) for n in (1, 2)}
    agent = agent_factory([resultat(1), resultat(2)], pages, budget_caracteres=4000)

    res = await agent.run("question")

    assert [s["characters"] for s in res["sources"]] == [2000, 2000]
    assert all(s["truncated"] for s in res["sources"])


async def test_le_nombre_de_pages_lues_est_plafonne(agent_factory):
    pages = {f"https://exemple.test/{n}": page_lue(n) for n in range(1, 6)}
    agent = agent_factory([resultat(n) for n in range(1, 6)], pages, sources_max=2)

    await agent.run("question")

    assert len(agent.lecture.urls_lues) == 2, "seules les premières pages doivent être lues"


async def test_une_page_courte_n_est_pas_marquee_tronquee(agent_factory):
    agent = agent_factory([resultat(1)], {"https://exemple.test/1": page_lue(1, texte="court")})

    res = await agent.run("question")

    assert res["sources"][0]["truncated"] is False
    assert res["sources"][0]["characters"] == 5


# --- Divers --------------------------------------------------------------------

async def test_la_question_est_transmise_telle_quelle_au_moteur(agent_factory):
    agent = agent_factory([resultat(1)], {"https://exemple.test/1": page_lue(1)})

    await agent.run("Quelle est la derniere version de Python ?")

    assert agent.recherche.requetes[0][0] == "Quelle est la derniere version de Python ?"


async def test_le_titre_du_moteur_depanne_quand_la_page_n_en_a_pas(agent_factory):
    agent = agent_factory(
        [resultat(1)], {"https://exemple.test/1": page_lue(1, titre=None)}
    )

    res = await agent.run("question")

    assert res["sources"][0]["title"] == "Titre 1"
