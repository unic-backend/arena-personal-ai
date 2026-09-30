"""`dispatch_request` journalise durablement ce qu'il a reellement decide.

Chantier « journal de routage » (DEC-0192, DEC-0193 : « la disponibilite
reelle des capacites et le journal de routage sont deux chantiers separes »).
Ces tests passent par le vrai `dispatch_request` — seuls le classeur et les
agents sont remplaces, meme methode que `tests/test_agents_travaillent_ensemble.py` —
et lisent le journal reel, jamais un double qui rejouerait sa propre logique.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from apps.backend.routers import chat as module_chat
from core.agent import equipe
from core.executive import question_en_attente
from core.observabilite.routage import JournalDeRoutage

PHRASE_SIMPLE = "fais-moi un devis de 30 m2 de cloison"
PHRASE_CHAINE = "fais un devis de 30 m2 de cloison et envoie-le par mail à khady@exemple.com"


@pytest.fixture(autouse=True)
def etat_vierge():
    equipe.oublier_les_plans()
    question_en_attente.tout_oublier()
    yield
    equipe.oublier_les_plans()
    question_en_attente.tout_oublier()


@pytest.fixture
def journal(tmp_path, monkeypatch) -> JournalDeRoutage:
    """Un journal isole — ces tests ne touchent jamais data/database/memory.db."""
    reel = JournalDeRoutage(db_path=str(tmp_path / "routage.db"))
    monkeypatch.setattr(module_chat, "journal_routage", reel)
    return reel


@pytest.fixture
def agent_unique(monkeypatch):
    """Une seule demande, un seul agent — le classeur ne coupe jamais en deux."""
    async def classer(texte, espace=None):
        return "PLAQUISTE"

    async def aiguiller(request, intention):
        return {"status": "success", "agent": "PLAQUISTE",
                "response": "Devis DV-7 pret.", "intent": intention}

    monkeypatch.setattr(module_chat.orchestrator, "analyze_intent", classer)
    monkeypatch.setattr(module_chat, "_aiguiller", aiguiller)


@pytest.fixture
def agents_en_chaine(monkeypatch):
    """Devis puis courrier — la vraie coupe de `core.agent.equipe`."""
    async def classer(texte, espace=None):
        if texte.startswith("envoie"):
            return "EMAIL"
        return "PLAQUISTE"

    async def aiguiller(request, intention):
        texte = "Devis DV-7 pret." if intention == "PLAQUISTE" else "Mail pret, a confirmer."
        return {"status": "success", "agent": intention, "response": texte,
                "intent": intention}

    monkeypatch.setattr(module_chat.orchestrator, "analyze_intent", classer)
    monkeypatch.setattr(module_chat, "_aiguiller", aiguiller)


async def test_une_demande_simple_journalise_sa_phrase_son_intention_et_son_agent(
        agent_unique, journal):
    session = f"s-{uuid4()}"

    await module_chat.dispatch_request(
        module_chat.ChatRequest(prompt=PHRASE_SIMPLE, session_id=session),
        consigner_le_tour=False)

    ligne = journal.dernieres()[0]
    assert ligne.phrase == PHRASE_SIMPLE
    assert ligne.intention == "PLAQUISTE"
    assert ligne.agents == ["PLAQUISTE"]
    assert ligne.etapes == []
    assert ligne.horodatage


async def test_un_intent_deja_classe_est_journalise_tel_quel(agent_unique, journal):
    """`intent` transmis par l'appelant (DEC-13/09) : le journal garde CETTE
    intention, sans reclasser."""
    await module_chat.dispatch_request(
        module_chat.ChatRequest(prompt=PHRASE_SIMPLE, session_id=f"s-{uuid4()}"),
        intent="PLAQUISTE", consigner_le_tour=False)

    assert journal.dernieres()[0].intention == "PLAQUISTE"


async def test_une_chaine_journalise_les_etapes_reellement_executees(
        agents_en_chaine, journal):
    await module_chat.dispatch_request(
        module_chat.ChatRequest(prompt=PHRASE_CHAINE, session_id=f"s-{uuid4()}"),
        consigner_le_tour=False)

    ligne = journal.dernieres()[0]
    assert ligne.phrase == PHRASE_CHAINE
    assert ligne.intention == "EMAIL"
    assert ligne.agents == ["PLAQUISTE", "EMAIL"]
    assert ligne.etapes == [
        {"intention": "PLAQUISTE", "agent": "PLAQUISTE", "status": "success"},
        {"intention": "EMAIL", "agent": "EMAIL", "status": "success"},
    ]


async def test_une_chaine_arretee_par_un_echec_ne_journalise_que_ce_qui_a_tourne(
        monkeypatch, journal):
    """La deuxieme etape echoue : l'equipe s'arrete, et le journal ne porte
    jamais une etape qui n'a pas tourne."""
    async def classer(texte, espace=None):
        return "EMAIL" if texte.startswith("envoie") else "PLAQUISTE"

    async def aiguiller(request, intention):
        if intention == "EMAIL":
            return {"status": "error", "agent": "EMAIL", "response": "", "intent": intention}
        return {"status": "success", "agent": "PLAQUISTE",
                "response": "Devis DV-7 pret.", "intent": intention}

    monkeypatch.setattr(module_chat.orchestrator, "analyze_intent", classer)
    monkeypatch.setattr(module_chat, "_aiguiller", aiguiller)

    await module_chat.dispatch_request(
        module_chat.ChatRequest(prompt=PHRASE_CHAINE, session_id=f"s-{uuid4()}"),
        consigner_le_tour=False)

    ligne = journal.dernieres()[0]
    assert ligne.agents == ["PLAQUISTE", "EMAIL"]
    assert [etape["status"] for etape in ligne.etapes] == ["success", "error"]


async def test_une_reponse_attendue_journalise_le_seul_agent_qui_l_a_posee(
        agents_en_chaine, journal):
    """Une reponse a une question d'ARENA ne se decoupe jamais (regle deja en
    place) : le journal doit refleter cette absence de chaine, pas en inventer
    une."""
    session = f"s-{uuid4()}"
    question_en_attente.noter(session, "PLAQUISTE",
                              {"statut": "INCOMPLET", "manquants": ["lieu"]})

    await module_chat.dispatch_request(
        module_chat.ChatRequest(prompt=PHRASE_CHAINE, session_id=session),
        intent="PLAQUISTE", consigner_le_tour=False)

    ligne = journal.dernieres()[0]
    assert ligne.agents == ["PLAQUISTE"]
    assert ligne.etapes == []


async def test_deux_demandes_du_meme_appelant_ecrivent_deux_lignes(agent_unique, journal):
    await module_chat.dispatch_request(
        module_chat.ChatRequest(prompt="un devis", session_id=f"s-{uuid4()}"),
        consigner_le_tour=False)
    await module_chat.dispatch_request(
        module_chat.ChatRequest(prompt="un autre devis", session_id=f"s-{uuid4()}"),
        consigner_le_tour=False)

    assert len(journal.dernieres()) == 2


async def test_l_ecriture_du_journal_n_empeche_pas_la_reponse(
        agent_unique, journal, monkeypatch):
    """Meme discipline que les journaux voisins : une panne d'ecriture ne doit
    jamais empecher la reponse de partir."""
    def casse(*_a, **_k):
        raise RuntimeError("disque plein")

    monkeypatch.setattr(journal, "_connexion", casse)

    rendu = await module_chat.dispatch_request(
        module_chat.ChatRequest(prompt=PHRASE_SIMPLE, session_id=f"s-{uuid4()}"),
        consigner_le_tour=False)

    assert "Devis DV-7 pret." in rendu["response"]


async def test_une_chaine_trop_longue_journalise_l_escalade_vers_le_projet(
        monkeypatch, journal):
    """DEC-0197 : quatre etapes explicites partent au projet, et le journal
    garde l'intention REELLEMENT retenue — « EQUIPE », pas le metier du
    premier morceau. C'est ce qui rend l'escalade verifiable apres coup."""
    phrase = ("lis ce PDF puis résume-le puis fais un tableur "
              "puis envoie-le par mail à khady@exemple.com")

    async def classer(texte, espace=None):
        return "PLAQUISTE"

    async def aiguiller(request, intention):
        return {"status": "success", "agent": "Projet(PLAQUISTE)",
                "response": "**Projet reparti** — mené par PLAQUISTE",
                "intent": intention}

    monkeypatch.setattr(module_chat.orchestrator, "analyze_intent", classer)
    monkeypatch.setattr(module_chat, "_aiguiller", aiguiller)

    await module_chat.dispatch_request(
        module_chat.ChatRequest(prompt=phrase, session_id=f"s-{uuid4()}"),
        consigner_le_tour=False)

    ligne = journal.dernieres()[0]
    assert ligne.phrase == phrase
    assert ligne.intention == "EQUIPE"
    assert ligne.agents == ["Projet(PLAQUISTE)"]
