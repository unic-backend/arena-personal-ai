"""Les agents travaillent ensemble sur une demande qui en nomme plusieurs.

Demande du proprietaire, 26/09/2026 : « tous les agents doivent pouvoir
travailler ensemble — aucun agent n'est prisonnier de ses capacites ».
Mesure avant ce correctif : chaque demande a deux metiers partait chez UN
agent, qui ne faisait que sa part. Ces tests passent par le vrai
`dispatch_request` et la vraie route du telephone ; seuls le classeur et les
agents sont remplaces, pour ne pas dependre d'un modele.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from apps.backend.routers import chat as module_chat
from core.agent import equipe
from core.executive import question_en_attente

CLE = "cle-de-test-equipe"
DEVIS = "Devis DV-7 : 30 m2 de cloison, 360 000 F."
PHRASE = "fais un devis de 30 m2 de cloison et envoie-le par mail à khady@exemple.com"


@pytest.fixture(autouse=True)
def etat_vierge():
    equipe.oublier_les_plans()
    question_en_attente.tout_oublier()
    yield
    equipe.oublier_les_plans()
    question_en_attente.tout_oublier()


@pytest.fixture
def agents(monkeypatch):
    """Classeur et agents scriptes ; le reste du chemin est le vrai."""
    async def classer(texte, espace=None):
        if texte.startswith("envoie"):
            return "EMAIL"
        return "PLAQUISTE"

    appels = []

    async def aiguiller(requete, intention):
        appels.append((intention, requete.prompt))
        texte = DEVIS if intention == "PLAQUISTE" else "Mail pret, a confirmer."
        return {"status": "success", "agent": intention, "response": texte,
                "intent": intention}

    monkeypatch.setattr(module_chat.orchestrator, "analyze_intent", classer)
    monkeypatch.setattr(module_chat, "_aiguiller", aiguiller)
    return appels


async def test_dispatch_fait_travailler_le_devis_puis_le_courrier(agents):
    rendu = await module_chat.dispatch_request(
        module_chat.ChatRequest(prompt=PHRASE, session_id=f"s-{uuid4()}"),
        consigner_le_tour=False)

    assert [intention for intention, _ in agents] == ["PLAQUISTE", "EMAIL"]
    assert DEVIS in agents[1][1], "l'agent courrier doit recevoir le devis"
    assert DEVIS in rendu["response"] and "Mail pret" in rendu["response"]


async def test_une_reponse_attendue_ne_se_decoupe_pas(agents):
    session = f"s-{uuid4()}"
    question_en_attente.noter(session, "PLAQUISTE",
                              {"statut": "INCOMPLET", "manquants": ["lieu"]})

    await module_chat.dispatch_request(
        module_chat.ChatRequest(prompt=PHRASE, session_id=session),
        intent="PLAQUISTE", consigner_le_tour=False)

    assert [intention for intention, _ in agents] == ["PLAQUISTE"]


def test_le_telephone_fait_travailler_l_equipe(agents, monkeypatch):
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE)
    securite.limiteur._passages.clear()
    client = TestClient(main.app, raise_server_exceptions=False)

    client.post("/agent/stream", headers={"Authorization": f"Bearer {CLE}"}, json={
        "text": PHRASE, "conversation_id": f"conv-{uuid4()}", "run_id": f"run-{uuid4()}"})

    assert [intention for intention, _ in agents] == ["PLAQUISTE", "EMAIL"]


# --- Plus d'etapes que la chaine courte : le projet, jamais un seul agent ---------

PHRASE_LONGUE = ("lis ce PDF puis résume-le puis fais un tableur "
                 "puis envoie-le par mail à khady@exemple.com")


async def test_une_chaine_trop_longue_ne_part_plus_chez_un_seul_agent(agents):
    """**Le defaut mesure le 30/09/2026, apres les quatre chantiers.** Cette
    phrase se decoupe en QUATRE etapes, une de plus que la chaine courte : le
    plan etait jete et le Plaquiste repondait seul, sans que rien ne le dise.
    Elle doit maintenant partir au projet (DEC-0197).
    """
    await module_chat.dispatch_request(
        module_chat.ChatRequest(prompt=PHRASE_LONGUE, session_id=f"s-{uuid4()}"),
        consigner_le_tour=False)

    assert [intention for intention, _ in agents] == ["EQUIPE"]
    assert agents[0][1] == PHRASE_LONGUE, "le projet recoit la demande ENTIERE"


async def test_le_classement_dune_chaine_trop_longue_rend_equipe():
    """La PWA classe AVANT d'appeler `dispatch_request` : sans cette regle
    la, elle envoyait deja l'intention d'un seul metier."""
    assert await module_chat.classer_la_demande(
        PHRASE_LONGUE, [], f"s-{uuid4()}") == "EQUIPE"


async def test_une_chaine_trop_longue_arrive_au_mecanisme_de_projet(monkeypatch):
    """La garde qui compte : l'intention EQUIPE ne sert a rien si le vrai
    aiguillage ne conduit pas au projet. Ici `_aiguiller` n'est PAS remplace.
    """
    recu = {}

    async def projet(texte, session_id, demande=None):
        recu["texte"] = texte
        return {"status": "success", "agent": "Projet(PLAQUISTE)",
                "response": "**Projet reparti** — mené par PLAQUISTE"}

    async def classer(texte, espace=None):
        return "PLAQUISTE"

    monkeypatch.setattr(module_chat, "_travail_d_equipe", projet)
    monkeypatch.setattr(module_chat.orchestrator, "analyze_intent", classer)

    rendu = await module_chat.dispatch_request(
        module_chat.ChatRequest(prompt=PHRASE_LONGUE, session_id=f"s-{uuid4()}"),
        consigner_le_tour=False)

    assert recu.get("texte") == PHRASE_LONGUE
    assert "Projet reparti" in rendu["response"]


async def test_une_reponse_attendue_longue_revient_a_son_agent(agents):
    """Une reponse a une question d'ARENA n'escalade jamais, meme si elle
    enchaine des « puis » — elle appartient a l'agent qui a demande."""
    session = f"s-{uuid4()}"
    question_en_attente.noter(session, "PLAQUISTE",
                              {"statut": "INCOMPLET", "manquants": ["lieu"]})

    await module_chat.dispatch_request(
        module_chat.ChatRequest(prompt=PHRASE_LONGUE, session_id=session),
        intent="PLAQUISTE", consigner_le_tour=False)

    assert [intention for intention, _ in agents] == ["PLAQUISTE"]


async def test_une_chaine_trop_longue_escalade_meme_si_l_appelant_a_deja_classe(agents):
    """`dispatch_request` refait la verification : ses cinq appelants ne
    classent pas tous par `classer_la_demande`, et l'un d'eux qui passerait
    l'intention d'un seul metier ramenerait exactement l'abandon silencieux.
    """
    await module_chat.dispatch_request(
        module_chat.ChatRequest(prompt=PHRASE_LONGUE, session_id=f"s-{uuid4()}"),
        intent="PLAQUISTE", consigner_le_tour=False)

    assert [intention for intention, _ in agents] == ["EQUIPE"]
