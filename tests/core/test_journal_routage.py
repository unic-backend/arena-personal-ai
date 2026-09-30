"""Le journal du routage : la date, la phrase, l'intention, les agents appeles.

Chantier « journal de routage », annonce separement par DEC-0192 et DEC-0193
(« la disponibilite reelle des capacites et le journal de routage sont deux
chantiers separes »). Trois proprietes portent ces tests :

1. **Le journal ne peut pas contredire l'execution.** `AppelRoute.depuis_dispatch`
   derive tout de ce que `dispatch_request` a reellement rendu — jamais fourni
   a la main.
2. **Aucune detection n'est ajoutee ici.** Une chaine n'est reconnue que si
   `reponse["equipe"]` — deja construit par `core/agent/equipe.py::executer` —
   la porte. Rien n'est recoupe depuis la phrase.
3. **Une ecriture qui echoue ne bloque jamais la reponse**, meme discipline que
   `core/actions/journal.py` et `core/observabilite/plans.py`.
"""
from __future__ import annotations

import pytest

from core.observabilite.fil import nouveau_fil
from core.observabilite.routage import AppelRoute, JournalDeRoutage


@pytest.fixture
def journal(tmp_path) -> JournalDeRoutage:
    return JournalDeRoutage(db_path=str(tmp_path / "routage.db"))


# --------------------------------------------------------------------------
# Une demande simple : un agent, aucune etape
# --------------------------------------------------------------------------

def test_une_demande_simple_enregistre_l_unique_agent_appele(journal):
    appel = AppelRoute.depuis_dispatch(
        "fais-moi un devis de 30 m2", "PLAQUISTE",
        {"status": "success", "agent": "PLAQUISTE", "response": "Devis pret."})

    journal.enregistrer(appel)

    ligne = journal.dernieres()[0]
    assert ligne.phrase == "fais-moi un devis de 30 m2"
    assert ligne.intention == "PLAQUISTE"
    assert ligne.agents == ["PLAQUISTE"]
    assert ligne.etapes == []


def test_une_reponse_sans_agent_n_en_invente_aucun(journal):
    """Un `agent` absent doit rester une liste vide, jamais `[None]` ou `['None']`."""
    appel = AppelRoute.depuis_dispatch("bonjour", "CHAT", {"response": "Bonjour !"})

    journal.enregistrer(appel)

    assert journal.dernieres()[0].agents == []


# --------------------------------------------------------------------------
# Une chaine : les etapes reellement executees, telles que l'equipe les a rendues
# --------------------------------------------------------------------------

def test_une_chaine_enregistre_les_etapes_reellement_executees(journal):
    reponse_equipe = {
        "status": "success",
        "agent": "Equipe(PLAQUISTE -> EMAIL)",
        "intention": "EMAIL",
        "equipe": [
            {"intention": "PLAQUISTE", "agent": "PLAQUISTE", "status": "success"},
            {"intention": "EMAIL", "agent": "EMAIL", "status": "success"},
        ],
    }

    appel = AppelRoute.depuis_dispatch(
        "fais un devis et envoie-le par mail", "EMAIL", reponse_equipe)
    journal.enregistrer(appel)

    ligne = journal.dernieres()[0]
    assert ligne.intention == "EMAIL"
    assert ligne.agents == ["PLAQUISTE", "EMAIL"]
    assert ligne.etapes == [
        {"intention": "PLAQUISTE", "agent": "PLAQUISTE", "status": "success"},
        {"intention": "EMAIL", "agent": "EMAIL", "status": "success"},
    ]


def test_une_chaine_arretee_a_l_echec_n_enregistre_que_ce_qui_a_tourne(journal):
    """`equipe.executer` s'arrete au premier echec : l'etape jamais lancee
    n'a pas a apparaitre ici — la revendiquer serait mentir sur ce qui a
    tourne."""
    reponse_equipe = {
        "status": "error",
        "agent": "Equipe(PLAQUISTE)",
        "intention": "PLAQUISTE",
        "equipe": [
            {"intention": "PLAQUISTE", "agent": "PLAQUISTE", "status": "error"},
        ],
    }

    appel = AppelRoute.depuis_dispatch(
        "fais un devis et envoie-le par mail", "PLAQUISTE", reponse_equipe)

    assert appel.agents == ["PLAQUISTE"]
    assert appel.etapes == [{"intention": "PLAQUISTE", "agent": "PLAQUISTE",
                             "status": "error"}]


def test_une_equipe_vide_se_comporte_comme_une_demande_simple(journal):
    """`equipe` a la cle mais vide (jamais le cas reel) : pas de fausse chaine."""
    appel = AppelRoute.depuis_dispatch(
        "salut", "CHAT", {"agent": "CHAT", "equipe": []})

    assert appel.agents == ["CHAT"]
    assert appel.etapes == []


# --------------------------------------------------------------------------
# La date et la tracabilite
# --------------------------------------------------------------------------

def test_chaque_appel_porte_un_horodatage(journal):
    appel = AppelRoute.depuis_dispatch("salut", "CHAT", {"agent": "CHAT"})
    journal.enregistrer(appel)

    assert journal.dernieres()[0].horodatage


def test_hors_demande_le_fil_reste_absent(journal):
    appel = AppelRoute.depuis_dispatch("salut", "CHAT", {"agent": "CHAT"})
    journal.enregistrer(appel)

    assert journal.dernieres()[0].requete is None


def test_dans_une_demande_le_fil_est_porte(journal):
    with nouveau_fil("demande-du-matin"):
        appel = AppelRoute.depuis_dispatch("salut", "CHAT", {"agent": "CHAT"})
        journal.enregistrer(appel)

    assert journal.dernieres()[0].requete == "demande-du-matin"


def test_une_demande_retrouve_exactement_ses_passages(journal):
    with nouveau_fil("demande-A"):
        journal.enregistrer(AppelRoute.depuis_dispatch("un", "CHAT", {"agent": "CHAT"}))
        journal.enregistrer(AppelRoute.depuis_dispatch("deux", "CHAT", {"agent": "CHAT"}))
    with nouveau_fil("demande-B"):
        journal.enregistrer(AppelRoute.depuis_dispatch("trois", "CHAT", {"agent": "CHAT"}))

    assert len(journal.dernieres(requete_id="demande-A")) == 2
    assert len(journal.dernieres(requete_id="demande-B")) == 1
    assert len(journal.dernieres()) == 3


def test_les_plus_recents_d_abord(journal):
    journal.enregistrer(AppelRoute.depuis_dispatch("un", "CHAT", {"agent": "CHAT"}))
    journal.enregistrer(AppelRoute.depuis_dispatch("deux", "CHAT", {"agent": "CHAT"}))

    assert [ligne.phrase for ligne in journal.dernieres()] == ["deux", "un"]


def test_deux_appels_ont_deux_identifiants(journal):
    premier = AppelRoute.depuis_dispatch("un", "CHAT", {"agent": "CHAT"})
    second = AppelRoute.depuis_dispatch("un", "CHAT", {"agent": "CHAT"})

    assert premier.identifiant != second.identifiant


def test_une_ecriture_impossible_ne_leve_pas(journal, monkeypatch):
    """Perdre la trace d'un routage est regrettable ; empecher la reponse de
    partir a cause de cette trace l'est davantage."""
    def casse(*_a, **_k):
        raise RuntimeError("disque plein")

    monkeypatch.setattr(journal, "_connexion", casse)

    resultat = journal.enregistrer(
        AppelRoute.depuis_dispatch("salut", "CHAT", {"agent": "CHAT"}))

    assert resultat is False


def test_un_rapport_vide_ne_pretend_rien(journal):
    assert journal.dernieres() == []
