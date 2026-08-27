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


# ==============================================================================
# Résistance aux timeouts réseau
# ==============================================================================
class MoteurQuiLeve:
    """Moteur brut : lève ce qu'on lui donne, puis rend ce qu'on lui donne.

    Il remplace `_interroger`, pas `_executer` : le réessai vit sous `_executer`,
    et un double placé au-dessus ne le verrait jamais.
    """

    def __init__(self, erreurs, resultats=None):
        self.erreurs = list(erreurs)
        self.resultats = resultats if resultats is not None else []
        self.appels = 0

    def __call__(self, categorie, query, max_results, timelimit=None):
        self.appels += 1
        if self.erreurs:
            raise self.erreurs.pop(0)
        return self.resultats


def _brut(href="https://a.test", date="2026-08-27"):
    return {"title": "T", "href": href, "body": "extrait", "date": date}


class TestReessaiSurTimeout:
    """Mesuré le 2026-08-27 : la passe du jour perdue sur `operation timed out`."""

    def test_un_timeout_declenche_un_reessai_et_la_passe_reussit(self):
        moteur = MoteurQuiLeve(
            [Exception("error sending request for url (https://duckduckgo.com/?q=x) > operation timed out")],
            [_brut()],
        )
        outil = WebSearchTool()
        outil._interroger = moteur

        resultats = outil._executer("news", "senegal", 5, timelimit="d")

        assert moteur.appels == 2, "le timeout n'a pas été réessayé"
        assert len(resultats) == 1
        assert resultats[0]["date"] == "2026-08-27"

    def test_un_seul_reessai_jamais_deux(self):
        """Pas de boucle : deux échecs, on abandonne."""
        moteur = MoteurQuiLeve([TimeoutError("timed out"), TimeoutError("timed out")])
        outil = WebSearchTool()
        outil._interroger = moteur

        assert outil._executer("news", "q", 5, timelimit="d") == []
        assert moteur.appels == 2

    def test_une_absence_de_resultat_n_est_pas_reessayee(self):
        """`No results found` est une réponse, pas une panne."""
        moteur = MoteurQuiLeve([Exception("DDGSException: No results found.")])
        outil = WebSearchTool()
        outil._interroger = moteur

        assert outil._executer("news", "q", 5, timelimit="d") == []
        assert moteur.appels == 1, "une recherche vide a été réessayée"

    def test_une_erreur_definitive_n_est_pas_reessayee(self):
        """Un paramètre refusé se reproduira à l'identique."""
        moteur = MoteurQuiLeve([ValueError("unknown category 'videos'")])
        outil = WebSearchTool()
        outil._interroger = moteur

        assert outil._executer("videos", "q", 5) == []
        assert moteur.appels == 1

    @pytest.mark.parametrize("erreur", [
        TimeoutError("timed out"),
        ConnectionError("connection reset by peer"),
        Exception("operation timed out"),
        Exception("HTTP 503 Service Unavailable"),
        Exception("network is unreachable"),
    ])
    def test_ces_pannes_valent_un_reessai(self, erreur):
        from tools.search.web_search_tool import est_panne_passagere
        assert est_panne_passagere(erreur) is True

    @pytest.mark.parametrize("erreur", [
        Exception("No results found."),
        ValueError("unknown category"),
        Exception("invalid region code"),
    ])
    def test_ces_erreurs_ne_valent_pas_un_reessai(self, erreur):
        from tools.search.web_search_tool import est_panne_passagere
        assert est_panne_passagere(erreur) is False

    def test_un_timeout_sur_la_premiere_passe_ne_perd_plus_le_jour(self):
        """Le cas complet : la passe 1 échoue, le réessai la sauve.

        Sans réessai, la recherche se rabattait sur `text` et rendait des pages
        du 10 au 19 août pour une question du jour.
        """
        moteur = MoteurQuiLeve([TimeoutError("operation timed out")], [_brut(date="2026-08-27")])
        outil = WebSearchTool()
        outil._interroger = moteur

        resultats = outil.search("senegal", max_results=5, recent=True)

        assert resultats, "la recherche rend zéro alors que le réessai réussit"
        assert resultats[0]["date"] == "2026-08-27"
        assert resultats[0]["source"] == "news", "on est retombé sur une passe moins fraîche"


class TestDelaiGlobal:
    def test_une_recherche_normale_n_est_pas_amputee(self):
        moteur = MoteurQuiLeve([], [_brut()])
        outil = WebSearchTool(delai_total=30.0)
        outil._interroger = moteur

        assert outil.search("q", max_results=1, recent=True)

    def test_le_delai_epuise_arrete_les_passes_suivantes(self):
        """Un moteur muet ne peut pas retarder la réponse indéfiniment."""
        moteur = MoteurQuiLeve([], [])
        outil = WebSearchTool(delai_total=0.0)
        outil._interroger = moteur

        outil.search("q", max_results=5, recent=True)

        assert moteur.appels == 1, "des passes ont été lancées après l'échéance"

    def test_le_delai_est_local_a_chaque_recherche(self):
        """Deux recherches successives ne se volent pas leur budget."""
        moteur = MoteurQuiLeve([], [_brut()])
        outil = WebSearchTool(delai_total=30.0)
        outil._interroger = moteur

        assert outil.search("q1", max_results=1, recent=True)
        assert outil.search("q2", max_results=1, recent=True)
