"""Le connecteur Xaar Kaname : ce qu'il mesure, et ce qu'il refuse.

Le moteur (Deep-Live-Cam, AGPL-3.0) vit **hors** du depot — la regle et sa
raison sont dans `test_xaar_kaname_reste_dehors.py`. Il n'est donc installe sur
aucune machine de test, et ces tests ne le lancent jamais : ils mesurent le
connecteur, qui est la seule partie qui appartient a ARENA.

Ce qui compte ici : le connecteur doit **dire son etat** au lieu de le
supposer, et **refuser plutot que produire un resultat plausible** quand une
entree manque. Un moteur qui ne tourne pas ne rend pas un fichier ; il rend
une raison.
"""
import subprocess
from pathlib import Path

import pytest

from core.connectors import xaar_kaname as module
from core.connectors.base import EtatSante
from core.connectors.xaar_kaname import XaarKanameConnector


def _installer_faux_moteur(tmp_path: Path, monkeypatch, avec_python=True, avec_run=True):
    """Pose sur le disque la forme d'une installation, sans le moteur."""
    racine = tmp_path / "Deep-Live-Cam"
    racine.mkdir()
    python = racine / ".venv" / "Scripts" / "python.exe"
    run = racine / "run.py"
    if avec_python:
        python.parent.mkdir(parents=True)
        python.write_text("")
    if avec_run:
        run.write_text("")
    monkeypatch.setattr(module, "XAAR_ROOT", racine)
    monkeypatch.setattr(module, "XAAR_PYTHON", python)
    monkeypatch.setattr(module, "XAAR_RUN", run)
    return racine


class TestSonde:
    """Trois etats, pas deux. La distinction est celle que lit le
    proprietaire dans `scripts/doctor.py`."""

    def test_moteur_absent_nest_pas_une_panne(self, tmp_path, monkeypatch):
        """Rien n'est casse : rien n'est installe.

        `EN_PANNE` enverrait le proprietaire reparer une installation qui n'a
        jamais existe. Tous les autres moteurs externes du depot (WanGP,
        MoneyPrinterTurbo, VoiceStudio, OpenTakeoff) rendent `NON_CONFIGURE`
        quand ils sont absents.
        """
        monkeypatch.setattr(module, "XAAR_ROOT", tmp_path / "nulle_part")
        sante = XaarKanameConnector().sonder()

        assert sante.etat == EtatSante.NON_CONFIGURE
        assert sante.ce_qui_manque, "un « introuvable » sans le chemin cherche n'aide personne"

    def test_installation_incomplete_est_une_panne(self, tmp_path, monkeypatch):
        """Le dossier existe mais `.venv` manque : une installation a
        commence et n'est pas allee au bout. La, il y a a reparer."""
        _installer_faux_moteur(tmp_path, monkeypatch, avec_python=False)
        sante = XaarKanameConnector().sonder()

        assert sante.etat == EtatSante.EN_PANNE
        assert ".venv" in sante.ce_qui_manque

    def test_run_py_absent_est_une_panne(self, tmp_path, monkeypatch):
        _installer_faux_moteur(tmp_path, monkeypatch, avec_run=False)
        sante = XaarKanameConnector().sonder()

        assert sante.etat == EtatSante.EN_PANNE
        assert "run.py" in sante.ce_qui_manque

    def test_installation_complete_est_operationnelle(self, tmp_path, monkeypatch):
        _installer_faux_moteur(tmp_path, monkeypatch)
        sante = XaarKanameConnector().sonder()

        assert sante.etat == EtatSante.OPERATIONNEL
        assert sante.utilisable


class TestRefus:
    """Une entree absente rend une raison, jamais un fichier invente."""

    def _capacite(self):
        return XaarKanameConnector().capacites()["traiter"]

    def test_source_absente_refuse_sans_lancer_le_moteur(self, tmp_path, monkeypatch):
        """Le moteur ne doit meme pas etre lance : le lancer sur un fichier
        qui n'existe pas ferait payer plusieurs minutes de GPU pour une erreur
        connue d'avance."""
        _installer_faux_moteur(tmp_path, monkeypatch)
        lance = []
        monkeypatch.setattr(subprocess, "run",
                            lambda *a, **k: lance.append(a) or pytest.fail("moteur lance"))

        cible = tmp_path / "cible.jpg"
        cible.write_bytes(b"x")
        connecteur = XaarKanameConnector()
        resultat = connecteur._executer(
            self._capacite(),
            source=str(tmp_path / "pas_la.jpg"), target=str(cible),
            output=str(tmp_path / "out.jpg"))

        assert resultat.statut.value != "SUCCESS"
        assert lance == []

    def test_sortie_manquante_apres_le_moteur_est_un_echec(self, tmp_path, monkeypatch):
        """**Le controle qui compte.** Un code de retour 0 ne prouve pas qu'un
        fichier a ete produit : Deep-Live-Cam peut terminer proprement sans
        rien ecrire (aucun visage detecte). Sans ce controle, ARENA
        annoncerait un artefact qui n'existe pas.
        """
        _installer_faux_moteur(tmp_path, monkeypatch)
        source = tmp_path / "s.jpg"
        cible = tmp_path / "c.jpg"
        source.write_bytes(b"s")
        cible.write_bytes(b"c")

        class Faux:
            returncode = 0
            stdout = ""
            stderr = ""

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: Faux())

        resultat = XaarKanameConnector()._executer(
            self._capacite(),
            source=str(source), target=str(cible),
            output=str(tmp_path / "jamais_ecrit.jpg"))

        assert resultat.statut.value != "SUCCESS"
        assert "jamais_ecrit.jpg" in (resultat.message or "")


class TestProtection:
    """L'ecriture passe par une confirmation. C'est la capacite elle-meme qui
    le declare, et `config/permissions_services.yaml` qui l'applique."""

    def test_traiter_est_declaree_en_ecriture(self):
        capacite = XaarKanameConnector().capacites()["traiter"]

        assert capacite.ecriture is True, (
            "sans `ecriture=True`, la generation ne demanderait aucune "
            "confirmation et partirait toute seule")
        assert capacite.action == "generate"

    def test_le_service_est_celui_que_la_regle_protege(self):
        assert XaarKanameConnector().service == "video_generation"

    def test_la_regle_exige_bien_une_confirmation(self):
        """La protection est dans un fichier de configuration : un test la
        mesure, sinon elle se fait retirer sans que rien ne tombe."""
        import yaml
        racine = Path(__file__).resolve().parent.parent
        regles = yaml.safe_load(
            (racine / "config" / "permissions_services.yaml").read_text(encoding="utf-8"))

        assert regles["services"]["video_generation"]["generate"]["decision"] == "CONFIRMATION"
