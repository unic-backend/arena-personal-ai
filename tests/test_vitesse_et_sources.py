"""Deux demandes du propriétaire, 2026-08-26 : aller plus vite, et se taire sur
les sources tant qu'on ne les demande pas.

La vitesse totale dépend du GPU du propriétaire, qui n'existe pas ici : elle
n'est donc **pas** mesurée. Ce qui l'est, et qui est le seul coût réductible
sans matériel, c'est le temps réseau — et le fait qu'une page lente ne retienne
plus toute la réponse.
"""
import asyncio
import time

import pytest

from agents.fresh_info.fresh_info_agent import FreshInfoAgent
from apps.backend.routers.chat import formater_sources, sources_demandees

SOURCES = [
    {"index": 1, "title": "Une page", "url": "https://exemple.test/a"},
    {"index": 2, "title": "Une autre", "url": "https://exemple.test/b"},
]


class TestSourcesALaDemande:
    @pytest.mark.parametrize("question", [
        "qui a remporté la coupe du monde 2026",
        "quelle est la population du Sénégal",
        "quel temps fait-il à Dakar",
    ])
    def test_par_defaut_aucune_liste_d_adresses(self, question):
        assert formater_sources(SOURCES, question) == ""

    @pytest.mark.parametrize("question", [
        "qui a gagné la coupe du monde 2026 ? donne tes sources",
        "quelle est la population du Sénégal, avec les liens",
        "d'où vient cette information",
        "tu peux le prouver",
        "donne-moi l'url",
    ])
    def test_reclamees_elles_sont_affichees(self, question):
        texte = formater_sources(SOURCES, question)
        assert "**Sources**" in texte
        assert "https://exemple.test/a" in texte

    def test_sans_source_rien_n_est_ajoute_meme_si_on_demande(self):
        assert formater_sources([], "donne tes sources") == ""

    def test_la_detection_ignore_la_casse_et_les_accents_manquants(self):
        assert sources_demandees("DONNE TES SOURCES") is True
        assert sources_demandees("d ou vient cette info") is True
        assert sources_demandees("raconte-moi une histoire") is False


class LecteurLent:
    """Une page répond vite, l'autre jamais."""

    def __init__(self, delai_lent: float = 30.0):
        self.delai_lent = delai_lent

    async def fetch(self, url: str):
        if "lent" in url:
            await asyncio.sleep(self.delai_lent)
        return {"status": "FETCHED", "url": url, "text": "contenu lisible", "title": "T"}


class RechercheDouble:
    def search(self, query, max_results=5):
        return [
            {"href": "https://rapide.test/", "title": "rapide"},
            {"href": "https://lent.test/", "title": "lent"},
        ]


class ModeleDouble:
    async def generate(self, prompt, **kw):
        return "réponse synthétisée"


class TestUnePageLenteNeRetientPlusToutLeMonde:
    @pytest.mark.asyncio
    async def test_la_lecture_s_arrete_au_delai(self):
        """Mesuré : sans plafond, l'agent attendait la page lente jusqu'au bout."""
        agent = FreshInfoAgent(provider=ModeleDouble())
        agent.search_tool = RechercheDouble()
        agent.fetcher = LecteurLent(delai_lent=30.0)
        agent.delai_lecture = 0.3

        depart = time.monotonic()
        resultat = await agent.run("une question")
        ecoule = time.monotonic() - depart

        assert ecoule < 3.0, f"a attendu {ecoule:.1f} s au lieu de s'arrêter à 0,3 s"
        assert resultat["status"] in ("success", "warning")

    @pytest.mark.asyncio
    async def test_quand_tout_repond_vite_rien_n_est_perdu(self):
        """Le plafond ne doit pas amputer un cas normal."""
        agent = FreshInfoAgent(provider=ModeleDouble())
        agent.search_tool = RechercheDouble()
        agent.fetcher = LecteurLent(delai_lent=0.0)
        agent.delai_lecture = 5.0

        resultat = await agent.run("une question")

        assert resultat["status"] == "success"
        assert resultat["sources_count"] == 2


class TestLaRechercheNeFigePlusLeServeur:
    @pytest.mark.asyncio
    async def test_une_recherche_qui_ne_repond_pas_est_abandonnee(self, monkeypatch):
        """Sans plafond, un moteur muet fige la réponse entière."""
        import agents.fresh_info.fresh_info_agent as module

        monkeypatch.setattr(module, "DELAI_RECHERCHE_SECONDES", 0.2)

        class RechercheMuette:
            def search(self, query, max_results=5):
                time.sleep(5)
                return []

        agent = FreshInfoAgent(provider=ModeleDouble())
        agent.search_tool = RechercheMuette()

        depart = time.monotonic()
        resultat = await agent.run("une question")
        ecoule = time.monotonic() - depart

        assert ecoule < 2.0, f"a attendu {ecoule:.1f} s"
        assert resultat["status"] == "warning"
        assert "Aucun resultat" in resultat["response"]


class TestCeQuiEstArriveEstConserve:
    """Le premier correctif jetait aussi les pages déjà lues. Mesuré, corrigé."""

    class LecteurMixte:
        async def fetch(self, url: str):
            await asyncio.sleep(5.0 if "lent" in url else 0.0)
            return {"status": "FETCHED", "url": url, "text": "contenu lisible", "title": "T"}

    class RechercheTrois:
        def search(self, query, max_results=5):
            return [
                {"href": "https://rapide1.test/", "title": "a"},
                {"href": "https://rapide2.test/", "title": "b"},
                {"href": "https://lent.test/", "title": "c"},
            ]

    @pytest.mark.asyncio
    async def test_les_pages_rapides_survivent_a_l_abandon_de_la_lente(self):
        agent = FreshInfoAgent(provider=ModeleDouble())
        agent.search_tool = self.RechercheTrois()
        agent.fetcher = self.LecteurMixte()
        agent.delai_lecture = 0.3

        resultat = await agent.run("une question")

        assert resultat["status"] == "success", "tout a été jeté au lieu des seules pages lentes"
        assert resultat["sources_count"] == 2
        assert len(resultat["unreadable"]) == 1
