"""Combien de voix affirment un souvenir — et pourquoi une seule qui se répète
n'en fait pas plusieurs.

`DEC-0099` avait nommé `source_count` sans le faire. En le faisant, un défaut
réel est apparu, mesuré le 13/09/2026 **avant** correction :

```
depart          : INFERENCE | source = 'devis_aout.pdf'
3x MEME source  : FACT      | source = 'devis_aout.pdf + devis_aout.pdf + devis_aout.pdf'
```

La docstring de `confirmer()` promettait « elle exige une source nouvelle ».
Elle ne le vérifiait pas. Un document qui se répétait trois fois promouvait une
inférence en **fait**, et ARENA répondait ensuite un prix avec l'assurance d'un
fait corroboré alors qu'une seule voix l'avait dit.

`occurrences` et `nombre_de_sources` répondent à deux questions différentes :
combien de fois c'est redit, et par combien de voix. Les confondre est
exactement ce qui produisait le défaut.
"""
import json
import sqlite3

import pytest

from core.memory.personnelle import (
    SEPARATEUR_SOURCES,
    MemoirePersonnelle,
    Nature,
    TypeSouvenir,
)

TARIF = "Le tarif de pose est 4500 F/m2."


@pytest.fixture
def memoire(tmp_path) -> MemoirePersonnelle:
    return MemoirePersonnelle(db_path=str(tmp_path / "memoire.db"))


def supposer(memoire, source="devis_aout.pdf"):
    """Une inférence : ce qu'ARENA a déduit, pas ce qu'on lui a confirmé."""
    return memoire.retenir(TARIF, TypeSouvenir.SEMANTIQUE, Nature.INFERENCE,
                           source=source)


# --------------------------------------------------------------------------
# Le défaut mesuré, et sa correction
# --------------------------------------------------------------------------

def test_la_meme_source_qui_se_repete_ne_promeut_pas_une_inference_en_fait(memoire):
    """Le défaut exact du 13/09/2026. C'est le test qui l'empêche de revenir."""
    souvenir = supposer(memoire)

    memoire.confirmer(souvenir.identifiant, "devis_aout.pdf")
    relu = memoire.confirmer(souvenir.identifiant, "devis_aout.pdf")

    assert relu.nature is Nature.INFERENCE, (
        "un document qui se repete est une seule voix : il ne peut pas "
        "promouvoir sa propre supposition en fait"
    )
    assert relu.nombre_de_sources == 1


def test_elle_est_quand_meme_notee_comme_revue(memoire):
    """« Redit » est vrai et doit se voir. « Confirmé » ne l'est pas."""
    souvenir = supposer(memoire)

    memoire.confirmer(souvenir.identifiant, "devis_aout.pdf")
    relu = memoire.confirmer(souvenir.identifiant, "devis_aout.pdf")

    assert relu.occurrences == 3, "le souvenir a bien ete revu deux fois de plus"
    assert relu.nombre_de_sources == 1, "par la meme voix, les trois fois"


def test_le_champ_source_lisible_ne_repete_plus_une_voix(memoire):
    """Avant : `'devis_aout.pdf + devis_aout.pdf + devis_aout.pdf'`."""
    souvenir = supposer(memoire)

    memoire.confirmer(souvenir.identifiant, "devis_aout.pdf")
    relu = memoire.confirmer(souvenir.identifiant, "devis_aout.pdf")

    assert relu.source == "devis_aout.pdf"
    assert SEPARATEUR_SOURCES not in relu.source


def test_une_voix_nouvelle_promeut_bien_l_inference_en_fait(memoire):
    """La correction ne doit pas casser le chemin légitime."""
    souvenir = supposer(memoire)

    relu = memoire.confirmer(souvenir.identifiant, "le proprietaire")

    assert relu.nature is Nature.FAIT
    assert relu.nombre_de_sources == 2
    assert relu.sources == ("devis_aout.pdf", "le proprietaire")
    assert relu.source == f"devis_aout.pdf{SEPARATEUR_SOURCES}le proprietaire"


def test_trois_voix_distinctes_se_comptent_toutes(memoire):
    souvenir = supposer(memoire)

    memoire.confirmer(souvenir.identifiant, "le proprietaire")
    memoire.confirmer(souvenir.identifiant, "facture_septembre.pdf")
    relu = memoire.confirmer(souvenir.identifiant, "le proprietaire")

    assert relu.nombre_de_sources == 3, (
        "trois voix distinctes malgre le quatrieme appel, qui repete la deuxieme"
    )
    assert relu.occurrences == 4, "quatre appels, quatre revues"


# --------------------------------------------------------------------------
# Le compte est dérivé, jamais stocké
# --------------------------------------------------------------------------

def test_aucune_colonne_ne_stocke_le_compte(memoire):
    """Un compteur rangé à côté de la liste finit par la contredire, et c'est
    alors le compteur qu'on croit."""
    with sqlite3.connect(memoire.db_path) as connexion:
        colonnes = {
            ligne[1]
            for ligne in connexion.execute("PRAGMA table_info(souvenirs)").fetchall()
        }

    assert "sources" in colonnes
    assert "nombre_de_sources" not in colonnes


def test_le_compte_suit_la_liste_a_chaque_etape(memoire):
    souvenir = supposer(memoire)
    for voix in ("le proprietaire", "le proprietaire", "facture_septembre.pdf"):
        relu = memoire.confirmer(souvenir.identifiant, voix)
        assert relu.nombre_de_sources == len(relu.sources)


def test_les_deux_chiffres_voyagent_dans_le_rendu(memoire):
    souvenir = supposer(memoire)
    memoire.confirmer(souvenir.identifiant, "le proprietaire")

    rendu = memoire.lire(souvenir.identifiant).to_dict()

    assert rendu["nombre_de_sources"] == 2
    assert rendu["sources"] == ["devis_aout.pdf", "le proprietaire"]
    assert rendu["occurrences"] == 2


# --------------------------------------------------------------------------
# Celui qui rejette n'affirme pas le contenu
# --------------------------------------------------------------------------

def test_rejeter_ne_compte_pas_comme_une_voix(memoire):
    souvenir = supposer(memoire)

    relu = memoire.rejeter(souvenir.identifiant, "le proprietaire")

    assert relu.nombre_de_sources == 1, (
        "dire non au contenu n'est pas l'affirmer"
    )
    assert relu.nature is Nature.INFERENCE
    assert "le proprietaire" in relu.source, "qui a decide reste trace"


# --------------------------------------------------------------------------
# Refus inchangés
# --------------------------------------------------------------------------

def test_confirmer_sans_source_reste_refuse(memoire):
    souvenir = supposer(memoire)

    with pytest.raises(ValueError):
        memoire.confirmer(souvenir.identifiant, "   ")


def test_une_liste_de_sources_illisible_est_traitee_comme_non_comptee(memoire):
    """Une ligne abîmée rend `None`, jamais un chiffre inventé, et ne fait pas
    échouer la lecture des autres."""
    souvenir = supposer(memoire)
    with sqlite3.connect(memoire.db_path) as connexion:
        connexion.execute("UPDATE souvenirs SET sources = ? WHERE identifiant = ?",
                          ("{pas du json", souvenir.identifiant))

    relu = memoire.lire(souvenir.identifiant)

    assert relu is not None
    assert relu.nombre_de_sources is None
    assert relu.sources == ()


# --------------------------------------------------------------------------
# Zone verrouillée : une base d'avant la colonne
# --------------------------------------------------------------------------

ANCIEN_SCHEMA = """CREATE TABLE souvenirs (
    identifiant TEXT PRIMARY KEY, contenu TEXT NOT NULL, type TEXT NOT NULL,
    nature TEXT NOT NULL, source TEXT NOT NULL, projet TEXT,
    importance REAL NOT NULL, metadonnees TEXT NOT NULL, cree_le TEXT NOT NULL,
    vu_le TEXT NOT NULL, expire_le TEXT, occurrences INTEGER NOT NULL DEFAULT 1,
    etat TEXT NOT NULL DEFAULT 'ACTIVE', sensible INTEGER NOT NULL DEFAULT 0)"""


def _base_ancienne(chemin, identifiant, source, occurrences=1):
    with sqlite3.connect(chemin) as connexion:
        connexion.execute(ANCIEN_SCHEMA)
        connexion.execute(
            "INSERT INTO souvenirs VALUES (?,?,'SEMANTIC','INFERENCE',?,NULL,0.5,'{}',"
            "'2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00',NULL,?,'ACTIVE',0)",
            (identifiant, TARIF, source, occurrences),
        )
    return MemoirePersonnelle(db_path=str(chemin))


def test_une_ligne_ancienne_jamais_confirmee_compte_une_voix(tmp_path):
    """La déduction est certaine : pas de séparateur, donc une seule voix."""
    memoire = _base_ancienne(tmp_path / "a.db", "seul", "devis_aout.pdf")

    relu = memoire.lire("seul")

    assert relu.nombre_de_sources == 1
    assert relu.sources == ("devis_aout.pdf",)


def test_une_ligne_ancienne_deja_confirmee_n_est_pas_comptee_du_tout(tmp_path):
    """`None`, pas `1`, et pas `2` non plus.

    Le champ `source` montre que le souvenir A été corroboré, mais découper la
    chaîne pour deviner par combien de voix fabriquerait un chiffre — une source
    nommée « a + b » en vaudrait deux. « Jamais compté ici » n'est pas « une
    seule ».
    """
    memoire = _base_ancienne(
        tmp_path / "b.db", "double", f"devis_aout.pdf{SEPARATEUR_SOURCES}le proprietaire"
    )

    relu = memoire.lire("double")

    assert relu.nombre_de_sources is None
    assert relu.nombre_de_sources != 1


def test_confirmer_une_ligne_ancienne_avec_une_voix_deja_presente_ne_promeut_pas(tmp_path):
    """Le test d'appartenance reste fiable là où le comptage ne l'est pas."""
    memoire = _base_ancienne(
        tmp_path / "c.db", "double", f"devis_aout.pdf{SEPARATEUR_SOURCES}le proprietaire"
    )

    relu = memoire.confirmer("double", "le proprietaire")

    assert relu.nature is Nature.INFERENCE, (
        "cette voix figure deja dans le champ source : elle ne corrobore rien"
    )
    assert relu.occurrences == 2


def test_confirmer_une_ligne_ancienne_avec_une_voix_nouvelle_n_invente_pas_de_compte(tmp_path):
    """Elle promeut — mais le compte reste `None` : y écrire `[nouvelle]`
    affirmerait que le souvenir n'a qu'une voix alors que `source` en montre
    plusieurs."""
    memoire = _base_ancienne(
        tmp_path / "d.db", "double", f"devis_aout.pdf{SEPARATEUR_SOURCES}le proprietaire"
    )

    relu = memoire.confirmer("double", "facture_septembre.pdf")

    assert relu.nature is Nature.FAIT
    assert relu.nombre_de_sources is None
    assert "facture_septembre.pdf" in relu.source


def test_la_colonne_est_bien_ajoutee_et_la_base_migree_accepte_une_ecriture(tmp_path):
    """Le test que le sabotage réclame.

    Tout ce qui précède est vrai **avec ou sans** l'`ALTER TABLE` :
    `_sources_depuis_ligne` tolère la colonne absente. Ce qui le prouve, c'est
    d'ÉCRIRE dans la base migrée — sans la colonne, l'`INSERT` nomme un champ
    qui n'existe pas.
    """
    memoire = _base_ancienne(tmp_path / "e.db", "ancien", "devis_aout.pdf")

    neuf = memoire.retenir("Le tarif passe a 5500 F/m2.", TypeSouvenir.SEMANTIQUE,
                           Nature.FAIT, source="le proprietaire")

    assert memoire.lire(neuf.identifiant).sources == ("le proprietaire",), (
        "la colonne n'a pas ete ajoutee : la base d'avant ne peut pas porter "
        "de liste de sources"
    )
    with sqlite3.connect(memoire.db_path) as connexion:
        stocke = connexion.execute(
            "SELECT sources FROM souvenirs WHERE identifiant = ?", (neuf.identifiant,)
        ).fetchone()[0]
    assert json.loads(stocke) == ["le proprietaire"]
    assert memoire.lire("ancien") is not None, "le souvenir d'avant a disparu"
