"""`ifc_metre.py` : traduire ce que le connecteur IFC rend en francais, et la
limite honnete sur ce qu'un mur SANS quantite exploitable devient (jamais
une estimation)."""
from agents.plaquiste.ifc_metre import (
    AnalyseIfc,
    MetreIfc,
    chemin_dans,
    demande_de_croquis_ifc,
    depuis_analyse,
    depuis_metre,
    dimensions_pour_croquis,
    formater_analyse,
    formater_metre,
)


class TestCheminDans:
    def test_un_chemin_linux_est_lu(self):
        assert chemin_dans("analyse /home/saer/chantiers/A-101.ifc stp") == \
            "/home/saer/chantiers/A-101.ifc"

    def test_un_chemin_windows_est_lu(self):
        assert chemin_dans(r"ouvre C:\Chantiers\Diallo\batiment.ifc") == \
            r"C:\Chantiers\Diallo\batiment.ifc"

    def test_un_nom_de_fichier_seul_sans_dossier_n_est_pas_retenu(self):
        assert chemin_dans("regarde exemple.ifc") is None

    def test_aucun_ifc_rend_none(self):
        assert chemin_dans("analyse /home/saer/plan.pdf") is None

    def test_ne_confond_pas_un_chemin_pdf_avec_un_ifc(self):
        assert chemin_dans("analyse /home/saer/plan.pdf et /home/saer/batiment.ifc") == \
            "/home/saer/batiment.ifc"


DETAIL_ANALYSE = {
    "niveaux": ["Niveau 1", "Niveau 2"],
    "comptes": {"mur": 3, "porte": 1, "fenetre": 1, "espace": 0, "plafond": 0},
    "elements_par_niveau": {"Niveau 1": {"mur": 2, "porte": 1}, "Niveau 2": {"mur": 1, "fenetre": 1}},
}


class TestDemandeDeCroquisIfc:
    def test_genere_le_croquis_ifc_declenche(self):
        assert demande_de_croquis_ifc("genere le croquis ifc de cette cloison") is True

    def test_cree_un_fichier_ifc_declenche(self):
        assert demande_de_croquis_ifc("cree un fichier ifc de 5,40 x 2,50") is True

    def test_exporte_en_ifc_declenche(self):
        assert demande_de_croquis_ifc("exporte cette cloison en ifc") is True

    def test_lire_un_fichier_ifc_ne_declenche_pas(self):
        """La frontiere qui compte : LIRE un fichier IFC existant ne doit
        jamais en generer un nouveau de son propre chef."""
        assert demande_de_croquis_ifc("analyse le fichier /home/saer/batiment.ifc") is False

    def test_une_phrase_ordinaire_ne_declenche_pas(self):
        assert demande_de_croquis_ifc("chiffre-moi 18 parois de 5,40 x 2,50 m") is False


class TestDimensionsPourCroquis:
    def test_longueur_x_hauteur_est_lue(self):
        assert dimensions_pour_croquis("5,40 x 2,50 m") == (5.4, 2.5)

    def test_forme_avec_par(self):
        assert dimensions_pour_croquis("3 par 2.5") == (3.0, 2.5)

    def test_rien_lu_rend_none(self):
        assert dimensions_pour_croquis("genere le croquis ifc de cette cloison") is None

    def test_une_dimension_nulle_n_est_pas_retenue(self):
        assert dimensions_pour_croquis("0 x 2,50 m") is None


class TestDepuisAnalyse:
    def test_traduit_les_niveaux_et_comptes(self):
        analyse = depuis_analyse("/x/b.ifc", DETAIL_ANALYSE)

        assert analyse.niveaux == ["Niveau 1", "Niveau 2"]
        assert analyse.comptes["mur"] == 3
        assert analyse.elements_par_niveau["Niveau 1"]["porte"] == 1

    def test_un_detail_vide_ne_leve_pas(self):
        analyse = depuis_analyse("/x/b.ifc", {})

        assert analyse.niveaux == []
        assert analyse.comptes == {}


class TestFormaterAnalyse:
    def test_niveaux_et_comptes_apparaissent(self):
        analyse = depuis_analyse("/x/b.ifc", DETAIL_ANALYSE)

        rendu = formater_analyse(analyse)

        assert "Niveau 1" in rendu
        assert "Niveau 2" in rendu
        assert "mur : 3" in rendu
        assert "porte : 1" in rendu

    def test_par_niveau_apparait(self):
        analyse = depuis_analyse("/x/b.ifc", DETAIL_ANALYSE)

        rendu = formater_analyse(analyse)

        assert "Par niveau" in rendu

    def test_aucun_element_le_dit_sans_rien_inventer(self):
        analyse = AnalyseIfc(chemin="/x/vide.ifc")

        rendu = formater_analyse(analyse)

        assert "vide.ifc" in rendu
        assert "aucun element BIM reconnu" in rendu


DETAIL_METRE = {
    "murs": 3, "surface_m2": 33.5, "elements_chiffres": 2,
    "elements_sans_quantite": ["Cloison sans metre"],
}


class TestDepuisMetre:
    def test_traduit_la_surface(self):
        metre = depuis_metre("/x/b.ifc", DETAIL_METRE)

        assert metre.surface_m2 == 33.5
        assert metre.murs == 3
        assert metre.elements_chiffres == 2

    def test_un_detail_vide_ne_leve_pas(self):
        metre = depuis_metre("/x/b.ifc", {})

        assert metre.surface_m2 == 0.0
        assert metre.murs == 0


class TestFormaterMetre:
    def test_la_surface_et_le_nombre_de_murs_apparaissent(self):
        metre = depuis_metre("/x/b.ifc", DETAIL_METRE)

        rendu = formater_metre(metre)

        assert "33.5" in rendu
        assert "3 mur(s)" in rendu

    def test_un_mur_sans_quantite_est_nomme_et_exclu(self):
        """La limite honnete du module : un mur sans quantite exploitable
        dans le fichier IFC n'entre jamais dans le total, il est nomme."""
        metre = depuis_metre("/x/b.ifc", DETAIL_METRE)

        rendu = formater_metre(metre)

        assert "Cloison sans metre" in rendu
        assert "SANS quantite exploitable" in rendu

    def test_aucun_mur_le_dit_sans_rien_inventer(self):
        metre = MetreIfc(chemin="/x/vide.ifc")

        rendu = formater_metre(metre)

        assert "vide.ifc" in rendu
        assert "Aucun mur trouve" in rendu

    def test_jamais_une_geometrie_recalculee(self):
        """La limite honnete du module : la surface vient des quantites deja
        ecrites dans le fichier, jamais d'une geometrie reconstruite ici."""
        metre = depuis_metre("/x/b.ifc", DETAIL_METRE)

        rendu = formater_metre(metre)

        assert "jamais une geometrie recalculee" in rendu
