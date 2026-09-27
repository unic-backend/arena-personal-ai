import pytest

from agents.fresh_info.fresh_info_agent import FreshInfoAgent


class MemoryPoison:
    def get_recent_history(self, session_id, limit=8):
        return [
            {"role": "user", "content": "Parle-moi de Brive et Colomiers en rugby."},
        ]


class Provider:
    def __init__(self):
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        if "Nouvelle question" in prompt:
            return "Qui sont les buteurs du match Angleterre Espagne ?"
        return "Les sources ne répondent pas à la question."


@pytest.mark.asyncio
async def test_historique_fourni_par_interface_est_prioritaire_sur_memoire_stale():
    provider = Provider()
    agent = FreshInfoAgent(provider=provider, memory=MemoryPoison())
    history = [
        {"role": "user", "content": "Qui a gagné entre Angleterre et Espagne ?"},
        {"role": "assistant", "content": "L'Espagne a gagné 3-2."},
        {"role": "user", "content": "Qui est l'homme du match ?"},
    ]

    question = await agent._reformuler_si_ellipse(
        "Qui sont les buteurs ?",
        {"session_id": "match", "history": history},
    )

    assert question == "Qui sont les buteurs du match Angleterre Espagne ?"
    assert "Angleterre et Espagne" in provider.prompts[0]
    assert "Brive" not in provider.prompts[0]


@pytest.mark.asyncio
async def test_historique_autoritatif_vide_ne_relit_jamais_la_memoire_serveur():
    provider = Provider()

    class MemoryInterdite:
        def get_recent_history(self, session_id, limit=8):
            raise AssertionError("un fil autoritatif vide ne doit pas relire la memoire")

    agent = FreshInfoAgent(provider=provider, memory=MemoryInterdite())
    question = await agent._reformuler_si_ellipse(
        "Quel temps fait-il aujourd'hui ?",
        {"session_id": "nouveau-fil", "history": [], "history_authoritative": True},
    )

    assert question == "Quel temps fait-il aujourd'hui ?"
    assert provider.prompts == []


@pytest.mark.asyncio
async def test_sans_historique_interface_relit_plusieurs_tours_de_session():
    provider = Provider()

    class Memory:
        def get_recent_history(self, session_id, limit=8):
            assert limit == 8
            return [
                {"role": "user", "content": "Qui a gagné entre Angleterre et Espagne ?"},
                {"role": "assistant", "content": "L'Espagne a gagné."},
            ]

    agent = FreshInfoAgent(provider=provider, memory=Memory())
    await agent._reformuler_si_ellipse("Qui sont les buteurs ?", {"session_id": "match"})
    assert "Angleterre et Espagne" in provider.prompts[0]


def test_synthese_interdit_de_changer_evenement_pour_coller_aux_sources():
    from agents.fresh_info.fresh_info_agent import GABARIT_SYNTHESE

    assert "HORS SUJET" in GABARIT_SYNTHESE
    assert "Ne change jamais le sujet" in GABARIT_SYNTHESE


class ProviderQuiPerdLeSujet:
    def __init__(self):
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        if "Nouvelle question" in prompt:
            if "Qui sont les Beatles ?" in prompt:
                return "Qui sont les Beatles ?"
            return "Qui sont les buteurs"
        return "Reponse sourcee [1]."


class RechercheTracee:
    def __init__(self, resultats):
        self.resultats = resultats
        self.requetes = []

    def search(self, query, max_results=5, recent=False):
        self.requetes.append(query)
        return self.resultats[:max_results]


class LecteurParUrl:
    def __init__(self, pages):
        self.pages = pages

    async def fetch(self, url):
        return self.pages[url]


@pytest.mark.asyncio
async def test_production_barcelone_un_suivi_sans_sujet_est_ancre_deterministement():
    """Reproduction du log Railway du 27/09/2026 a 00:15:32."""
    provider = ProviderQuiPerdLeSujet()
    recherche = RechercheTracee([])
    agent = FreshInfoAgent(provider=provider, search_tool=recherche)
    history = [
        {
            "role": "user",
            "content": (
                "Maintenant, quel a été le dernier match du FC Barcelone "
                "et quel était le score exact ? Vérifie sur le web."
            ),
        },
        {
            "role": "assistant",
            "content": "Les sources disponibles ne permettent pas de répondre.",
        },
    ]

    await agent.run(
        "Qui sont les buteurs",
        {"history": history, "history_authoritative": True},
    )

    assert recherche.requetes
    requete = recherche.requetes[0].casefold()
    assert "barcelone" in requete
    assert requete != "qui sont les buteurs"


@pytest.mark.asyncio
async def test_une_source_hockey_hors_sujet_est_eliminee_avant_la_synthese():
    provider = ProviderQuiPerdLeSujet()
    recherche = RechercheTracee([
        {
            "title": "Coupe de France de hockey",
            "href": "https://hockey.test/coupe",
            "body": "Jordane Fazende et Loic Chabert ont marque.",
        },
        {
            "title": "FC Barcelone - dernier match",
            "href": "https://football.test/barcelone",
            "body": "FC Barcelone : compte rendu du dernier match.",
        },
    ])
    lecteur = LecteurParUrl({
        "https://hockey.test/coupe": {
            "status": "FETCHED",
            "url": "https://hockey.test/coupe",
            "title": "Coupe de France de hockey",
            "text": "Jordane Fazende et Loic Chabert ont marque en hockey.",
            "truncated": False,
        },
        "https://football.test/barcelone": {
            "status": "FETCHED",
            "url": "https://football.test/barcelone",
            "title": "FC Barcelone - dernier match",
            "text": "Le FC Barcelone a dispute son dernier match. Buteurs verifies ici.",
            "truncated": False,
        },
    })
    agent = FreshInfoAgent(
        provider=provider,
        search_tool=recherche,
        fetcher=lecteur,
    )
    history = [{
        "role": "user",
        "content": "Quel a été le dernier match du FC Barcelone et le score exact ?",
    }]

    resultat = await agent.run(
        "Qui sont les buteurs ?",
        {"history": history, "history_authoritative": True},
    )

    assert resultat["status"] == "success"
    assert [s["url"] for s in resultat["sources"]] == [
        "https://football.test/barcelone"
    ]
    prompt_synthese = provider.prompts[-1]
    assert "FC Barcelone" in prompt_synthese
    assert "Jordane Fazende" not in prompt_synthese


@pytest.mark.asyncio
async def test_si_toutes_les_sources_sont_hors_sujet_arena_refuse():
    provider = ProviderQuiPerdLeSujet()
    recherche = RechercheTracee([{
        "title": "Hockey",
        "href": "https://hockey.test/coupe",
        "body": "Jordane Fazende et Loic Chabert.",
    }])
    lecteur = LecteurParUrl({
        "https://hockey.test/coupe": {
            "status": "FETCHED",
            "url": "https://hockey.test/coupe",
            "title": "Hockey",
            "text": "Jordane Fazende et Loic Chabert ont marque.",
            "truncated": False,
        },
    })
    agent = FreshInfoAgent(
        provider=provider,
        search_tool=recherche,
        fetcher=lecteur,
    )

    resultat = await agent.run(
        "Qui sont les buteurs ?",
        {
            "history": [{
                "role": "user",
                "content": "Quel a été le dernier match du FC Barcelone ?",
            }],
            "history_authoritative": True,
        },
    )

    assert resultat["status"] == "warning"
    assert resultat["sources"] == []
    assert "ne concernent pas le sujet" in resultat["response"]
    # Un seul appel modele : la reformulation. Aucune synthese hors sujet.
    assert len(provider.prompts) == 1


@pytest.mark.asyncio
async def test_question_courte_avec_sujet_explicit_ne_recupere_pas_l_ancien_sujet():
    provider = ProviderQuiPerdLeSujet()
    agent = FreshInfoAgent(provider=provider, search_tool=RechercheTracee([]))

    question = await agent._reformuler_si_ellipse(
        "Qui sont les Beatles ?",
        {
            "history": [{
                "role": "user",
                "content": "Parle-moi du FC Barcelone.",
            }],
            "history_authoritative": True,
        },
    )

    assert question == "Qui sont les Beatles ?"
    assert "barcelone" not in question.casefold()


@pytest.mark.asyncio
async def test_plusieurs_suivis_restent_sur_le_dernier_sujet_concret():
    provider = ProviderQuiPerdLeSujet()
    recherche = RechercheTracee([])
    agent = FreshInfoAgent(provider=provider, search_tool=recherche)
    history = [
        {
            "role": "user",
            "content": "Quel a été le dernier match du FC Barcelone ?",
        },
        {
            "role": "assistant",
            "content": "Je vérifie le dernier match du FC Barcelone.",
        },
        {
            "role": "user",
            "content": "Qui sont les buteurs ?",
        },
        {
            "role": "assistant",
            "content": "Je vérifie les buteurs.",
        },
    ]

    await agent.run(
        "Et l'homme du match ?",
        {"history": history, "history_authoritative": True},
    )

    assert recherche.requetes
    requete = recherche.requetes[0].casefold()
    assert "barcelone" in requete
    assert "homme du match" in requete


class ProviderSuiviEvenement:
    def __init__(self):
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        if "Nouvelle question" in prompt:
            return "Qui a marqué les buts lors du dernier match du FC Barcelone ?"
        return "Réponse vérifiée [1]."


def _historique_barca_seville():
    return [
        {
            "role": "user",
            "content": (
                "Quel a été le dernier match du FC Barcelone et quel était "
                "le score exact ? Vérifie sur le web."
            ),
        },
        {
            "role": "assistant",
            "content": (
                "Le dernier match du FC Barcelone était contre Séville. "
                "Barcelone l'a emporté 3-1."
            ),
        },
    ]


@pytest.mark.asyncio
async def test_suivi_detail_reutilise_l_evenement_resolu_comme_indice_de_recherche():
    """Reproduction du log production du 27/09/2026 a 01:20."""
    provider = ProviderSuiviEvenement()
    recherche = RechercheTracee([])
    agent = FreshInfoAgent(provider=provider, search_tool=recherche)

    await agent.run(
        "Qui sont les buteurs ?",
        {
            "history": _historique_barca_seville(),
            "history_authoritative": True,
        },
    )

    assert recherche.requetes
    requete = recherche.requetes[0].casefold()
    assert "barcelone" in requete
    assert "séville" in requete
    assert "3-1" in requete


@pytest.mark.asyncio
async def test_suivi_detail_elimine_une_source_du_bon_club_mais_du_mauvais_evenement():
    provider = ProviderSuiviEvenement()
    recherche = RechercheTracee([
        {
            "title": "Une jeune joueuse du FC Barcelone",
            "href": "https://med1.test/barca-jeune",
            "body": "Actualité générale du FC Barcelone sans rapport avec Séville.",
        },
        {
            "title": "FC Barcelone - Séville 3-1",
            "href": "https://officiel.test/barca-seville",
            "body": "FC Barcelone contre Séville, victoire 3-1.",
        },
    ])
    lecteur = LecteurParUrl({
        "https://med1.test/barca-jeune": {
            "status": "FETCHED",
            "url": "https://med1.test/barca-jeune",
            "title": "Une jeune joueuse du FC Barcelone",
            "text": "Actualité générale du FC Barcelone sans détail sur le match demandé.",
            "truncated": False,
        },
        "https://officiel.test/barca-seville": {
            "status": "FETCHED",
            "url": "https://officiel.test/barca-seville",
            "title": "FC Barcelone - Séville 3-1",
            "text": (
                "Le FC Barcelone a battu Séville 3-1. "
                "Les buteurs du match sont indiqués dans ce compte rendu."
            ),
            "truncated": False,
        },
    })
    agent = FreshInfoAgent(
        provider=provider,
        search_tool=recherche,
        fetcher=lecteur,
    )

    resultat = await agent.run(
        "Qui sont les buteurs ?",
        {
            "history": _historique_barca_seville(),
            "history_authoritative": True,
        },
    )

    assert resultat["status"] == "success"
    assert [s["url"] for s in resultat["sources"]] == [
        "https://officiel.test/barca-seville"
    ]
    assert "med1.test" not in provider.prompts[-1]


@pytest.mark.asyncio
async def test_suivi_detail_refuse_si_aucune_source_ne_confirme_l_evenement_resolu():
    provider = ProviderSuiviEvenement()
    recherche = RechercheTracee([{
        "title": "FC Barcelone actualité",
        "href": "https://general.test/barca",
        "body": "Actualité générale du FC Barcelone.",
    }])
    lecteur = LecteurParUrl({
        "https://general.test/barca": {
            "status": "FETCHED",
            "url": "https://general.test/barca",
            "title": "FC Barcelone actualité",
            "text": "Actualité générale du FC Barcelone sans mention de l’adversaire.",
            "truncated": False,
        },
    })
    agent = FreshInfoAgent(
        provider=provider,
        search_tool=recherche,
        fetcher=lecteur,
    )

    resultat = await agent.run(
        "Qui sont les buteurs ?",
        {
            "history": _historique_barca_seville(),
            "history_authoritative": True,
        },
    )

    assert resultat["status"] == "warning"
    assert resultat["sources"] == []
    assert "evenement precis" in resultat["response"]
    # Reformulation uniquement : aucune synthese avec une mauvaise rencontre.
    assert len(provider.prompts) == 1
