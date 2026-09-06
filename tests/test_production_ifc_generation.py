"""`ifc_generation.py` : un croquis IFC minimal, relu par notre PROPRE
lecteur (`ifc_lecture.py`, DEC-0053) pour vérifier la cohérence bout en
bout — jamais deux calculs de surface qui pourraient diverger.

IfcOpenShell est réellement installé (offline, pas de réseau) : aucun mock
ici, un vrai fichier IFC est écrit et relu.
"""
from core.production.ifc_generation import EPAISSEUR_DEFAUT_M, generer_croquis_cloison
from core.production.ifc_lecture import elements, niveaux, surface_totale


class TestGenererCroquisCloison:
    def test_le_fichier_engendre_un_mur_reel(self):
        fichier = generer_croquis_cloison(5.4, 2.5, nom="Test")

        murs = elements(fichier, "IfcWall")
        assert len(murs) == 1
        assert murs[0].nom == "Test"
        assert murs[0].niveau == "Niveau 1"

    def test_la_surface_ecrite_est_longueur_fois_hauteur(self):
        """La garantie centrale (DEC-0056) : la quantite ecrite dans le
        fichier correspond EXACTEMENT a ce que le devis a chiffre — jamais
        un second calcul qui pourrait diverger."""
        fichier = generer_croquis_cloison(5.4, 2.5)

        murs = elements(fichier, "IfcWall")
        assert murs[0].surface_m2 == 13.5

    def test_epaisseur_par_defaut_est_le_montant_70mm(self):
        import ifcopenshell.util.element as util_element

        fichier = generer_croquis_cloison(3.0, 2.5)
        mur = fichier.by_type("IfcWall")[0]
        quantites = next(iter(util_element.get_psets(mur, qtos_only=True).values()))
        assert quantites["Width"] == EPAISSEUR_DEFAUT_M

    def test_epaisseur_explicite_est_prise_en_compte(self):
        import ifcopenshell.util.element as util_element

        fichier = generer_croquis_cloison(3.0, 2.5, epaisseur_m=0.48)
        mur = fichier.by_type("IfcWall")[0]
        quantites = next(iter(util_element.get_psets(mur, qtos_only=True).values()))
        assert quantites["Width"] == 0.48
        # La surface (longueur x hauteur) ne depend pas de l'epaisseur.
        assert elements(fichier, "IfcWall")[0].surface_m2 == 7.5

    def test_un_seul_niveau_est_cree(self):
        fichier = generer_croquis_cloison(5.4, 2.5)
        assert niveaux(fichier) == ["Niveau 1"]

    def test_surface_totale_coherente_avec_le_lecteur(self):
        """Smoke test reel : ecrit puis relu par notre propre module de
        lecture, comme un client le ferait avec un fichier reel."""
        fichier = generer_croquis_cloison(5.4, 2.5)
        murs = elements(fichier, "IfcWall")

        resultat = surface_totale(murs)

        assert resultat["surface_m2"] == 13.5
        assert resultat["elements_chiffres"] == 1
        assert resultat["elements_sans_quantite"] == []

    def test_epaisseur_par_defaut_est_documentee(self):
        assert EPAISSEUR_DEFAUT_M == 0.07
