"""Une question elliptique doit garder son vrai sujet avant de partir en recherche.

Mesuré le 30/08/2026 (signalé par le propriétaire) : après « Qui a gagné la
coupe du monde 2002 » puis « Celle de 2006 », la question « Celle de 2026 »
partait en recherche telle quelle. Sans le sujet, « Celle » est lu comme la
ville allemande (Landkreis Celle), et Usman répondait avec des faits divers
locaux — vol, radars, météo — au lieu de la Coupe du Monde.
"""
import pytest

from agents.fresh_info.fresh_info_agent import FreshInfoAgent


class MemoireDouble:
    """Rend l'historique qu'on lui donne, sans base de données derrière."""

    def __init__(self, historique=None):
        self._historique = historique or []
        self.appels = []

    def get_recent_history(self, session_id, limit=10):
        self.appels.append((session_id, limit))
        return self._historique


class ModeleReformulation:
    """Répond à la reformulation avec un texte fixe, puis à la synthèse normalement.

    Le premier appel est la reformulation, le second la synthèse — comme dans
    `FreshInfoAgent.run` une fois la recherche faite.
    """

    def __init__(self, reformulation="question reformulee", echoue_reformulation=False):
        self.prompts = []
        self._reformulation = reformulation
        self._echoue = echoue_reformulation

    async def generate(self, prompt, **kw):
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            if self._echoue:
                raise ConnectionError("modele indisponible")
            return self._reformulation
        return "réponse fondée sur les extraits"


class RechercheEnregistree:
    """Note chaque requête reçue, pour vérifier ce qui a réellement été cherché."""

    def __init__(self, resultats=None):
        self.requetes = []
        self._resultats = resultats if resultats is not None else [
            {"title": "T", "href": "https://x.test/1", "body": "un extrait", "date": None}
        ]

    def search(self, query, max_results=5, recent=False):
        self.requetes.append(query)
        return self._resultats


class LecteurQuiMarche:
    async def fetch(self, url):
        return {"status": "FETCHED", "url": url, "text": "contenu de page", "title": "T"}


def _agent(memoire, modele):
    agent = FreshInfoAgent(provider=modele, memory=memoire)
    agent.search_tool = RechercheEnregistree()
    agent.fetcher = LecteurQuiMarche()
    return agent


class TestReformulationDesQuestionsElliptiques:
    @pytest.mark.asyncio
    async def test_question_elliptique_est_completee_avec_lhistorique(self):
        memoire = MemoireDouble(historique=[
            {"role": "user", "content": "Qui a gagné la coupe du monde 2002 ?"},
            {"role": "assistant", "content": "Le Brésil."},
            {"role": "user", "content": "Celle de 2006 ?"},
            {"role": "assistant", "content": "L'Italie."},
        ])
        modele = ModeleReformulation(reformulation="Qui a gagné la Coupe du Monde 2026 ?")
        agent = _agent(memoire, modele)

        resultat = await agent.run("Celle de 2026", context={"session_id": "pwa"})

        assert agent.search_tool.requetes == ["Qui a gagné la Coupe du Monde 2026 ?"], (
            "la recherche est partie sur la question brute, pas sur la version "
            "reformulee — c'est exactement le bug rapporte"
        )
        assert resultat["query"] == "Qui a gagné la Coupe du Monde 2026 ?"

    @pytest.mark.asyncio
    async def test_sans_session_id_la_question_part_telle_quelle(self):
        """Pas de session -> pas d'appel de reformulation : rien a completer."""
        memoire = MemoireDouble(historique=[{"role": "user", "content": "peu importe"}])
        modele = ModeleReformulation()
        agent = _agent(memoire, modele)

        await agent.run("une question autonome")

        assert agent.search_tool.requetes == ["une question autonome"]
        assert len(modele.prompts) == 1, "un appel de reformulation a eu lieu sans session"

    @pytest.mark.asyncio
    async def test_sans_historique_la_question_part_telle_quelle(self):
        """Une session sans aucun tour precedent n'a rien a apporter."""
        memoire = MemoireDouble(historique=[])
        modele = ModeleReformulation()
        agent = _agent(memoire, modele)

        await agent.run("une question", context={"session_id": "pwa"})

        assert agent.search_tool.requetes == ["une question"]
        assert len(modele.prompts) == 1

    @pytest.mark.asyncio
    async def test_sans_memoire_la_question_part_telle_quelle(self):
        """Un agent sans MemoryManager (comme dans les tests existants) reste inchange."""
        modele = ModeleReformulation()
        agent = FreshInfoAgent(provider=modele)
        agent.search_tool = RechercheEnregistree()
        agent.fetcher = LecteurQuiMarche()

        await agent.run("une question", context={"session_id": "pwa"})

        assert agent.search_tool.requetes == ["une question"]
        assert len(modele.prompts) == 1

    @pytest.mark.asyncio
    async def test_reformulation_qui_echoue_garde_la_question_dorigine(self):
        """Une panne du modele sur la reformulation ne doit pas bloquer la recherche."""
        memoire = MemoireDouble(historique=[{"role": "user", "content": "contexte"}])
        modele = ModeleReformulation(echoue_reformulation=True)
        agent = _agent(memoire, modele)

        resultat = await agent.run("Celle de 2026", context={"session_id": "pwa"})

        assert agent.search_tool.requetes == ["Celle de 2026"]
        assert resultat["status"] == "success"
