"""Le connecteur de génération IFC : un vrai fichier écrit et relu, jamais
un second calcul de surface qui pourrait diverger du devis.

IfcOpenShell est réellement installé (offline) : aucun mock, un vrai
fichier IFC est écrit sur disque puis relu avec `ifc_lecture.py`.
"""
from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.ifc_generation import (
    EPAISSEUR_MAX_M,
    HAUTEUR_MAX_M,
    LONGUEUR_MAX_M,
    ConnecteurIfcGeneration,
)
from core.production.ifc_lecture import elements


class TestCapacites:
    def test_une_seule_capacite_qui_ecrit(self):
        capacites = ConnecteurIfcGeneration().capacites()
        assert set(capacites) == {"generer"}
        assert capacites["generer"].ecriture is True
        assert capacites["generer"].action == "document"


class TestSonde:
    def test_ifcopenshell_installe_est_operationnel(self):
        sante = ConnecteurIfcGeneration().sonder()
        assert sante.etat is EtatSante.OPERATIONNEL


class TestGeneration:
    def test_ecrit_un_fichier_reel_relisible(self, tmp_path):
        connecteur = ConnecteurIfcGeneration(dossier=tmp_path)

        resultat = connecteur.executer_confirmee("generer", longueur_m=5.4, hauteur_m=2.5)

        assert resultat.statut is Statut.SUCCES, resultat.message
        assert resultat.detail["surface_m2"] == 13.5
        fichier_ecrit = tmp_path / next(iter(tmp_path.iterdir())).name
        assert fichier_ecrit.is_file() and fichier_ecrit.stat().st_size > 0

    def test_le_fichier_ecrit_est_coherent_avec_le_lecteur(self, tmp_path):
        """La garantie centrale (DEC-0056) : ce que le connecteur annonce et
        ce que notre propre lecteur IFC relit doivent coincider exactement."""
        connecteur = ConnecteurIfcGeneration(dossier=tmp_path)
        resultat = connecteur.executer_confirmee("generer", longueur_m=4.0, hauteur_m=2.5)

        from core.production.ifc_lecture import ouvrir
        fichier = ouvrir(resultat.preuve)
        murs = elements(fichier, "IfcWall")

        assert len(murs) == 1
        assert murs[0].surface_m2 == resultat.detail["surface_m2"]

    def test_url_pointe_vers_media_rendered_quand_le_dossier_est_le_bon(self, tmp_path, monkeypatch):
        import core.connectors.ifc_generation as module
        monkeypatch.setattr(module, "RENDERED_DIR", tmp_path)
        connecteur = ConnecteurIfcGeneration()  # dossier par defaut = RENDERED_DIR

        resultat = connecteur.executer_confirmee("generer", longueur_m=3.0, hauteur_m=2.5)

        assert resultat.detail["url"].startswith("/media/rendered/")

    def test_nom_personnalise_est_repris(self, tmp_path):
        connecteur = ConnecteurIfcGeneration(dossier=tmp_path)
        resultat = connecteur.executer_confirmee(
            "generer", longueur_m=3.0, hauteur_m=2.5, nom="Cloison chambre")

        from core.production.ifc_lecture import ouvrir
        murs = elements(ouvrir(resultat.preuve), "IfcWall")
        assert murs[0].nom == "Cloison chambre"


class TestValidation:
    def test_longueur_non_numerique_est_un_echec(self, tmp_path):
        connecteur = ConnecteurIfcGeneration(dossier=tmp_path)
        resultat = connecteur.executer_confirmee("generer", longueur_m="pas-un-nombre", hauteur_m=2.5)
        assert resultat.statut is Statut.ECHEC

    def test_longueur_hors_bornes_est_un_echec(self, tmp_path):
        connecteur = ConnecteurIfcGeneration(dossier=tmp_path)
        resultat = connecteur.executer_confirmee(
            "generer", longueur_m=LONGUEUR_MAX_M + 1, hauteur_m=2.5)
        assert resultat.statut is Statut.ECHEC

    def test_longueur_negative_est_un_echec(self, tmp_path):
        connecteur = ConnecteurIfcGeneration(dossier=tmp_path)
        resultat = connecteur.executer_confirmee("generer", longueur_m=-1.0, hauteur_m=2.5)
        assert resultat.statut is Statut.ECHEC

    def test_hauteur_hors_bornes_est_un_echec(self, tmp_path):
        connecteur = ConnecteurIfcGeneration(dossier=tmp_path)
        resultat = connecteur.executer_confirmee(
            "generer", longueur_m=3.0, hauteur_m=HAUTEUR_MAX_M + 1)
        assert resultat.statut is Statut.ECHEC

    def test_epaisseur_hors_bornes_est_un_echec(self, tmp_path):
        connecteur = ConnecteurIfcGeneration(dossier=tmp_path)
        resultat = connecteur.executer_confirmee(
            "generer", longueur_m=3.0, hauteur_m=2.5, epaisseur_m=EPAISSEUR_MAX_M + 1)
        assert resultat.statut is Statut.ECHEC


class TestLaVraiePolitiqueLivree:
    def test_generer_reste_sous_write_files_dans_le_depot_reel(self):
        from core.permissions.politique import FICHIER_POLITIQUE, PolitiqueDePermissions

        politique = PolitiqueDePermissions(chemin=FICHIER_POLITIQUE)
        regle = politique.regle("ifc_generation", "document")
        assert regle is not None, "ifc_generation.document a disparu de la politique livree"
        assert regle.get("decision") == "ALLOWED"
        assert regle.get("interrupteur") == "WRITE_FILES"
