"""Depuis quand un souvenir est vrai — le miroir de « jusqu'à quand ».

`expire_le` existe depuis le premier jour : il dit **quand cesser de croire**.
Rien ne disait **à partir de quand commencer**, et `DEC-0099` l'avait nommé sans
le faire.

Le cas qui le rend nécessaire, et c'est celui du propriétaire :

> « À partir du 1er octobre, le tarif de pose passe à 5500 F/m². »

Enregistré en septembre. Sans début de validité, ARENA le sert dès septembre
comme le tarif courant et répond un prix faux **avec l'assurance d'un fait** —
la faute précise que `DUREE_CONTEXTE_HEURES` évite dans l'autre sens.

`valide_depuis` n'est pas `cree_le` : celui-ci dit quand le souvenir a été
**écrit**, celui-là depuis quand il est **vrai**. Les confondre est exactement
ce qui fait servir une annonce comme un fait.
"""
from datetime import datetime, timedelta, timezone

import pytest

from core.memory.personnelle import MemoirePersonnelle, Nature, Souvenir, TypeSouvenir

MAINTENANT = datetime.now(timezone.utc)
DANS_UN_MOIS = (MAINTENANT + timedelta(days=30)).isoformat(timespec="seconds")
IL_Y_A_UN_AN = (MAINTENANT - timedelta(days=365)).isoformat(timespec="seconds")


@pytest.fixture
def memoire(tmp_path) -> MemoirePersonnelle:
    return MemoirePersonnelle(db_path=str(tmp_path / "memoire.db"))


def retenir(memoire, contenu, **reste):
    return memoire.retenir(contenu, TypeSouvenir.SEMANTIQUE, Nature.FAIT,
                           source="proprietaire", **reste)


# --------------------------------------------------------------------------
# Un souvenir qui annonce une vérité à venir n'est pas encore vrai
# --------------------------------------------------------------------------

def test_un_tarif_annonce_pour_le_mois_prochain_n_est_pas_le_tarif_courant(memoire):
    """Le cas qui a motivé le champ."""
    retenir(memoire, "Le tarif de pose est 5000 F/m2.")
    retenir(memoire, "Le tarif de pose passe a 5500 F/m2.", valide_depuis=DANS_UN_MOIS)

    courants = [s.contenu for s in memoire.souvenirs()]

    assert courants == ["Le tarif de pose est 5000 F/m2."]


def test_il_est_quand_meme_garde_et_retrouvable(memoire):
    """Écarté de la lecture courante, jamais perdu : il sera vrai le mois prochain."""
    futur = retenir(memoire, "Le tarif passe a 5500 F/m2.", valide_depuis=DANS_UN_MOIS)

    assert memoire.lire(futur.identifiant) is not None
    assert len(memoire.souvenirs(inclure_a_venir=True)) == 1


def test_il_devient_vrai_le_jour_venu(memoire):
    futur = retenir(memoire, "Le tarif passe a 5500 F/m2.", valide_depuis=DANS_UN_MOIS)
    dans_deux_mois = MAINTENANT + timedelta(days=60)

    assert futur.pas_encore_vrai() is True
    assert futur.pas_encore_vrai(dans_deux_mois) is False
    assert futur.est_en_vigueur(dans_deux_mois) is True


def test_une_validite_passee_ne_change_rien(memoire):
    """Un souvenir vrai depuis un an est simplement vrai."""
    ancien = retenir(memoire, "Le tarif est 5000 F/m2.", valide_depuis=IL_Y_A_UN_AN)

    assert ancien.pas_encore_vrai() is False
    assert ancien.est_en_vigueur() is True
    assert len(memoire.souvenirs()) == 1


def test_sans_date_un_souvenir_est_vrai_depuis_toujours(memoire):
    """Le cas de la quasi-totalité des souvenirs — et de tous ceux d'avant."""
    souvenir = retenir(memoire, "Le tarif est 5000 F/m2.")

    assert souvenir.valide_depuis is None
    assert souvenir.pas_encore_vrai() is False
    assert souvenir.est_en_vigueur() is True


# --------------------------------------------------------------------------
# Le miroir tient des deux côtés
# --------------------------------------------------------------------------

def test_en_vigueur_exige_commence_ET_pas_fini(memoire):
    """`est_en_vigueur` combine les deux bornes, sans en oublier une."""
    fini = Souvenir(contenu="x", type=TypeSouvenir.SEMANTIQUE, nature=Nature.FAIT,
                    source="p", expire_le=IL_Y_A_UN_AN)
    pas_commence = Souvenir(contenu="x", type=TypeSouvenir.SEMANTIQUE,
                            nature=Nature.FAIT, source="p", valide_depuis=DANS_UN_MOIS)
    entre_les_deux = Souvenir(
        contenu="x", type=TypeSouvenir.SEMANTIQUE, nature=Nature.FAIT, source="p",
        valide_depuis=IL_Y_A_UN_AN,
        expire_le=(MAINTENANT + timedelta(days=30)).isoformat(timespec="seconds"))

    assert fini.est_en_vigueur() is False
    assert pas_commence.est_en_vigueur() is False
    assert entre_les_deux.est_en_vigueur() is True


def test_une_date_illisible_tait_le_souvenir_au_lieu_de_l_affirmer(memoire):
    """Même prudence qu'`est_perime` avec une échéance illisible.

    Des deux erreurs possibles, taire un souvenir coûte moins cher que
    d'affirmer une chose fausse.
    """
    casse = Souvenir(contenu="x", type=TypeSouvenir.SEMANTIQUE, nature=Nature.FAIT,
                     source="p", valide_depuis="pas une date")

    assert casse.pas_encore_vrai() is True
    assert casse.est_en_vigueur() is False


def test_les_deux_bornes_voyagent_dans_le_rendu(memoire):
    souvenir = retenir(memoire, "x", valide_depuis=DANS_UN_MOIS, duree_heures=48)

    rendu = souvenir.to_dict()

    assert rendu["valide_depuis"] == DANS_UN_MOIS
    assert rendu["expire_le"]


# --------------------------------------------------------------------------
# Zone verrouillée : la migration n'efface rien
# --------------------------------------------------------------------------

def test_une_base_d_avant_la_colonne_est_migree_sans_rien_perdre(tmp_path):
    """`core/memory/personnelle.py` est une zone verrouillée : « une migration
    qui n'efface rien »."""
    import sqlite3

    chemin = tmp_path / "ancienne.db"
    with sqlite3.connect(chemin) as connexion:
        connexion.execute("""CREATE TABLE souvenirs (
            identifiant TEXT PRIMARY KEY, contenu TEXT NOT NULL, type TEXT NOT NULL,
            nature TEXT NOT NULL, source TEXT NOT NULL, projet TEXT,
            importance REAL NOT NULL, metadonnees TEXT NOT NULL, cree_le TEXT NOT NULL,
            vu_le TEXT NOT NULL, expire_le TEXT, occurrences INTEGER NOT NULL DEFAULT 1,
            etat TEXT NOT NULL DEFAULT 'ACTIVE', sensible INTEGER NOT NULL DEFAULT 0)""")
        connexion.execute(
            "INSERT INTO souvenirs VALUES ('ancien','Le tarif est 5000 F/m2.',"
            "'SEMANTIC','FACT','proprietaire',NULL,0.5,'{}',"
            "'2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00',NULL,1,'ACTIVE',0)")

    memoire = MemoirePersonnelle(db_path=str(chemin))
    relu = memoire.lire("ancien")

    assert relu is not None, "le souvenir d'avant la migration a disparu"
    assert relu.contenu == "Le tarif est 5000 F/m2."
    assert relu.valide_depuis is None, (
        "aucun souvenir d'avant n'annoncait une verite a venir : `None` est exact"
    )
    assert relu.est_en_vigueur() is True, (
        "une migration ne doit pas faire taire ce qui etait lu hier"
    )
    assert len(memoire.souvenirs()) == 1

    # Le test que le sabotage a réclamé (13/09/2026). Tout ce qui précède est
    # vrai **avec ou sans** la migration : `_depuis_ligne` tolère la colonne
    # absente et rend `None`. Retirer l'`ALTER TABLE` laissait donc 72 tests au
    # vert. Ce qui le prouve vraiment, c'est d'ÉCRIRE dans la base migrée : sans
    # la colonne, l'`INSERT` nomme un champ qui n'existe pas.
    nouveau = retenir(memoire, "Le tarif passe a 5500 F/m2.", valide_depuis=DANS_UN_MOIS)

    assert memoire.lire(nouveau.identifiant).valide_depuis == DANS_UN_MOIS, (
        "la colonne n'a pas ete ajoutee : la base d'avant ne peut pas porter "
        "de debut de validite"
    )
    assert [s.contenu for s in memoire.souvenirs()] == ["Le tarif est 5000 F/m2."], (
        "le tarif a venir ne doit pas etre servi comme tarif courant"
    )
