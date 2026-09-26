"""Une question posée par ARENA revient à l'agent qui l'a posée — quel qu'il soit.

**Pourquoi ce fichier existe séparément.** Le premier correctif du 20/09/2026
ne regardait que les trois questions du destinataire d'un devis. Le
propriétaire a refusé ce périmètre :

    « si tu le règles seulement ici, sur d'autres sujets il peut répéter cette
    hallucination — tu dois régler le fond du problème, pas ce problème que tu
    as vu seulement »

Il avait raison. Au moins quatre chemins réclament une information et
repartaient ensuite au classeur d'intention : le devis, le courrier, l'analyse
vidéo, la fiche personnage. Ce fichier couvre le mécanisme qui vaut pour tous.
"""
from __future__ import annotations

import asyncio

import pytest

from core.executive import question_en_attente as q


@pytest.fixture(autouse=True)
def memoire_vierge():
    q.tout_oublier()
    yield
    q.tout_oublier()


# --- Lire ce qu'un agent réclame --------------------------------------------

def test_le_statut_a_la_racine_est_lu() -> None:
    """La forme de `agents/email/email_agent.py`."""
    resultat = {"statut": "INCOMPLET", "manquants": ["destinataire", "sujet"]}
    assert q.champs_reclames(resultat) == ("destinataire", "sujet")


def test_le_statut_imbrique_est_lu() -> None:
    """La forme de `agents/plaquiste` : le statut vit sous `document`."""
    resultat = {"agent": "plaquiste", "response": "...",
                "document": {"statut": "INCOMPLET", "manquants": ["client", "lieu"]}}
    assert q.champs_reclames(resultat) == ("client", "lieu")


def test_un_statut_qui_reclame_sans_nommer_rend_un_tuple_vide() -> None:
    """Vide et `None` disent deux choses différentes.

    Un tuple vide : « je réclame quelque chose, sans savoir le nommer ».
    `None` : « je ne réclame rien ». Les confondre ferait soit oublier une
    question posée, soit en inventer une.
    """
    assert q.champs_reclames({"statut": "A_COMPLETER"}) == ()


@pytest.mark.parametrize("resultat", [
    {"statut": "SUCCESS", "preuve": "x"},
    {"statut": "FAILED", "message": "non"},
    {"response": "bonjour"},
    {}, None, "texte", 42,
])
def test_ce_qui_ne_reclame_rien_ne_retient_rien(resultat) -> None:
    assert q.champs_reclames(resultat) is None


def test_la_recherche_ne_descend_pas_indefiniment() -> None:
    """Le routage ne doit pas dépendre de la profondeur d'un dictionnaire."""
    profond = {"a": {"b": {"c": {"d": {"statut": "INCOMPLET"}}}}}
    assert q.champs_reclames(profond) is None


# --- Retenir, relire, oublier -----------------------------------------------

def test_une_question_posee_est_retenue_avec_son_agent() -> None:
    assert q.noter("s1", "EMAIL", {"statut": "INCOMPLET", "manquants": ["sujet"]})

    attente = q.en_attente("s1")
    assert attente is not None
    assert attente.intention == "EMAIL"
    assert attente.champs == ("sujet",)


def test_un_tour_qui_ne_demande_rien_efface_ce_qui_attendait() -> None:
    """Sans cet effacement, une question déjà répondue continuerait
    d'aspirer ses phrases."""
    q.noter("s1", "EMAIL", {"statut": "INCOMPLET", "manquants": ["sujet"]})

    assert not q.noter("s1", "EMAIL", {"statut": "SUCCESS", "preuve": "envoye"})
    assert q.en_attente("s1") is None


def test_une_question_perimee_n_attend_plus() -> None:
    q.noter("s1", "EMAIL", {"statut": "INCOMPLET"}, maintenant=1000.0)

    encore_bon = 1000.0 + q.DELAI_DE_VALIDITE_SECONDES - 1
    trop_tard = 1000.0 + q.DELAI_DE_VALIDITE_SECONDES + 1
    assert q.en_attente("s1", maintenant=encore_bon) is not None
    assert q.en_attente("s1", maintenant=trop_tard) is None


def test_les_sessions_ne_se_melangent_pas() -> None:
    q.noter("s1", "EMAIL", {"statut": "INCOMPLET"})
    q.noter("s2", "PLAQUISTE", {"statut": "INCOMPLET"})

    assert q.en_attente("s1").intention == "EMAIL"
    assert q.en_attente("s2").intention == "PLAQUISTE"
    assert q.en_attente("s3") is None


def test_la_memoire_reste_bornee() -> None:
    """Un serveur qui tourne des mois ne garde pas une entrée par session."""
    for numero in range(q.SESSIONS_MAX + 50):
        q.noter(f"s{numero}", "EMAIL", {"statut": "INCOMPLET"},
                maintenant=1000.0 + numero)

    assert len(q._ATTENTES) <= q.SESSIONS_MAX
    # Les plus recentes survivent, les plus anciennes partent.
    assert q.en_attente(f"s{q.SESSIONS_MAX + 49}", maintenant=1000.0) is not None
    assert q.en_attente("s0", maintenant=1000.0) is None


@pytest.mark.parametrize("session", ["", None])
def test_une_session_sans_nom_ne_retient_rien(session) -> None:
    assert not q.noter(session, "EMAIL", {"statut": "INCOMPLET"})


# --- Le routage, pour un agent qui n'est pas le devis -----------------------

def test_la_reponse_revient_a_l_agent_qui_a_pose_la_question(monkeypatch) -> None:
    """Le cas du devis, rejoué sur le COURRIER.

    C'est la preuve que le correctif n'est pas resté cantonné au devis : le
    même mot « Medina », après une question du courrier, revient au courrier.
    """
    from apps.backend.routers import chat as module_chat

    classeur = []

    async def classeur_interdit(*args, **kwargs):
        classeur.append(args)
        return "FRESH_INFO"

    vus = []
    reclame = {"statut": "INCOMPLET", "manquants": ["destinataire", "sujet"]}

    async def faux_aiguillage(requete, intention):
        vus.append(intention)
        return reclame if intention == "EMAIL" else {"response": "ok"}

    monkeypatch.setattr(module_chat.orchestrator, "analyze_intent", classeur_interdit)
    monkeypatch.setattr(module_chat, "_aiguiller", faux_aiguillage)

    asyncio.run(module_chat.dispatch_request(
        module_chat.ChatRequest(prompt="écris un mail", session_id="s1"), intent="EMAIL"))
    asyncio.run(module_chat.dispatch_request(
        module_chat.ChatRequest(prompt="Medina", session_id="s1", message_actuel="Medina")))

    assert vus == ["EMAIL", "EMAIL"]
    assert classeur == [], "le classeur a ete appele alors qu'une question attendait"


def test_un_changement_de_sujet_manifeste_libere_la_question(monkeypatch) -> None:
    from apps.backend.routers import chat as module_chat

    q.noter("s1", "EMAIL", {"statut": "INCOMPLET", "manquants": ["sujet"]})

    assert module_chat.intention_dune_reponse_attendue([], "Bonjour", "s1") is None
    # Et la question est LIBEREE : il est passe a autre chose, elle ne doit
    # pas ressurgir au tour suivant.
    assert q.en_attente("s1") is None


def test_sans_question_retenue_le_classeur_garde_la_main() -> None:
    from apps.backend.routers import chat as module_chat

    assert module_chat.intention_dune_reponse_attendue([], "Medina", "s-inconnue") is None


def test_tout_controle_avant_l_espace_libere_la_question() -> None:
    """La liste des controles qui priment suit `analyze_intent`, sans recopie oubliee.

    Mesure du 26/09/2026 : `demande_executive` et `demande_la_date` avaient
    rejoint `analyze_intent` apres que `CONTROLES_QUI_PRIMENT` avait ete
    ecrite, et n'y avaient jamais ete ajoutes. Une question de devis en
    attente avalait alors « devrions-nous accepter ce contrat ? ».
    """
    import inspect
    import re

    from agents.orchestrator.orchestrator_agent import OrchestratorAgent
    from apps.backend.routers import chat as module_chat

    source = inspect.getsource(OrchestratorAgent.analyze_intent)
    avant_l_espace = source.split("if espace")[0]
    appeles = re.findall(r"if self\.(\w+)\(user_input\)", avant_l_espace)
    # `exige_verification` est exclu volontairement : « aujourd'hui » est
    # aussi une reponse (« le chantier commence aujourd'hui »).
    attendus = [nom for nom in appeles if nom != "exige_verification"]

    assert attendus, "l'analyse de la source d'analyze_intent n'a rien trouve"
    assert sorted(attendus) == sorted(module_chat.CONTROLES_QUI_PRIMENT)


def test_une_decision_d_affaires_libere_la_question() -> None:
    from apps.backend.routers import chat as module_chat

    q.noter("s1", "PLAQUISTE", {"statut": "INCOMPLET", "manquants": ["lieu"]})

    assert module_chat.intention_dune_reponse_attendue(
        [], "devrions-nous accepter ce contrat ?", "s1") is None
