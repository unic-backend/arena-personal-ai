"""L'etat de la memoire se mesure, il ne se declare pas.

Trois causes differentes produisent la meme phrase — « il oublie ce qu'on
s'est dit » — et rien ne permettait de savoir laquelle agissait sur
l'hebergeur. Ce module les separe ; ces tests verifient qu'il **mesure** au
lieu de supposer, et qu'une mesure impossible ne devient jamais un zero.
"""
import asyncio
import sqlite3
from datetime import timedelta

import pytest

from core.memory import etat as module_etat
from core.memory.etat import (
    PERSISTANCE_CONFIRMEE,
    PERSISTANCE_INCONNUE,
    PERSISTANCE_PAS_OBSERVEE,
    RECHERCHE_INCONNUE,
    RECHERCHE_PAR_LE_SENS,
    RECHERCHE_PAR_LES_MOTS,
    etat_base,
    etat_fil,
    etat_memoire,
    etat_recherche,
    etat_souvenirs,
)
from core.memory.semantique import EtatEmbeddings


@pytest.fixture
def base(tmp_path):
    """Une vraie base SQLite, jetable, avec les deux tables qui comptent."""
    chemin = tmp_path / "memory.db"
    with sqlite3.connect(chemin) as connexion:
        connexion.execute("""CREATE TABLE short_term_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, role TEXT,
            content TEXT, timestamp DATETIME)""")
        connexion.execute("""CREATE TABLE souvenirs (
            identifiant TEXT PRIMARY KEY, contenu TEXT, cree_le TEXT)""")
    return chemin


def ecrire_message(chemin, session, horodatage):
    with sqlite3.connect(chemin) as connexion:
        connexion.execute(
            "INSERT INTO short_term_memory (session_id, role, content, timestamp)"
            " VALUES (?, 'user', 'peu importe', ?)", (session, horodatage))


# --- Le fil -------------------------------------------------------------------

def test_le_fil_compte_les_messages_et_les_conversations(base):
    ecrire_message(base, "conv-A", "2026-09-01 10:00:00")
    ecrire_message(base, "conv-A", "2026-09-01 10:01:00")
    ecrire_message(base, "conv-B", "2026-09-02 10:00:00")

    fil = etat_fil(base)

    assert fil.messages == 3
    assert fil.conversations == 2
    assert fil.plus_ancien == "2026-09-01 10:00:00"


def test_une_base_absente_ne_rend_pas_zero_message(tmp_path):
    """Zero message et base introuvable sont deux faits differents. Les
    confondre envoie chercher la panne ailleurs."""
    fil = etat_fil(tmp_path / "rien.db")

    assert fil.messages is None, "une base absente a ete comptee comme vide"
    assert fil.detail


def test_une_table_absente_ne_rend_pas_zero(tmp_path):
    chemin = tmp_path / "vide.db"
    sqlite3.connect(chemin).close()

    assert etat_fil(chemin).messages is None
    assert etat_souvenirs(chemin).total is None


def test_les_souvenirs_sont_comptes(base):
    with sqlite3.connect(base) as connexion:
        connexion.execute("INSERT INTO souvenirs VALUES ('a', 'x', '2026-09-03T10:00:00+00:00')")
        connexion.execute("INSERT INTO souvenirs VALUES ('b', 'y', '2026-09-04T10:00:00+00:00')")

    souvenirs = etat_souvenirs(base)

    assert souvenirs.total == 2
    assert souvenirs.plus_ancien == "2026-09-03T10:00:00+00:00"


# --- La persistance s'observe --------------------------------------------------

def test_une_ligne_anterieure_au_demarrage_prouve_la_persistance(base):
    avant = (module_etat.DEMARRAGE - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

    resultat = etat_base(base, avant)

    assert resultat.persistance == PERSISTANCE_CONFIRMEE
    assert avant in resultat.detail


def test_sans_ligne_anterieure_la_persistance_n_est_pas_niee(base):
    """`PAS_ENCORE_OBSERVEE` n'est pas « non ». Une base neuve ne prouve pas
    qu'elle sera effacee."""
    apres = (module_etat.DEMARRAGE + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")

    resultat = etat_base(base, apres)

    assert resultat.persistance == PERSISTANCE_PAS_OBSERVEE
    assert resultat.persistance != "NON"


def test_une_base_absente_rend_une_persistance_inconnue(tmp_path):
    resultat = etat_base(tmp_path / "rien.db", None)

    assert resultat.persistance == PERSISTANCE_INCONNUE
    assert resultat.existe is False
    assert resultat.octets is None


def test_un_horodatage_illisible_ne_conclut_pas_a_la_persistance(base):
    resultat = etat_base(base, "pas une date")

    assert resultat.persistance == PERSISTANCE_PAS_OBSERVEE


# --- Par le sens, ou par les mots ---------------------------------------------

def test_sans_embeddings_la_recherche_est_annoncee_lexicale():
    async def absent():
        return EtatEmbeddings(disponible=False, etat="SERVEUR_ABSENT",
                              detail="aucun vecteur rendu", modele="bge-m3")

    resultat = asyncio.run(etat_recherche(absent))

    assert resultat.mode == RECHERCHE_PAR_LES_MOTS
    assert "SERVEUR_ABSENT" in resultat.detail, (
        "le mode lexical est annonce sans sa raison mesuree")


def test_avec_embeddings_la_recherche_est_annoncee_semantique():
    async def present():
        return EtatEmbeddings(disponible=True, etat="DISPONIBLE",
                              detail="vecteur obtenu", modele="bge-m3",
                              dimension=1024)

    resultat = asyncio.run(etat_recherche(present))

    assert resultat.mode == RECHERCHE_PAR_LE_SENS
    assert "1024" in resultat.detail


def test_une_sonde_qui_leve_rend_inconnu_pas_lexical():
    """Une mesure impossible n'est pas une mesure negative."""
    async def casse():
        raise ConnectionError("rien au bout")

    resultat = asyncio.run(etat_recherche(casse))

    assert resultat.mode == RECHERCHE_INCONNUE
    assert "rien au bout" in resultat.detail


# --- Le rapport complet --------------------------------------------------------

def test_le_rapport_porte_les_quatre_sections(base):
    ecrire_message(base, "conv-A", "2026-09-01 10:00:00")

    async def absent():
        return EtatEmbeddings(disponible=False, etat="SERVEUR_ABSENT",
                              detail="rien", modele="bge-m3")

    rapport = asyncio.run(etat_memoire(base, absent))

    assert set(rapport) == {"base", "fil", "souvenirs", "recherche"}
    assert rapport["fil"]["messages"] == 1
    assert rapport["base"]["chemin"].endswith("memory.db")


def test_le_rapport_ne_leve_jamais_sur_une_base_absente(tmp_path):
    async def absent():
        return EtatEmbeddings(disponible=False, etat="SERVEUR_ABSENT",
                              detail="rien", modele="bge-m3")

    rapport = asyncio.run(etat_memoire(tmp_path / "rien.db", absent))

    assert rapport["fil"]["messages"] is None
    assert rapport["base"]["existe"] is False
