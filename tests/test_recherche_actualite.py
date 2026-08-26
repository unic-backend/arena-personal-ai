"""La recherche doit voir ce qui a moins d'une heure, et ne pas abandonner.

Deux échecs mesurés le 2026-08-26 :

- « quelle est la dernière victoire du Real Madrid en championnat » →
  *« Aucun résultat de recherche »* ;
- « quand Real jouera son prochain match » → des pages générales, sans date.

Trois réglages de `ddgs` n'étaient pas utilisés — région, fraîcheur, catégorie
`news` — et l'agent renonçait dès qu'aucune page n'était lisible, alors que le
moteur avait rendu des extraits.
"""
import pytest

from agents.fresh_info.fresh_info_agent import FreshInfoAgent
from tools.search.web_search_tool import WebSearchTool


class MoteurDouble:
    """Enregistre chaque appel, rend ce qu'on lui dit de rendre."""

    def __init__(self, par_categorie=None):
        self.appels = []
        self.par_categorie = par_categorie or {}

    def __call__(self, categorie, query, max_results, timelimit=None):
        self.appels.append({"categorie": categorie, "timelimit": timelimit, "query": query})
        return self.par_categorie.get((categorie, timelimit), [])


def _resultat(href, titre="T", corps="un extrait", date=None):
    return {"title": titre, "href": href, "body": corps, "date": date, "source": "test"}


class TestStrategieDeRecherche:
    def test_une_question_recente_commence_par_les_actualites_du_jour(self):
        moteur = MoteurDouble({("news", "d"): [_resultat("https://a.test", date="2026-08-26")]})
        outil = WebSearchTool()
        outil._executer = moteur

        resultats = outil.search("dernier match", max_results=1, recent=True)

        assert moteur.appels[0] == {"categorie": "news", "timelimit": "d", "query": "dernier match"}
        assert resultats[0]["date"] == "2026-08-26"

    def test_sans_actualite_du_jour_on_elargit_a_la_semaine(self):
        moteur = MoteurDouble({("text", "w"): [_resultat("https://b.test")]})
        outil = WebSearchTool()
        outil._executer = moteur

        outil.search("dernier match", max_results=3, recent=True)

        categories = [(a["categorie"], a["timelimit"]) for a in moteur.appels]
        assert ("news", "d") in categories
        assert ("text", "w") in categories

    def test_on_finit_sans_contrainte_de_date_plutot_que_zero_resultat(self):
        """Le cas exact du 2026-08-26 : la recherche rendait zéro."""
        moteur = MoteurDouble({("text", None): [_resultat("https://c.test")]})
        outil = WebSearchTool()
        outil._executer = moteur

        resultats = outil.search("derniere victoire du real madrid", max_results=3, recent=True)

        assert resultats, "la recherche rend encore zéro résultat"
        assert ("text", None) in [(a["categorie"], a["timelimit"]) for a in moteur.appels]

    def test_une_question_intemporelle_ne_paie_pas_le_filtre_de_fraicheur(self):
        moteur = MoteurDouble({("text", None): [_resultat("https://d.test")]})
        outil = WebSearchTool()
        outil._executer = moteur

        outil.search("qu'est-ce que la photosynthèse", max_results=3, recent=False)

        assert [a["categorie"] for a in moteur.appels] == ["text"]
        assert moteur.appels[0]["timelimit"] is None

    def test_un_meme_lien_n_est_pas_compte_deux_fois(self):
        moteur = MoteurDouble({
            ("news", "d"): [_resultat("https://meme.test")],
            ("text", "w"): [_resultat("https://meme.test")],
            ("text", None): [_resultat("https://meme.test")],
        })
        outil = WebSearchTool()
        outil._executer = moteur

        assert len(outil.search("q", max_results=5, recent=True)) == 1

    def test_la_recherche_se_fait_en_francais(self):
        assert WebSearchTool().region == "fr-fr"


class LecteurQuiEchoue:
    async def fetch(self, url):
        return {"status": "FAILED", "url": url, "reason": "403", "text": "", "title": None}


class ModeleDouble:
    def __init__(self):
        self.prompts = []

    async def generate(self, prompt, **kw):
        self.prompts.append(prompt)
        return "réponse fondée sur les extraits"


class TestSecoursParExtraits:
    """Les sites d'actualité bloquent les robots. Ce n'est pas une raison d'abandonner."""

    @pytest.mark.asyncio
    async def test_les_extraits_servent_quand_aucune_page_n_est_lisible(self):
        class Recherche:
            def search(self, query, max_results=5, recent=False):
                return [
                    {"title": "Real 2-0", "href": "https://sport.test/1",
                     "body": "Le Real Madrid s'est imposé 2-0 samedi.", "date": "2026-08-25"},
                ]

        modele = ModeleDouble()
        agent = FreshInfoAgent(provider=modele)
        agent.search_tool = Recherche()
        agent.fetcher = LecteurQuiEchoue()

        resultat = await agent.run("derniere victoire du real")

        assert resultat["status"] == "success", "l'agent a renoncé alors qu'il avait un extrait"
        assert resultat["sources_count"] == 1
        assert "sport.test" in resultat["sources"][0]["url"]
        assert "2-0" in modele.prompts[0]
        assert "2026-08-25" in modele.prompts[0], "la date de l'article n'est pas transmise"

    @pytest.mark.asyncio
    async def test_sans_extrait_ni_page_l_agent_refuse_toujours(self):
        """Le garde-fou d'origine ne doit pas être perdu."""
        class RechercheSansCorps:
            def search(self, query, max_results=5, recent=False):
                return [{"title": "T", "href": "https://x.test/1", "body": "", "date": None}]

        agent = FreshInfoAgent(provider=ModeleDouble())
        agent.search_tool = RechercheSansCorps()
        agent.fetcher = LecteurQuiEchoue()

        resultat = await agent.run("une question")

        assert resultat["status"] == "warning"
        assert "je ne reponds pas de memoire" in resultat["response"]

    @pytest.mark.asyncio
    async def test_une_page_lue_reste_preferee_a_un_extrait(self):
        """L'extrait est un secours, pas un raccourci."""
        class Recherche:
            def search(self, query, max_results=5, recent=False):
                return [{"title": "T", "href": "https://ok.test/1", "body": "extrait court", "date": None}]

        class LecteurQuiMarche:
            async def fetch(self, url):
                return {"status": "FETCHED", "url": url,
                        "text": "le contenu complet de la page", "title": "T"}

        modele = ModeleDouble()
        agent = FreshInfoAgent(provider=modele)
        agent.search_tool = Recherche()
        agent.fetcher = LecteurQuiMarche()

        await agent.run("une question")

        assert "le contenu complet de la page" in modele.prompts[0]
        assert "extrait court" not in modele.prompts[0]


def test_toute_doublure_de_recherche_suit_la_vraie_signature():
    """Une doublure qui a dérivé fait échouer 19 tests d'un coup. Vécu.

    Ajouter `recent` à `WebSearchTool.search` a cassé toutes les doublures qui
    ne connaissaient que `(query, max_results)`. Ce test compare les signatures
    au lieu d'attendre le prochain paramètre pour s'en apercevoir.
    """
    import inspect
    import re
    from pathlib import Path

    attendus = set(inspect.signature(WebSearchTool.search).parameters) - {"self"}
    racine = Path(__file__).resolve().parent

    ecarts = []
    for fichier in racine.rglob("test_*.py"):
        for ligne in fichier.read_text(encoding="utf-8").splitlines():
            trouve = re.search(r"def search\(self,([^)]*)\)", ligne)
            if not trouve:
                continue
            noms = {p.split("=")[0].split(":")[0].strip() for p in trouve.group(1).split(",")}
            manquants = attendus - noms
            if manquants:
                ecarts.append(f"{fichier.name} : il manque {sorted(manquants)}")

    assert ecarts == [], "doublures désynchronisées :\n" + "\n".join(ecarts)
