"""Le calcul des materiaux : il retrouve son chantier, et il dit ses hypotheses.

Le test qui compte le plus est `test_retrouve_le_chantier_de_reference` : si les
quantites calculees pour 243 m2 ne redonnent pas exactement ce qu'il a commande
sur UC-2026-0804-FG2, les ratios ne valent rien.
"""
import math

import pytest

from agents.plaquiste.calcul_materiaux import (
    Besoin,
    formater,
    phrase_convention,
    quantites_pour,
    surface_developpee,
)
from agents.plaquiste.plaquiste_agent import charger_metier


@pytest.fixture(scope="module")
def metier():
    return charger_metier()


@pytest.fixture
def quantites(metier):
    def _q(*args, **kwargs):
        calcul = quantites_pour(*args, metier=metier, **kwargs)
        return {b.article: b.quantite for b in calcul.besoins}
    return _q


# --- Le chantier de reference -------------------------------------------------

def test_retrouve_le_chantier_de_reference(quantites):
    """243 m2 de mur, 18 parois : exactement ce qui a ete commande."""
    assert quantites(243, faces=2, parois=18) == {
        "Plaque standard BA13": 234,
        "Montant 7 cm (70 mm)": 288,
        "Rails 7 cm (70 mm)": 54,
        "Seau enduit": 10,
        "Seau Katex": 4,
        "Paquet papier enduit": 1,
        "Laine de verre (paquet)": 18,
        "Paquet vis (25 mm ou 35 mm)": 18,
        "Sac enduit": 18,
        "Bande a joints": 18,
        "Bande armee": 18,
        "Paquet chevilles a frapper": 18,
    }


def test_le_total_du_chantier_de_reference(metier):
    calcul = quantites_pour(243, metier, faces=2, parois=18)
    attendu = sum(b.quantite * b.prix_unitaire for b in calcul.besoins)
    assert calcul.total_connu == attendu
    assert calcul.articles_sans_prix == []


# --- Surface developpee -------------------------------------------------------

def test_deux_faces_doublent_la_surface():
    assert surface_developpee(89, faces=2) == 178


def test_une_face_ne_double_pas():
    assert surface_developpee(89, faces=1) == 89


def test_une_surface_deja_developpee_n_est_pas_multipliee():
    assert surface_developpee(89, faces=2, deja_developpee=True) == 89


def test_la_surface_developpee_apparait_dans_le_calcul(metier):
    assert quantites_pour(89, metier, faces=2).surface_developpee == 178
    assert quantites_pour(89, metier, faces=2, deja_developpee=True).surface_developpee == 89


# --- L'hypothese est ecrite, jamais silencieuse -------------------------------

def test_la_convention_annonce_la_multiplication():
    phrase = phrase_convention(89, 2, 178, deja_developpee=False)
    assert "89" in phrase and "178" in phrase
    assert "deja developpes" in phrase  # elle propose l'autre lecture


def test_la_convention_dit_quand_rien_n_est_multiplie():
    phrase = phrase_convention(89, 2, 89, deja_developpee=True)
    assert "Aucune multiplication" in phrase


def test_le_rapport_porte_l_hypothese_en_tete(metier):
    rapport = formater(quantites_pour(89, metier))
    assert "Hypothese" in rapport.splitlines()[1]


@pytest.mark.parametrize("deja", [False, True])
def test_les_deux_lectures_donnent_des_quantites_differentes(metier, deja):
    calcul = quantites_pour(89, metier, deja_developpee=deja)
    plaques = next(b.quantite for b in calcul.besoins if b.article == "Plaque standard BA13")
    assert plaques == (43 if deja else 86)


# --- Parois : connues, ou estimees et annoncees comme telles ------------------

def test_un_nombre_de_parois_fourni_n_est_pas_estime(metier):
    calcul = quantites_pour(243, metier, parois=18)
    assert calcul.parois == 18
    assert calcul.parois_estimees is False


def test_sans_nombre_de_parois_il_est_estime(metier):
    calcul = quantites_pour(243, metier)
    assert calcul.parois_estimees is True
    assert calcul.parois == 18  # 486 m2 / 27 m2 par paroi


def test_une_estimation_est_annoncee_dans_le_rapport(metier):
    """Le rapport le dit en toutes lettres, pas seulement dans la colonne base :
    « estime » apparait aussi dans « 7 paroi(s) estimee(s) », ce qui ne suffit pas."""
    rapport = formater(quantites_pour(89, metier))
    assert "Nombre de parois non fourni" in rapport
    assert "paroi(s) estimee(s)" in rapport


def test_une_paroi_connue_n_est_pas_annoncee_comme_estimee(metier):
    rapport = formater(quantites_pour(89, metier, parois=4))
    assert "Nombre de parois non fourni" not in rapport


def test_les_consommables_suivent_les_parois_pas_la_surface(metier):
    """Six articles sont commandes a la paroi : deux fois plus de parois,
    deux fois plus de sacs, a surface identique."""
    peu = quantites_pour(100, metier, parois=3)
    beaucoup = quantites_pour(100, metier, parois=6)
    def quantite(calcul, article):
        return next(b.quantite for b in calcul.besoins if b.article == article)

    assert quantite(beaucoup, "Sac enduit") == 2 * quantite(peu, "Sac enduit")
    assert quantite(beaucoup, "Plaque standard BA13") == quantite(peu, "Plaque standard BA13")


# --- Arrondi ------------------------------------------------------------------

def test_les_quantites_sont_arrondies_au_dessus(metier):
    """On n'achete pas 0,4 sac : toute quantite exacte fractionnaire monte."""
    calcul = quantites_pour(37, metier, parois=2)
    for besoin in calcul.besoins:
        assert besoin.quantite == math.ceil(round(besoin.quantite_exacte, 6))
        assert besoin.quantite >= besoin.quantite_exacte


def test_aucune_quantite_nulle(metier):
    """Meme un tout petit chantier commande au moins une unite de chaque."""
    for besoin in quantites_pour(2, metier, parois=1).besoins:
        assert besoin.quantite >= 1


# --- Prix : jamais inventes ---------------------------------------------------

def test_un_article_hors_grille_n_a_pas_de_total(metier):
    ampute = dict(metier)
    ampute["prix_materiaux"] = {k: v for k, v in metier["prix_materiaux"].items()
                                if k != "Sac enduit"}
    calcul = quantites_pour(243, ampute, parois=18)
    sac = next(b for b in calcul.besoins if b.article == "Sac enduit")
    assert sac.prix_unitaire is None
    assert sac.total is None
    assert "Sac enduit" in calcul.articles_sans_prix
    assert "a confirmer" in formater(calcul)


def test_un_article_sans_prix_ne_gonfle_pas_le_total(metier):
    ampute = dict(metier)
    ampute["prix_materiaux"] = {k: v for k, v in metier["prix_materiaux"].items()
                                if k != "Sac enduit"}
    complet = quantites_pour(243, metier, parois=18)
    partiel = quantites_pour(243, ampute, parois=18)
    assert partiel.total_connu == complet.total_connu - 18 * metier["prix_materiaux"]["Sac enduit"]


# --- Refus plutot qu'invention ------------------------------------------------

def test_sans_ratios_rien_n_est_chiffre():
    calcul = quantites_pour(89, {"prix_materiaux": {"Plaque standard BA13": 4500}})
    assert calcul.besoins == []
    assert "n'invente" in formater(calcul) or "pas de quantites" in formater(calcul)


@pytest.mark.parametrize("surface", [0, -1, -89.5])
def test_une_surface_non_positive_est_refusee(metier, surface):
    with pytest.raises(ValueError):
        quantites_pour(surface, metier)


@pytest.mark.parametrize("faces", [0, 3, -1])
def test_un_nombre_de_faces_impossible_est_refuse(metier, faces):
    with pytest.raises(ValueError):
        quantites_pour(89, metier, faces=faces)


def test_un_nombre_de_parois_non_positif_est_refuse(metier):
    with pytest.raises(ValueError):
        quantites_pour(89, metier, parois=0)


# --- Tracabilite --------------------------------------------------------------

def test_le_rapport_nomme_le_chantier_source(metier):
    assert "UC-2026-0804-FG2" in formater(quantites_pour(89, metier))


def test_chaque_besoin_dit_sur_quoi_il_est_calcule(metier):
    for besoin in quantites_pour(89, metier, parois=4).besoins:
        assert besoin.base
        assert "m2 developpes" in besoin.base or "paroi" in besoin.base


def test_un_besoin_se_lit_en_une_ligne():
    besoin = Besoin(article="Sac enduit", quantite=3, base="4 paroi(s)",
                    quantite_exacte=2.5, prix_unitaire=12000, total=36000)
    assert str(besoin) == "Sac enduit : 3 (4 paroi(s)) — 36000 FCFA"
