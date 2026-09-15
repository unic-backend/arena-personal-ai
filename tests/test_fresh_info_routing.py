"""Le chat va-t-il réellement chercher l'information sur le web ?

Ces tests parcourent la chaîne HTTP complète : routeur → agent → sources
renvoyées à l'appelant. Le modèle et le web sont doublés ; le reste est réel.
"""
import datetime

import pytest
from fastapi.testclient import TestClient

from agents.orchestrator.orchestrator_agent import OrchestratorAgent
from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import chat as routeur_chat
from apps.backend.routers import openai_gateway as passerelle

CLE = "cle-de-test"
ENTETES = {"Authorization": f"Bearer {CLE}"}

REPONSE_SOURCEE = {
    "status": "success",
    "agent": "FreshInfoAgent",
    "response": "Python 3.14 est la dernière version [1].",
    "sources_count": 1,
    "sources": [
        {"index": 1, "title": "Python 3.14", "url": "https://exemple.test/py",
         "characters": 120, "truncated": False},
    ],
    "unreadable": [],
}


async def _reponse_de_chat(user_input=None, context=None, **kw):
    """Réponse conversationnelle simulée : pas d'appel au modèle, pas de source."""
    return {"intent": "CHAT", "agent": "OrchestratorAgent", "response": "Bonjour."}


class AgentDouble:
    def __init__(self, reponse):
        self.reponse = reponse
        self.demandes = []

    async def run(self, user_input, context=None):
        self.demandes.append(user_input)
        return self.reponse


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE)
    monkeypatch.setattr(securite, "REQUETES_MAX", 100)
    monkeypatch.setattr(securite.limiteur, "requetes_max", 100)

    # `/api/chat` s'arrête avant tout agent si Ollama ne répond pas. C'est le
    # comportement voulu ; ici on veut mesurer l'aiguillage, pas cette garde.
    async def toujours_disponible():
        return True

    monkeypatch.setattr(main.fast_provider, "is_available", toujours_disponible)
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def agent_double(monkeypatch) -> AgentDouble:
    double = AgentDouble(REPONSE_SOURCEE)
    monkeypatch.setattr(routeur_chat, "fresh_agent", double)
    monkeypatch.setattr(passerelle, "fresh_agent", double)
    return double


@pytest.fixture
def intention(monkeypatch):
    """Force l'intention détectée, sans dépendre du modèle."""
    def _forcer(valeur):
        async def _classer(user_input):
            return valeur
        monkeypatch.setattr(routeur_chat.orchestrator, "analyze_intent", _classer)
    return _forcer


# --- Mise en forme des sources -------------------------------------------------

def test_les_sources_sont_listees_quand_on_les_demande():
    texte = routeur_chat.formater_sources(REPONSE_SOURCEE["sources"], "donne tes sources")

    assert "**Sources**" in texte
    assert "[1] Python 3.14 — https://exemple.test/py" in texte


def test_sans_demande_la_liste_d_adresses_reste_masquee():
    """Décision du propriétaire, 2026-08-26 : elle encombre chaque réponse."""
    texte = routeur_chat.formater_sources(REPONSE_SOURCEE["sources"], "quelle heure est-il")

    assert texte == ""


def test_sans_source_rien_n_est_ajoute():
    assert routeur_chat.formater_sources([], "donne tes sources") == ""


# --- /api/chat -----------------------------------------------------------------

def test_une_question_d_actualite_atteint_l_agent(client, agent_double, intention):
    intention("FRESH_INFO")

    res = client.post("/api/chat",
                      json={"prompt": "Quelle est la dernière version de Python ?"},
                      headers=ENTETES)

    assert res.status_code == 200
    assert agent_double.demandes == ["Quelle est la dernière version de Python ?"]


def test_les_sources_sont_renvoyees_a_l_appelant(client, agent_double, intention):
    intention("FRESH_INFO")

    corps = client.post("/api/chat", json={"prompt": "question"}, headers=ENTETES).json()

    assert corps["agent"] == "FreshInfoAgent"
    assert corps["sources"][0]["url"] == "https://exemple.test/py"


def test_l_intention_annoncee_est_celle_qui_a_ete_suivie(client, agent_double, intention):
    """Elle annonçait « CHAT » même quand un agent spécialisé avait répondu."""
    intention("FRESH_INFO")

    corps = client.post("/api/chat", json={"prompt": "question"}, headers=ENTETES).json()

    assert corps["intent"] == "FRESH_INFO"
    assert corps["agent"] == "FreshInfoAgent"


def test_une_conversation_ordinaire_ne_declenche_pas_de_recherche(
    client, agent_double, intention, monkeypatch
):
    intention("CHAT")
    monkeypatch.setattr(routeur_chat.orchestrator, "run", _reponse_de_chat)

    client.post("/api/chat", json={"prompt": "Bonjour"}, headers=ENTETES)

    assert agent_double.demandes == []


def test_une_reponse_sans_source_expose_une_liste_vide(client, monkeypatch, intention):
    intention("CHAT")
    monkeypatch.setattr(routeur_chat.orchestrator, "run", _reponse_de_chat)

    corps = client.post("/api/chat", json={"prompt": "Bonjour"}, headers=ENTETES).json()

    assert corps["status"] == "success"
    assert corps["sources"] == []


# --- Passerelle /v1 ------------------------------------------------------------

def test_le_modele_arena_fresh_est_propose_aux_interfaces(client):
    modeles = [m["id"] for m in client.get("/v1/models", headers=ENTETES).json()["data"]]

    assert "usman-fresh" in modeles


def test_arena_fresh_appelle_l_agent_et_cite_ses_sources(client, agent_double):
    res = client.post("/v1/chat/completions",
                      json={"model": "usman-fresh",
                            "messages": [{"role": "user", "content": "question"}]},
                      headers=ENTETES)

    contenu = res.json()["choices"][0]["message"]["content"]
    # Les numéros [1] restent : ils disent sur quelle source repose l'affirmation.
    assert "Python 3.14 est la dernière version [1]." in contenu
    # La liste d'adresses, elle, n'apparaît que si on la réclame.
    assert "https://exemple.test/py" not in contenu
    assert agent_double.demandes == ["question"]


def test_arena_fresh_donne_ses_adresses_quand_on_les_reclame(client, agent_double):
    res = client.post("/v1/chat/completions",
                      json={"model": "usman-fresh",
                            "messages": [{"role": "user", "content": "question, avec les sources"}]},
                      headers=ENTETES)

    contenu = res.json()["choices"][0]["message"]["content"]
    assert "**Sources**" in contenu
    assert "https://exemple.test/py" in contenu


def test_arena_core_aiguille_aussi_vers_l_agent(client, agent_double, intention):
    intention("FRESH_INFO")

    res = client.post("/v1/chat/completions",
                      json={"model": "usman-chat",
                            "messages": [{"role": "user", "content": "question"}]},
                      headers=ENTETES)

    contenu = res.json()["choices"][0]["message"]["content"]
    assert "Python 3.14 est la dernière version [1]." in contenu
    assert "**Sources**" not in contenu, "la liste d'adresses sort sans avoir été demandée"
    assert agent_double.demandes == ["question"]


def test_la_classification_n_est_pas_refaite_par_la_passerelle(client, agent_double, monkeypatch):
    """Elle coûte un appel au modèle : la refaire par requête serait du gaspillage."""
    appels = []

    async def _classer(user_input):
        appels.append(user_input)
        return "FRESH_INFO"

    monkeypatch.setattr(routeur_chat.orchestrator, "analyze_intent", _classer)

    client.post("/v1/chat/completions",
                json={"model": "usman-chat",
                      "messages": [{"role": "user", "content": "question"}]},
                headers=ENTETES)

    assert len(appels) == 1, f"classification faite {len(appels)} fois"


class TestControleDate:
    """Le tri ne peut pas dépendre d'un modèle qui ignore l'année en cours.

    Cas réel, mesuré le 2026-08-26 sur la machine du propriétaire : à
    « qui a gagné la coupe du monde 2026 », le chat a répondu *« je n'ai pas les
    informations récentes »* au lieu d'aller chercher. Le modèle classeur avait
    répondu `CHAT` — une réponse valide, et fausse : il ne peut pas savoir que
    2026 est postérieur à son entraînement.
    """

    UN_JOUR_DE_2026 = datetime.date(2026, 8, 26)

    @pytest.mark.parametrize("question", [
        "qui a gagner la coupe du monde 2026",
        "quels sont les résultats des élections de 2027",
        "quel est le prix du baril en 2026",
    ])
    def test_une_annee_a_venir_declenche_la_verification(self, question):
        assert OrchestratorAgent.exige_verification(question, self.UN_JOUR_DE_2026) is True

    @pytest.mark.parametrize("question", [
        "qui a gagné la coupe du monde 1998",
        "que s'est-il passé en 1789",
        "qui est le vainqueur du tour de france 2019",
    ])
    def test_une_annee_passee_ne_declenche_rien(self, question):
        """Un fait daté et acquis n'a rien à aller chercher sur le web."""
        assert OrchestratorAgent.exige_verification(question, self.UN_JOUR_DE_2026) is False

    @pytest.mark.parametrize("question", [
        "qui a gagné la coupe du monde",
        "quelle est la dernière version de python",
        "qui est le président du sénégal",
        "combien coûte un billet pour dakar",
    ])
    def test_un_etat_courant_sans_annee_declenche_la_verification(self, question):
        assert OrchestratorAgent.exige_verification(question, self.UN_JOUR_DE_2026) is True

    @pytest.mark.parametrize("question", [
        "explique-moi la relativité",
        "traduis bonjour en wolof",
        "écris une fonction python qui trie une liste",
    ])
    def test_une_question_ordinaire_passe_par_le_modele(self, question):
        """Le contrôle daté ne doit pas rafler tout le trafic."""
        assert OrchestratorAgent.exige_verification(question, self.UN_JOUR_DE_2026) is False

    def test_la_date_vient_de_l_horloge_et_non_du_modele(self):
        """La même question bascule selon l'année réelle, sans toucher au modèle."""
        question = "qui a gagné la coupe du monde 2026"
        assert OrchestratorAgent.exige_verification(question, datetime.date(2026, 1, 1)) is True
        assert OrchestratorAgent.exige_verification(question, datetime.date(2030, 1, 1)) is False


@pytest.mark.asyncio
async def test_le_controle_date_court_circuite_le_modele():
    """`analyze_intent` ne doit même pas interroger le modèle sur ces questions."""
    appels = []

    class ProviderQuiCompte:
        async def generate(self, prompt, **kw):
            appels.append(prompt)
            return "CHAT"

    orchestrateur = OrchestratorAgent(provider=ProviderQuiCompte())
    intention = await orchestrateur.analyze_intent("qui a gagné la coupe du monde 2026")

    assert intention == "FRESH_INFO"
    assert appels == [], "le modèle a été interrogé alors que la date suffisait"


class TestFormulationsReprisesDeSaer:
    """Sa liste de mots-clés web attrapait des cas que la nôtre manquait.

    Mesuré le 2026-08-26 : « quelle est la population de la France » recevait
    une réponse de mémoire — le modèle a répondu « environ 67 millions », sans
    rien vérifier. Sa branche `saer-video-wip` classait cette question en WEB.
    """

    AUJOURD_HUI = datetime.date(2026, 8, 26)

    @pytest.mark.parametrize("question", [
        "quelle est la population de france",
        "qui est le meilleur joueur du monde",
        "qui a gagné la coupe du monde",
        "donne-moi les dernières nouvelles",
        "cherche sur le web le prix du ciment",
    ])
    def test_ces_questions_partent_verifier(self, question):
        assert OrchestratorAgent.exige_verification(question, self.AUJOURD_HUI) is True

    @pytest.mark.parametrize("question", [
        "combien font deux plus deux",
        "explique-moi comment fonctionne un moteur",
        "écris une fonction qui trie une liste",
    ])
    def test_elargir_la_liste_ne_rafle_pas_tout(self, question):
        """Un « combien » nu resterait une question ordinaire : il n'est pas repris."""
        assert OrchestratorAgent.exige_verification(question, self.AUJOURD_HUI) is False


class TestQuestionsPersonnelles:
    """« qui suis-je » est partie sur Internet. Mesuré le 2026-08-26.

    Le modèle classeur a répondu `FRESH_INFO`, la question a fait le tour du web
    pendant une trentaine de secondes, et la réponse a été « les sources ne
    contiennent aucune information qui réponde à la question ». La réponse était
    dans la mémoire du système depuis le début.
    """

    @pytest.mark.parametrize("question", [
        "qui suije",
        "qui suis-je",
        "qui es-tu",
        "quel est mon nom",
        "comment tu t'appelles",
    ])
    def test_ces_questions_ne_partent_jamais_sur_le_web(self, question):
        assert OrchestratorAgent.question_personnelle(question) is True

    @pytest.mark.parametrize("question", [
        "qui est le président du sénégal",
        "qui a gagné la coupe du monde 2026",
        "quelle est la population du sénégal",
    ])
    def test_une_question_sur_quelqu_un_d_autre_n_est_pas_personnelle(self, question):
        """Le garde-fou doit être étroit : il ne doit pas rafler l'actualité."""
        assert OrchestratorAgent.question_personnelle(question) is False

    @pytest.mark.asyncio
    async def test_le_modele_classeur_n_est_meme_pas_interroge(self):
        """Deux coûts supprimés d'un coup : l'appel de tri, et le tour du web."""
        appels = []

        class ProviderQuiCompte:
            async def generate(self, prompt, **kw):
                appels.append(prompt)
                return "FRESH_INFO"

        orchestrateur = OrchestratorAgent(provider=ProviderQuiCompte())
        intention = await orchestrateur.analyze_intent("qui suis-je")

        assert intention == "CHAT"
        assert appels == [], "le modèle a été interrogé sur l'identité du propriétaire"


class TestLaDateNEstPasUneRechercheWeb:
    """« Aujourd'hui c'est quand » partait chercher sur le web.

    **Mesure du 15/09/2026, sur le telephone du proprietaire.** La question
    est partie en `FRESH_INFO`, le modele a recu une source `bfmtv.com`, et a
    repondu : *« Les sources fournies ne mentionnent pas la date du jour. Je
    ne peux donc pas repondre a la question. »*

    La cause : « aujourd'hui » figure dans `FORMULATIONS_COURANTES` comme
    QUALIFICATIF de fraicheur — « qui est president aujourd'hui » a bien
    besoin du web. Dans cette phrase-ci, « aujourd'hui » est le SUJET. Le web
    ne sait pas quel jour on est chez lui ; l'horloge de la machine, si, et
    `apps/backend/prompts.py` met deja cette date dans le prompt du chemin
    `CHAT`.

    Troisieme detournement de `FORMULATIONS_COURANTES` apres le courrier et
    la finance (31/08/2026), et la meme parade : un controle deterministe
    place AVANT le controle date.
    """

    def test_la_question_du_proprietaire_ne_part_plus_au_web(self):
        """Le cas exact de la capture d'ecran."""
        assert OrchestratorAgent.demande_la_date("Aujourd'hui c'est quand")

    @pytest.mark.parametrize("question", [
        "on est quel jour",
        "quel jour sommes-nous",
        "quelle est la date",
        "c'est quoi la date du jour",
        "on est le combien",
        "quelle heure est-il",
    ])
    def test_les_autres_facons_de_demander_le_jour(self, question):
        assert OrchestratorAgent.demande_la_date(question)

    @pytest.mark.parametrize("question", [
        "quelle est la date de livraison du chantier",
        "quel jour tu livres le BA13",
        "quelle heure ouvre le magasin demain",
        "quelle est la date de la coupe du monde",
    ])
    def test_une_date_qui_n_est_pas_LA_date_n_est_pas_prise(self, question):
        """Phrase ENTIERE, jamais un `in` — sinon ce controle volerait au
        metier toutes ses questions de planning."""
        assert not OrchestratorAgent.demande_la_date(question)

    def test_l_apostrophe_du_telephone_ne_change_rien(self):
        """Le clavier insere U+2019, ce fichier ecrit U+0027."""
        assert OrchestratorAgent.demande_la_date("Aujourd’hui c’est quand")


class TestLApostropheTypographiqueNeDesarmePlusLaVerification:
    """Un defaut silencieux, trouve en cherchant le precedent.

    **Mesure du 15/09/2026.** `FORMULATIONS_COURANTES` est ecrit avec
    l'apostrophe droite `'` (U+0027). Le clavier d'un telephone insere
    l'apostrophe typographique `’` (U+2019). Consequence : « quel temps
    fait-il aujourd'hui » tape sur un telephone ne declenchait AUCUNE
    verification, et partait repondre de memoire.

    Ce defaut ne se voit pas : la reponse arrive, elle a l'air normale, et
    rien ne dit qu'elle n'a rien verifie. C'est exactement ce que la regle 2
    du module veut empecher.
    """

    def test_la_meteo_du_jour_declenche_la_verification_dans_les_deux_graphies(self):
        for apostrophe in ("'", "’"):
            question = f"quel temps fait-il aujourd{apostrophe}hui"
            assert OrchestratorAgent.exige_verification(question), question

    def test_une_annee_future_reste_detectee(self):
        """Le premier cas de `exige_verification` n'a pas bouge."""
        futur = datetime.date(2026, 9, 15)
        assert OrchestratorAgent.exige_verification(
            "resultats de 2027", aujourd_hui=futur)

    def test_une_annee_passee_ne_declenche_toujours_rien(self):
        futur = datetime.date(2026, 9, 15)
        assert not OrchestratorAgent.exige_verification(
            "qui a gagne la coupe du monde 1998", aujourd_hui=futur)
