"""`metre_plan.py` : traduire ce qu'OpenTakeoff mesure (pieds) en m2/ml,
et la limite honnete sur ce qu'un perimetre de piece peut devenir.
"""
from agents.plaquiste.metre_plan import (
    MetrePlan,
    Piece,
    chemin_dans,
    demande_un_plafond,
    depuis_mesure,
    formater,
    lire_hauteur,
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
    def test_plafond_nomme(self):
        assert demande_un_plafond("calcule le faux plafond de cette piece") is True

    def test_doublage_nomme(self):
        assert demande_un_plafond("c'est un doublage") is True

    def test_cloison_n_est_pas_un_plafond(self):
        assert demande_un_plafond("la surface de la cloison") is False


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
        une surface de cloisons a poser (docstring du module)."""
        metre = depuis_mesure("/x/a.pdf", DETAIL_UNE_PIECE)

        rendu = formater(metre)

        assert "pas encore une surface de cloisons" in rendu
