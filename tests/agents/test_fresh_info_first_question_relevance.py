"""Une premiere question ne recoit que des sources qui parlent de son sujet (DEC-0151).

Mesure du 28/09/2026 sur le vrai moteur, avant correction :
- « derniere version de Python » -> un article sur GTA 6 envoye a la synthese ;
- « president du Senegal » -> un article sur la Guinee ; les pages Wikipedia,
  pertinentes, refusees (403), et leurs extraits jetes ;
- « quel temps a Dakar » -> un article sur l'IA et la fin des temps.
Les suivis avaient deja une barriere (#347) ; les premieres questions non.
"""
from agents.fresh_info.fresh_info_agent import FreshInfoAgent


def _resultat(n, titre, extrait=""):
    return {"title": titre, "href": f"https://exemple.test/{n}", "body": extrait}


def _page(n, titre, texte):
    return {"status": "FETCHED", "url": f"https://exemple.test/{n}", "title": titre,
            "text": texte, "truncated": False}


class _Recherche:
    def __init__(self, resultats):
        self.resultats = resultats

    def search(self, query, max_results=5, recent=False):
        return self.resultats[:max_results]


class _Lecture:
    def __init__(self, pages):
        self.pages = pages
        self.lues = []

    async def fetch(self, url):
        self.lues.append(url)
        return self.pages.get(url) or {"status": "FAILED", "url": url, "reason": "code HTTP 403",
                                       "text": "", "title": None}


class _Modele:
    def __init__(self):
        self.prompts = []

    async def generate(self, prompt, system_prompt=None, **options):
        self.prompts.append(prompt)
        return "Python 3.14.7 [1]."


def _agent(resultats, pages):
    modele = _Modele()
    agent = FreshInfoAgent(provider=modele, search_tool=_Recherche(resultats),
                           fetcher=_Lecture(pages))
    return agent, modele


async def test_une_page_hors_sujet_n_atteint_pas_la_synthese():
    agent, modele = _agent(
        [_resultat(1, "GTA 6 : Rockstar confie les secrets de Leonida"),
         _resultat(2, "Download Python | Python.org", "Python 3.14.7")],
        {"https://exemple.test/1": _page(1, "GTA 6", "Leonida, Rockstar, sortie en novembre."),
         "https://exemple.test/2": _page(2, "Download Python", "Download Python 3.14.7")})

    resultat = await agent.run("Quelle est la dernière version de Python ?")

    assert [s["url"] for s in resultat["sources"]] == ["https://exemple.test/2"]
    assert "GTA" not in modele.prompts[-1] and "Leonida" not in modele.prompts[-1]
    assert agent.fetcher.lues == ["https://exemple.test/2"], "la page hors sujet n'est meme pas lue"


async def test_sans_aucune_source_sur_le_sujet_l_agent_le_dit_sans_appeler_le_modele():
    agent, modele = _agent(
        [_resultat(1, "L'IA et la fin des temps", "des chretiens croient...")],
        {"https://exemple.test/1": _page(1, "L'IA", "La fin des temps.")})

    resultat = await agent.run("Quel temps fait-il à Dakar aujourd'hui ?")

    assert resultat["status"] == "warning"
    assert "dakar" in resultat["response"].casefold()
    assert modele.prompts == []


async def test_l_extrait_d_une_page_pertinente_illisible_est_garde():
    """Wikipedia refusee (403) : son extrait de recherche devient une source,
    a cote de la page lisible — au lieu d'etre jete parce qu'une autre page
    etait lisible."""
    agent, modele = _agent(
        [_resultat(1, "Sénégal : actualité politique", "Le président sénégalais..."),
         _resultat(2, "Bassirou Diomaye Faye — Wikipédia",
                   "Bassirou Diomaye Faye est le président de la République du Sénégal")],
        {"https://exemple.test/1": _page(1, "Sénégal", "Au Sénégal, le gouvernement...")})

    resultat = await agent.run("Qui est le président du Sénégal ?")

    urls = [s["url"] for s in resultat["sources"]]
    assert urls == ["https://exemple.test/1", "https://exemple.test/2"]
    assert "Bassirou Diomaye Faye est le président" in modele.prompts[-1]


def test_une_page_tableau_n_envoie_pas_une_colonne_de_noms_repetes():
    """Mesure du 28/09/2026 (calendrier footmercato) : le modele recevait
    « Barcelone | Barcelone | Barcelone... ». Les cellules sont regroupees en
    lignes : chaque match garde son adversaire et sa date."""
    remplissage = "\n".join(f"Article {i} : une actualite sans rapport avec le sujet demande ici." for i in range(30))
    cellules = "\n".join(f"Barcelone\nAdversaire {i}\n{10 + i}/10" for i in range(20))
    page = f"{remplissage}\n{cellules}"

    extrait = FreshInfoAgent.extraire_pertinent(
        page, "Quel a été le dernier match du FC Barcelone ?", 400)

    assert "Adversaire 0" in extrait and "10/10" in extrait
    assert "Barcelone\nBarcelone" not in extrait


import pytest  # noqa: E402


@pytest.mark.parametrize("question, sujet", [
    ("Quel temps fait-il à Dakar aujourd'hui ?", ["dakar"]),
    ("Qui est le président du Sénégal ?", ["sénégal"]),
    ("Quel est le prix du bitcoin aujourd'hui ?", ["bitcoin"]),
    ("Combien coûte l'iPhone 17 ?", ["iphone"]),
    ("Résultat du match Sénégal Égypte", ["sénégal", "égypte"]),
    # Une question sans sujet propre n'a pas de barriere : elle ne doit pas
    # etre refusee faute d'un mot que les pages du jour ne portent pas.
    ("Quelles sont les actualités du jour ?", []),
    ("Donne-moi les dernières infos", []),
    ("C'est quoi les nouvelles aujourd'hui ?", []),
])
def test_le_sujet_d_une_question_ignore_le_temps_et_les_pronoms(question, sujet):
    """« aujourd'hui » coupe en « aujourd » + « hui », « fait-il », « jour »
    rendaient la barriere passoire — n'importe quelle page du jour les porte."""
    assert FreshInfoAgent._sujet_de_la_question(question) == sujet


async def test_une_question_generique_n_est_pas_refusee_par_la_barriere():
    agent, modele = _agent(
        [_resultat(1, "Sénégal : le budget 2027 adopté", "L'Assemblée a voté")],
        {"https://exemple.test/1": _page(1, "Budget", "L'Assemblée nationale a voté le budget.")})

    resultat = await agent.run("Quelles sont les actualités du jour ?")

    assert resultat["status"] == "success"
    assert modele.prompts, "la synthese a bien ete appelee"


async def test_sans_resultat_du_jour_sur_le_sujet_une_recherche_sans_date_suit():
    """Mesure du 28/09/2026 : la passe « actualites du jour » remplissait les
    cinq resultats (GTA 6, Tesla...) et la passe web sans date, qui trouve
    python.org, n'avait jamais lieu."""

    class _RechercheEnDeuxTemps:
        def __init__(self):
            self.appels = []

        def search(self, query, max_results=5, recent=False):
            self.appels.append(recent)
            if recent:
                return [_resultat(1, "GTA 6 : Rockstar confie les secrets de Leonida")]
            return [_resultat(2, "Download Python | Python.org", "Python 3.14.7")]

    modele = _Modele()
    agent = FreshInfoAgent(
        provider=modele, search_tool=_RechercheEnDeuxTemps(),
        fetcher=_Lecture({"https://exemple.test/2": _page(2, "Python", "Python 3.14.7")}))

    resultat = await agent.run("Quelle est la dernière version de Python ?")

    assert agent.search_tool.appels == [True, False]
    assert [s["url"] for s in resultat["sources"]] == ["https://exemple.test/2"]
