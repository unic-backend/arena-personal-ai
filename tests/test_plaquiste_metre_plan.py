"""`metre_plan.py` : traduire ce qu'OpenTakeoff mesure (pieds) en m2/ml,
et la limite honnete sur ce qu'un perimetre de piece peut devenir.
"""
from agents.plaquiste.metre_plan import (
    MetrePlan,
    Piece,
    chemin_dans,
    demande_non_calculable_depuis_le_plan,
    demande_un_plafond,
    depuis_mesure,
    faces_du_mur,
    formater,
    lire_hauteur,
    surface_murs_m2,
)


class TestCheminDans:
    def test_un_chemin_linux_est_lu(self):
        assert chemin_dans("analyse /home/saer/chantiers/A-101.pdf stp") == \
            "/home/saer/chantiers/A-101.pdf"

    def test_un_chemin_windows_est_lu(self):
        assert chemin_dans(r"ouvre C:\Chantiers\Diallo\plan.pdf") == \
            r"C:\Chantiers\Diallo\plan.pdf"

    def test_un_nom_de_fichier_seul_sans_dossier_n_est_pas_retenu(self):
        assert chemin_dans("regarde sample-plan.pdf") is None

    def test_aucun_pdf_rend_none(self):
        assert chemin_dans("chiffre-moi 18 parois de 5,40 x 2,50 m") is None


class TestLireHauteur:
    def test_hauteur_de_forme(self):
        assert lire_hauteur("hauteur de 2,50 m") == 2.5

    def test_forme_inversee(self):
        assert lire_hauteur("2.5m de hauteur") == 2.5

    def test_rien_lu_rend_none(self):
        assert lire_hauteur("analyse ce plan") is None

    def test_une_hauteur_nulle_n_est_pas_retenue(self):
        assert lire_hauteur("hauteur de 0 m") is None


class TestDemandeUnPlafond:
    """Seul un plafond PLAT est floor-area-equivalent (correction du
    29/08/2026) : un doublage, un habillage ou un coffre sont posés sur un
    MUR, pas au plafond — les confondre avec un plafond aurait chiffré une
    surface au sol la où il fallait largeur x hauteur."""

    def test_plafond_nomme(self):
        assert demande_un_plafond("calcule le faux plafond de cette piece") is True

    def test_doublage_n_est_plus_confondu_avec_un_plafond(self):
        assert demande_un_plafond("c'est un doublage") is False

    def test_cloison_n_est_pas_un_plafond(self):
        assert demande_un_plafond("la surface de la cloison") is False


class TestFacesDuMur:
    def test_doublage_est_une_seule_face(self):
        assert faces_du_mur("le doublage de ce mur") == 1

    def test_habillage_est_une_seule_face(self):
        assert faces_du_mur("un habillage") == 1

    def test_cloison_est_deux_faces_par_defaut(self):
        assert faces_du_mur("la cloison a poser") == 2

    def test_rien_de_nomme_est_deux_faces_par_defaut(self):
        assert faces_du_mur("la surface du mur") == 2


class TestDemandeNonCalculable:
    def test_rampant_n_est_calculable_depuis_aucune_mesure(self):
        assert demande_non_calculable_depuis_le_plan("le rampant de ce comble") is True

    def test_une_cloison_est_calculable(self):
        assert demande_non_calculable_depuis_le_plan("la cloison") is False


class TestSurfaceMurs:
    def test_perimetre_fois_hauteur(self):
        assert surface_murs_m2(perimetre_ml=26.4, hauteur_m=2.5) == 66.0

    def test_perimetre_absent_ne_leve_pas(self):
        assert surface_murs_m2(perimetre_ml=None, hauteur_m=2.5) == 0.0


DETAIL_UNE_PIECE = {
    "pieces": [{"feuille": "a.pdf", "numero": "101", "surface_pi2": 100.0,
                "perimetre_pi": 40.0, "confiance": 0.95}],
    "resume": {"totals": {"total_sf_net": 100.0, "lf_net": 40.0}},
    "feuilles_mesurees": ["a.pdf"],
    "feuilles_sans_echelle": [],
}


class TestDepuisMesure:
    def test_convertit_pieds_en_metres(self):
        metre = depuis_mesure("/x/a.pdf", DETAIL_UNE_PIECE)

        # 100 pi2 = 9.29 m2 ; 40 pi = 12.19 ml (arrondis a 2 decimales)
        assert metre.surface_totale_m2 == 9.29
        assert metre.perimetre_total_ml == 12.19
        assert metre.pieces[0].surface_m2 == 9.29
        assert metre.pieces[0].numero == "101"

    def test_un_detail_vide_ne_leve_pas(self):
        metre = depuis_mesure("/x/a.pdf", {})

        assert metre.pieces == []
        assert metre.surface_totale_m2 == 0.0

    def test_complet_est_faux_des_qu_une_feuille_manque(self):
        detail = dict(DETAIL_UNE_PIECE, feuilles_sans_echelle=["b.pdf"])
        metre = depuis_mesure("/x/a.pdf", detail)

        assert metre.complet is False

    def test_complet_est_vrai_sans_feuille_manquante(self):
        metre = depuis_mesure("/x/a.pdf", DETAIL_UNE_PIECE)

        assert metre.complet is True


class TestFormater:
    def test_le_total_et_chaque_piece_apparaissent(self):
        metre = depuis_mesure("/x/a.pdf", DETAIL_UNE_PIECE)

        rendu = formater(metre)

        assert "101" in rendu
        assert "9.29" in rendu
        assert "12.19" in rendu

    def test_une_feuille_sans_echelle_est_nommee(self):
        metre = MetrePlan(chemin="/x/a.pdf", pieces=[Piece("a.pdf", "1", 10.0, 5.0)],
                          surface_totale_m2=10.0, perimetre_total_ml=5.0,
                          feuilles_mesurees=["a.pdf"], feuilles_sans_echelle=["b.pdf"])

        rendu = formater(metre)

        assert "b.pdf" in rendu
        assert "NON comptee" in rendu

    def test_aucune_piece_le_dit_sans_rien_inventer(self):
        metre = MetrePlan(chemin="/x/vide.pdf")

        rendu = formater(metre)

        assert "vide.pdf" in rendu
        assert "Aucune piece mesurable" in rendu

    def test_le_perimetre_n_est_jamais_presente_comme_un_chiffrage(self):
        """La limite honnete du module : un perimetre mesure n'est pas encore
        une surface de mur a poser (docstring du module)."""
        metre = depuis_mesure("/x/a.pdf", DETAIL_UNE_PIECE)

        rendu = formater(metre)

        assert "pas encore une surface de mur" in rendu
