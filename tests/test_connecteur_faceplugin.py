"""Le connecteur Faceplugin : ce qu'il mesure, et ce qu'il refuse d'inventer.

Le SDK vit **hors du dépôt** (aucune licence déclarée — voir
`test_moteurs_externes_restent_dehors.py`). Les tests ci-dessous tournent donc
avec des doubles, sauf ceux marqués `moteur_reel`, qui sont **sautés** quand le
SDK n'est pas installé plutôt que simulés.

Ce qui compte ici, et c'est la règle de tout ce dépôt : **le connecteur dit ce
qu'il a mesuré, jamais ce qui serait plausible.** Aucun visage inventé, aucun
score de similarité fabriqué, aucune identité déduite d'une base — il n'y en a
pas.
"""
import json
import subprocess
from pathlib import Path

import pytest

from core.connectors import faceplugin as module
from core.connectors.base import EtatSante
from core.connectors.faceplugin import MARQUEUR, ConnecteurFaceplugin

RACINE = Path(__file__).resolve().parent.parent
SDK = RACINE / "tools" / "vision" / "faceplugin" / "Open-Source-Face-Recognition-SDK"

moteur_reel = pytest.mark.skipif(
    not (SDK / "run.py").is_file(),
    reason="SDK Faceplugin non installe : mesure impossible, donc non simulee")


def _reponse(charge: dict, bavardage: str = "") -> subprocess.CompletedProcess:
    """Ce que rend vraiment le moteur : son bavardage, puis la ligne marquée."""
    return subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout=f"{bavardage}\n{MARQUEUR}{json.dumps(charge)}\n", stderr="")


@pytest.fixture
def installe(monkeypatch, tmp_path):
    """Fait croire que le SDK est là, sans le lancer."""
    run = tmp_path / "run.py"
    run.write_text("")
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("")
    monkeypatch.setattr(module, "FACEPLUGIN_ROOT", tmp_path)
    monkeypatch.setattr(module, "FACEPLUGIN_RUN", run)
    monkeypatch.setattr(module, "_python_du_sdk", lambda: python)
    return tmp_path


class TestSonde:
    def test_moteur_absent_nest_pas_une_panne(self, monkeypatch, tmp_path):
        """Rien n'est cassé : rien n'est installé. Même distinction que pour
        Xaar Kaname — dire « en panne » enverrait réparer une installation qui
        n'a jamais existé."""
        monkeypatch.setattr(module, "FACEPLUGIN_ROOT", tmp_path / "nulle_part")
        sante = ConnecteurFaceplugin().sonder()

        assert sante.etat == EtatSante.NON_CONFIGURE
        assert sante.ce_qui_manque

    def test_un_venv_sans_dependances_est_une_panne(self, installe, monkeypatch):
        """**Le contrôle qui compte.** Un `.venv` existe très bien sans torch.

        Conclure « opérationnel » de la présence des fichiers annoncerait une
        capacité qui échouerait au premier appel.
        """
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _reponse(
            {"ok": False, "erreur": "ModuleNotFoundError: No module named 'torch'"}))

        sante = ConnecteurFaceplugin().sonder()

        assert sante.etat == EtatSante.EN_PANNE
        assert "torch" in sante.ce_qui_manque


def _cap(nom):
    return ConnecteurFaceplugin().capacites()[nom]


class TestRefus:
    def test_sans_le_sdk_rien_nest_tente(self, monkeypatch, tmp_path):
        monkeypatch.setattr(module, "FACEPLUGIN_ROOT", tmp_path / "nulle_part")
        monkeypatch.setattr(module, "FACEPLUGIN_RUN", tmp_path / "nulle_part" / "run.py")
        lance = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: lance.append(a))

        resultat = ConnecteurFaceplugin()._executer(
            _cap("detecter"), image=str(tmp_path))

        assert resultat.statut.value == "NOT_CONFIGURED"
        assert lance == []

    def test_comparer_exige_deux_images(self, installe, tmp_path, monkeypatch):
        """Comparer une image avec elle-même rendrait 100 — un score qui se
        lirait comme un résultat."""
        image = tmp_path / "a.jpg"
        image.write_bytes(b"x")
        lance = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: lance.append(a))

        resultat = ConnecteurFaceplugin()._executer(_cap("comparer"), image=str(image))

        assert resultat.statut.value != "SUCCESS"
        assert lance == [], "le moteur a ete lance sans seconde image"

    def test_aucun_score_quand_aucun_visage(self, installe, tmp_path, monkeypatch):
        """**Le refus le plus important.** Sans visage il n'y a rien à
        comparer : on le dit, on ne rend pas 0. Un 0 se lirait « comparées,
        très différentes »."""
        for nom in ("a.jpg", "b.jpg"):
            (tmp_path / nom).write_bytes(b"x")
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _reponse({
            "ok": False, "erreur": "aucun visage detecte dans la premiere image",
            "nombre_image1": 0, "nombre_image2": 1}))

        resultat = ConnecteurFaceplugin()._executer(
            _cap("comparer"), image=str(tmp_path / "a.jpg"),
            image2=str(tmp_path / "b.jpg"))

        assert resultat.statut.value != "SUCCESS"
        assert "score" not in (resultat.detail or {})

    def test_zero_visage_est_un_resultat_pas_une_panne(self, installe, tmp_path, monkeypatch):
        """Une image sans visage est une réponse légitime du moteur."""
        image = tmp_path / "mur.jpg"
        image.write_bytes(b"x")
        monkeypatch.setattr(subprocess, "run",
                            lambda *a, **k: _reponse({"ok": True, "nombre": 0}))

        resultat = ConnecteurFaceplugin()._executer(_cap("detecter"), image=str(image))

        assert resultat.statut.value == "SUCCESS"
        assert (resultat.detail or {})["nombre"] == 0


class TestProtocole:
    def test_le_bavardage_du_moteur_nest_pas_lu_comme_une_reponse(
            self, installe, tmp_path, monkeypatch):
        """**Mesuré le 03/09/2026.** Le SDK imprime « priors nums:4420 » sur la
        même sortie que le pont. Sans marqueur, une mesure réussie se
        rapportait en panne — « sortie illisible »."""
        image = tmp_path / "a.jpg"
        image.write_bytes(b"x")
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _reponse(
            {"ok": True, "nombre": 1, "boites": [[1, 2, 3, 4]], "scores": [0.9]},
            bavardage="priors nums:4420"))

        resultat = ConnecteurFaceplugin()._executer(_cap("detecter"), image=str(image))

        assert resultat.statut.value == "SUCCESS"
        assert (resultat.detail or {})["nombre"] == 1

    def test_detecter_ne_ramene_aucun_gabarit_biometrique(
            self, installe, tmp_path, monkeypatch):
        """Détecter ne dit pas QUI. Faire voyager les caractéristiques « au cas
        où » ferait circuler de la biométrie à chaque comptage de visages."""
        image = tmp_path / "a.jpg"
        image.write_bytes(b"x")
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _reponse(
            {"ok": True, "nombre": 1, "boites": [[1, 2, 3, 4]], "scores": [0.9]}))

        resultat = ConnecteurFaceplugin()._executer(_cap("detecter"), image=str(image))

        assert "caracteristiques" not in (resultat.detail or {})


class TestPermissions:
    def test_la_biometrie_passe_par_une_confirmation(self):
        """La frontière est l'identité : compter des visages est une lecture,
        extraire un gabarit et comparer produisent de la biométrie."""
        import yaml
        regles = yaml.safe_load(
            (RACINE / "config" / "permissions_services.yaml").read_text(encoding="utf-8"))
        service = regles["services"]["biometrie_visage"]

        assert service["read"]["decision"] == "ALLOWED"
        assert service["biometrie"]["decision"] == "CONFIRMATION"
        assert service["biometrie"]["risque"] == "HIGH"

    def test_les_capacites_declarent_la_bonne_action(self):
        capacites = ConnecteurFaceplugin().capacites()

        assert capacites["detecter"].action == "read"
        assert capacites["reperes"].action == "read"
        for nom in ("caracteristiques", "comparer"):
            assert capacites[nom].action == "biometrie", (
                f"{nom} passerait en lecture : plus aucune confirmation")
            assert capacites[nom].ecriture is True

    def test_aucune_capacite_ne_cherche_dans_une_base(self):
        """Pas d'identification implicite : le connecteur n'expose rien qui
        interroge une collection de visages. Comparer prend deux images dans
        le même appel."""
        capacites = set(ConnecteurFaceplugin().capacites())

        assert capacites == {"detecter", "reperes", "caracteristiques", "comparer"}
        # On cherche des DEFINITIONS, pas des mots. Le premier essai
        # cherchait « identifier » dans tout le fichier et tombait sur la
        # docstring qui explique justement qu'on n'identifie personne : un
        # test qui echoue sur sa propre explication ne mesure rien.
        import ast
        source = (RACINE / "core" / "connectors" / "faceplugin.py").read_text(encoding="utf-8")
        noms = {n.name for n in ast.walk(ast.parse(source))
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        for interdit in ("identifier", "rechercher_visage", "base_de_visages", "enroler"):
            assert not any(interdit in nom for nom in noms), (
                f"une fonction « {interdit} » ouvrirait l'identification implicite")


class TestMoteurReel:
    """Le SDK, pour de vrai. Sauté s'il n'est pas installé — jamais simulé."""

    @moteur_reel
    def test_le_moteur_repond(self):
        assert ConnecteurFaceplugin().sonder().etat == EtatSante.OPERATIONNEL

    @moteur_reel
    def test_il_trouve_un_visage_et_ses_68_reperes(self):
        connecteur = ConnecteurFaceplugin()
        image = str(SDK / "test" / "1.jpg")

        detection = connecteur._executer(connecteur.capacites()["detecter"], image=image)
        reperes = connecteur._executer(connecteur.capacites()["reperes"], image=image)

        assert (detection.detail or {})["nombre"] >= 1
        assert len((reperes.detail or {})["reperes"][0]) == 136, "68 points, x et y"

    @moteur_reel
    def test_une_image_comparee_a_elle_meme_donne_le_maximum(self):
        """Le contrôle de bon sens qui prouve que le score n'est pas fabriqué :
        une image contre elle-même doit saturer l'échelle."""
        connecteur = ConnecteurFaceplugin()
        image = str(SDK / "test" / "1.jpg")

        resultat = connecteur._executer(
            connecteur.capacites()["comparer"], image=image, image2=image)

        assert resultat.statut.value == "SUCCESS"
        assert (resultat.detail or {})["score"] == pytest.approx(100.0, abs=0.5)
