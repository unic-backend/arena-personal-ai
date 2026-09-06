"""Le connecteur IFC : lecture reelle d'un fichier IFC via IfcOpenShell,
jamais une geometrie recalculee ni un second moteur BIM.

`tests/fixtures/ifc/exemple.ifc` est un vrai fichier IFC4, engendre par
IfcOpenShell lui-meme (son API `ifcopenshell.api`, jamais ecrit a la main) :
2 niveaux, 3 murs (deux avec une quantite `Qto_WallBaseQuantities` exploitable,
un troisieme sans aucune), 1 porte, 1 fenetre. Aucun mock ici : IfcOpenShell
est reellement installe (offline, pas de reseau) et lit ce vrai fichier.
"""
from pathlib import Path

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.ifc import ConnecteurIfc

FIXTURE = str(Path(__file__).resolve().parents[1] / "fixtures" / "ifc" / "exemple.ifc")


class TestCapacites:
    def test_trois_capacites_de_lecture(self):
        capacites = ConnecteurIfc().capacites()
        assert set(capacites) == {"analyser", "elements", "metre"}
        assert all(c.ecriture is False for c in capacites.values())
        assert all(c.action == "read" for c in capacites.values())


class TestSonde:
    def test_ifcopenshell_installe_est_operationnel(self):
        sante = ConnecteurIfc().sonder()
        assert sante.etat is EtatSante.OPERATIONNEL


class TestValidationDuChemin:
    def test_sans_chemin_est_un_echec(self):
        resultat = ConnecteurIfc().executer_confirmee("analyser", chemin="")
        assert resultat.statut is Statut.ECHEC

    def test_fichier_absent_est_un_echec(self):
        resultat = ConnecteurIfc().executer_confirmee("analyser", chemin="/x/n-existe-pas.ifc")
        assert resultat.statut is Statut.ECHEC
        assert "Aucun fichier" in resultat.message

    def test_extension_autre_que_ifc_est_un_echec(self, tmp_path):
        pdf = tmp_path / "plan.pdf"
        pdf.write_text("pas un IFC")
        resultat = ConnecteurIfc().executer_confirmee("analyser", chemin=str(pdf))
        assert resultat.statut is Statut.ECHEC
        assert "n'est pas un .ifc" in resultat.message

    def test_fichier_trop_volumineux_est_un_echec(self, tmp_path, monkeypatch):
        gros = tmp_path / "gros.ifc"
        gros.write_text("ISO-10303-21;")
        monkeypatch.setattr(
            "core.connectors.ifc.TAILLE_MAX_OCTETS", 1)  # 1 octet : le fichier le depasse forcement
        resultat = ConnecteurIfc().executer_confirmee("analyser", chemin=str(gros))
        assert resultat.statut is Statut.ECHEC
        assert "trop volumineux" in resultat.message

    def test_fichier_corrompu_est_un_echec_jamais_un_crash(self, tmp_path):
        casse = tmp_path / "casse.ifc"
        casse.write_text("ceci n'est pas un fichier IFC valide")
        resultat = ConnecteurIfc().executer_confirmee("analyser", chemin=str(casse))
        assert resultat.statut is Statut.ECHEC
        assert "illisible" in resultat.message


class TestAnalyser:
    def test_niveaux_et_comptes_reels(self):
        resultat = ConnecteurIfc().executer_confirmee("analyser", chemin=FIXTURE)

        assert resultat.statut is Statut.SUCCES, resultat.message
        assert resultat.detail["niveaux"] == ["Niveau 1", "Niveau 2"]
        assert resultat.detail["comptes"]["mur"] == 3
        assert resultat.detail["comptes"]["porte"] == 1
        assert resultat.detail["comptes"]["fenetre"] == 1
        assert resultat.detail["elements_par_niveau"]["Niveau 1"]["mur"] == 2

    def test_preuve_est_le_chemin(self):
        resultat = ConnecteurIfc().executer_confirmee("analyser", chemin=FIXTURE)
        assert resultat.preuve == FIXTURE


class TestElements:
    def test_murs_filtres_par_niveau(self):
        resultat = ConnecteurIfc().executer_confirmee(
            "elements", chemin=FIXTURE, type="mur", niveau="Niveau 1")

        assert resultat.statut is Statut.SUCCES, resultat.message
        noms = {e["nom"] for e in resultat.detail["elements"]}
        assert noms == {"Cloison BA13 - salon", "Cloison sans metre"}

    def test_portes_du_fichier(self):
        resultat = ConnecteurIfc().executer_confirmee("elements", chemin=FIXTURE, type="porte")

        assert resultat.statut is Statut.SUCCES
        assert len(resultat.detail["elements"]) == 1
        assert resultat.detail["elements"][0]["nom"] == "Porte salon"

    def test_type_inconnu_est_un_echec(self):
        resultat = ConnecteurIfc().executer_confirmee("elements", chemin=FIXTURE, type="ascenseur")

        assert resultat.statut is Statut.ECHEC
        assert "Type inconnu" in resultat.message

    def test_le_materiau_du_premier_mur_est_lu(self):
        resultat = ConnecteurIfc().executer_confirmee("elements", chemin=FIXTURE, type="mur")
        murs = {e["nom"]: e for e in resultat.detail["elements"]}
        assert murs["Cloison BA13 - salon"]["materiau"] == "Placo BA13"
        assert murs["Cloison sans metre"]["materiau"] is None


class TestMetre:
    def test_somme_les_murs_avec_quantite_exploitable(self):
        resultat = ConnecteurIfc().executer_confirmee("metre", chemin=FIXTURE)

        assert resultat.statut is Statut.SUCCES, resultat.message
        assert resultat.detail["surface_m2"] == 33.5
        assert resultat.detail["murs"] == 3
        assert resultat.detail["elements_chiffres"] == 2

    def test_le_mur_sans_quantite_est_nomme_jamais_estime(self):
        """La regle mission (« quand les donnees geometriques le permettent »,
        jamais une geometrie recalculee ici) : un mur sans Qto exploitable
        est absent du total, nomme explicitement."""
        resultat = ConnecteurIfc().executer_confirmee("metre", chemin=FIXTURE)

        assert "Cloison sans metre" in resultat.detail["elements_sans_quantite"]

    def test_metre_filtre_par_niveau(self):
        resultat = ConnecteurIfc().executer_confirmee("metre", chemin=FIXTURE, niveau="Niveau 2")

        assert resultat.statut is Statut.SUCCES
        assert resultat.detail["murs"] == 1
        assert resultat.detail["surface_m2"] == 20.0


class TestSansIfcOpenShellInstalle:
    """Mesure du meme defaut que txtai (DEC-0051) : une bibliotheque optionnelle
    importee en tete de fichier fait planter TOUT ARENA au demarrage des
    qu'elle manque, puisque chaque module cascade par
    `apps/backend/runtime.py`. Les deux modules IFC importent IfcOpenShell
    localement (`TYPE_CHECKING` + import dans la fonction) : ce test le
    verifie en bloquant reellement l'import, pas en le supposant."""

    def test_les_modules_s_importent_sans_ifcopenshell_installe(self, monkeypatch):
        import builtins
        import importlib

        import core.connectors.ifc as connecteur_module
        import core.production.ifc_lecture as production_module

        reel = builtins.__import__

        def bloque_ifcopenshell(name, *args, **kwargs):
            if name == "ifcopenshell" or name.startswith("ifcopenshell."):
                raise ModuleNotFoundError("No module named 'ifcopenshell'")
            return reel(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", bloque_ifcopenshell)
        try:
            importlib.reload(production_module)
            importlib.reload(connecteur_module)
        finally:
            monkeypatch.undo()
            importlib.reload(production_module)
            importlib.reload(connecteur_module)

    def test_sonde_non_configuree_sans_ifcopenshell(self, monkeypatch):
        import builtins

        reel = builtins.__import__

        def bloque_ifcopenshell(name, *args, **kwargs):
            if name == "ifcopenshell" or name.startswith("ifcopenshell."):
                raise ModuleNotFoundError("No module named 'ifcopenshell'")
            return reel(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", bloque_ifcopenshell)
        sante = ConnecteurIfc().sonder()

        assert sante.etat is EtatSante.NON_CONFIGURE
        assert "ifcopenshell" in sante.ce_qui_manque.lower()

    def test_executer_sans_ifcopenshell_rend_non_configure_jamais_un_crash(self, monkeypatch):
        import builtins

        reel = builtins.__import__

        def bloque_ifcopenshell(name, *args, **kwargs):
            if name == "ifcopenshell" or name.startswith("ifcopenshell."):
                raise ModuleNotFoundError("No module named 'ifcopenshell'")
            return reel(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", bloque_ifcopenshell)
        resultat = ConnecteurIfc().executer_confirmee("analyser", chemin=FIXTURE)

        assert resultat.statut is Statut.NON_CONFIGURE


class TestLaVraiePolitiqueLivree:
    def test_lire_reste_allowed_dans_le_depot_reel(self):
        from core.permissions.politique import FICHIER_POLITIQUE, PolitiqueDePermissions

        regle = PolitiqueDePermissions(chemin=FICHIER_POLITIQUE).regle("ifc", "read")
        assert regle is not None, "ifc.read a disparu de la politique livree"
        assert regle.get("decision") == "ALLOWED"
