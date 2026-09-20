"""Une réponse à une question d'ARENA n'est pas une nouvelle demande.

**Le défaut, mesuré le 20/09/2026, capture d'écran à l'appui.**

    — Fais moi un devis du nom de khady diop
    — Quel est le nom du client ? Quel est le lieu du chantier ?
      Quelles sont les prestations souhaitées ?
    — Medina
    — « La Médina désigne à l'origine le centre historique d'une ville…
      la ville sainte d'al-Madinah al-Munawwarah… 1 477 023 habitants… »
      (sources : fr.wikipedia.org)

La cause n'était pas la compréhension du modèle. `analyze_intent()` ne lit
**que le message courant** : « Medina » seul ne ressemble à rien d'autre qu'à
une question de culture générale, et la recherche web partait avant que le
moindre code métier ne voie la phrase. La capture du destinataire existait et
fonctionnait — elle n'était jamais atteinte.

Et une fois atteinte, elle révélait un second défaut : la même réponse
remplissait **les trois champs**. Le devis serait parti au nom de « Medina »,
chantier « Medina », objet « Medina ».
"""
from __future__ import annotations

import pytest

from agents.plaquiste.plaquiste_agent import (
    champs_demandes_au_tour_precedent,
    destinataire_annonce,
    destinataire_depuis_l_historique,
)
from apps.backend.routers.chat import intention_dune_reponse_attendue

#: Le message d'ARENA, tel qu'il est apparu sur son téléphone.
QUESTION_TROIS_CHAMPS = (
    "UniC Plaquiste - Devis\n"
    "Merci de bien vouloir nous préciser les informations manquantes.\n"
    "Quel est le nom du client ?\n"
    "Quel est le lieu du chantier ?\n"
    "Quelles sont les prestations souhaitées ?")

CONVERSATION = [
    {"role": "user", "content": "Fais moi un devis du nom de khady diop"},
    {"role": "assistant", "content": QUESTION_TROIS_CHAMPS},
]


# --- Le routage : la question posée garde la main ---------------------------

def test_la_reponse_ne_part_plus_en_recherche_web() -> None:
    """Le cas exact de la capture d'écran."""
    assert intention_dune_reponse_attendue(CONVERSATION, "Medina") == "PLAQUISTE"


@pytest.mark.parametrize("champ, question", [
    ("client", "Quel est le nom du client ?"),
    ("lieu", "Quel est le lieu du chantier ?"),
    ("objet", "Quelles sont les prestations souhaitées ?"),
])
def test_chacune_des_trois_questions_est_reconnue(champ: str, question: str) -> None:
    historique = [{"role": "assistant", "content": question}]
    assert champs_demandes_au_tour_precedent(historique) == [champ]
    assert intention_dune_reponse_attendue(historique, "une réponse") == "PLAQUISTE"


@pytest.mark.parametrize("phrase", [
    "Bonjour",
    "combien de mails aujourd'hui ?",
    "analyse le bitcoin",
])
def test_un_changement_de_sujet_manifeste_passe_devant(phrase: str) -> None:
    """Il a le droit de laisser une question en plan.

    Une salutation, une demande de courrier ou de finance ne se fait pas
    avaler par un devis en cours.
    """
    assert intention_dune_reponse_attendue(CONVERSATION, phrase) is None


def test_sans_question_en_attente_le_classeur_garde_la_main() -> None:
    historique = [{"role": "user", "content": "salut"},
                  {"role": "assistant", "content": "Bonjour."}]
    assert intention_dune_reponse_attendue(historique, "Medina") is None


def test_une_question_deja_repondue_ne_force_plus_rien() -> None:
    """Un tour utilisateur plus récent que la question a consommé celle-ci."""
    historique = CONVERSATION + [
        {"role": "user", "content": "Medina"},
        {"role": "user", "content": "et sinon, la médina de Dakar c'est quoi ?"},
    ]
    assert champs_demandes_au_tour_precedent(historique) == []


def test_un_message_vide_ne_force_rien() -> None:
    assert intention_dune_reponse_attendue(CONVERSATION, "   ") is None


def test_le_branchement_lui_meme_est_couvert(monkeypatch) -> None:
    """Le routage doit être ATTEINT par `dispatch_request`, pas seulement exister.

    Un sabotage coupant l'appel dans `dispatch_request` ne faisait échouer
    aucun test (mesuré le 20/09/2026) : ils appelaient tous la fonction en
    direct. Le défaut serait revenu sans un bruit — c'est exactement la
    forme qu'il avait la première fois.
    """
    import asyncio

    from apps.backend.routers import chat as module_chat

    classeur_appele = []

    async def classeur_interdit(*args, **kwargs):
        classeur_appele.append(args)
        return "FRESH_INFO"          # ce que le vrai classeur répondait

    recu = {}

    async def faux_aiguillage(requete, intention):
        recu["intention"] = intention
        return {"response": "ok", "status": "success"}

    monkeypatch.setattr(module_chat.orchestrator, "analyze_intent", classeur_interdit)
    monkeypatch.setattr(module_chat, "_aiguiller", faux_aiguillage)

    requete = module_chat.ChatRequest(
        prompt="Medina", message_actuel="Medina", history=CONVERSATION)
    asyncio.run(module_chat.dispatch_request(requete))

    assert recu["intention"] == "PLAQUISTE"
    # Et le classeur n'a meme pas ete appele : la question posee tranche
    # avant, sans modele et sans un jeton depense.
    assert classeur_appele == []


# --- La capture : une question, une réponse ---------------------------------

def test_une_reponse_ne_remplit_jamais_trois_champs() -> None:
    """« Medina » ne peut pas être à la fois le client, le lieu et l'objet.

    Un devis au nom de « Medina », chantier « Medina », objet « Medina » est
    un document plausible et faux — exactement ce qu'un statut INCOMPLET
    existe pour empêcher.
    """
    capte = destinataire_depuis_l_historique(CONVERSATION, "Medina")
    assert capte == {}


def test_une_reponse_groupee_va_au_bon_champ() -> None:
    """Deux champs demandés, deux valeurs : chacun prend la sienne, dans
    l'ordre où la question les a posées."""
    historique = [{"role": "assistant",
                   "content": "Quel est le lieu du chantier et les prestations souhaitées ?"}]

    capte = destinataire_depuis_l_historique(
        historique, "Fann Hock, 18 parois de 5,40 x 2,50 m")

    assert capte == {"lieu": "Fann Hock", "objet": "18 parois de 5,40 x 2,50 m"}


def test_les_decimales_francaises_survivent_au_decoupage() -> None:
    """« 5,40 m » n'est pas deux valeurs.

    Le découpage se fait sur une virgule SUIVIE D'UNE ESPACE. Sur la virgule
    seule, « Fann Hock, 18 parois de 5,40 x 2,50 m » donnerait quatre
    morceaux — « 18 parois de 5 », « 40 x 2 », « 50 m » — et le devis
    porterait des dimensions amputées.
    """
    historique = [{"role": "assistant",
                   "content": "Quel est le lieu du chantier et les prestations souhaitées ?"}]

    capte = destinataire_depuis_l_historique(
        historique, "Fann Hock, 18 parois de 5,40 x 2,50 m")

    assert "5,40" in capte["objet"]
    assert "2,50" in capte["objet"]


def test_une_question_seule_capte_sa_reponse() -> None:
    historique = [
        {"role": "user", "content": "fais-moi un devis"},
        {"role": "assistant", "content": "Quel est le lieu du chantier ?"},
    ]
    assert destinataire_depuis_l_historique(historique, "Medina") == {"lieu": "Medina"}


# --- La sortie de secours : la forme étiquetée ------------------------------

def test_la_ligne_etiquetee_remplit_les_trois_champs() -> None:
    """La forme que le message d'ARENA propose doit marcher, mot pour mot.

    Elle se lit sur la phrase du PROPRIÉTAIRE, donc elle fonctionne quelle
    que soit la façon dont le modèle a tourné sa question.
    """
    capte = destinataire_annonce(
        "client : Khady Diop, lieu : Medina, objet : faux plafond sans design")

    assert capte == {"client": "Khady Diop", "lieu": "Medina",
                     "objet": "faux plafond sans design"}


def test_la_virgule_ne_reste_pas_collee_au_nom() -> None:
    """« Khady Diop, » — virgule comprise — serait parti sur le PDF."""
    capte = destinataire_annonce("le client c'est Khady Diop, lieu du chantier : Medina")
    assert capte["client"] == "Khady Diop"


@pytest.mark.parametrize("phrase", [
    "j'ai vu mon client habituel hier",
    "le lieu est beau",
    "Medina",
])
def test_aucune_etiquette_aucune_capture(phrase: str) -> None:
    """Un nom propre mentionné en passant n'a jamais rempli un devis."""
    assert destinataire_annonce(phrase) == {}
