"""Tests du connecteur et de la configuration du moteur Edit-Banana."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.edit_banana import ConnecteurEditBanana
from core.diagramme.edit_banana import (
    ConfigurationEditBanana,
    ErreurEditBanana,
    ResultatDiagramme,
    ServiceEditBanana,
)

SAMPLE_DRAWIO_XML = """<mxfile host="arena" modified="2026-09-30T12:00:00.000Z" agent="Edit-Banana" version="1.0">
  <diagram id="diagram_1" name="Page-1">
    <mxGraphModel dx="1000" dy="1000" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="827" pageHeight="1169">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <mxCell id="2" value="Module A" style="rounded=0;whiteSpace=wrap;html=1;" vertex="1" parent="1">
          <mxGeometry x="120" y="120" width="120" height="60" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>"""


@pytest.fixture
def fake_edit_banana_tree(tmp_path) -> tuple[Path, Path, Path]:
    racine = tmp_path / "Edit-Banana"
    racine.mkdir(parents=True)
    (racine / "main.py").write_text("# double CLI", encoding="utf-8")
    (racine / "requirements.txt").write_text("torch\ntorchvision\n", encoding="utf-8")
    (racine / "models").mkdir(parents=True)
    sam3_ckpt = racine / "models" / "sam3.pt"
    sam3_ckpt.write_bytes(b"poids-sam3-double")

    python_bin = racine / ".venv" / "bin" / "python"
    python_bin.parent.mkdir(parents=True)
    python_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    python_bin.chmod(0o755)

    return racine, python_bin, sam3_ckpt


def test_connecteur_non_configure_quand_racine_manquante(tmp_path):
    config = ConfigurationEditBanana(
        racine=None,
        python=None,
        sam3_checkpoint=None,
        sorties=tmp_path / "rendered" / "diagrams",
        licence_acceptee=True,
    )
    service = ServiceEditBanana(config)
    connecteur = ConnecteurEditBanana(configuration=config, service_moteur=service)

    sante = connecteur.sonder()
    assert sante.etat == EtatSante.NON_CONFIGURE
    assert not sante.utilisable
    assert "USMAN_EDIT_BANANA_ROOT" in sante.ce_qui_manque or "USMAN_EDIT_BANANA_ROOT" in sante.message


def test_connecteur_non_configure_quand_licence_non_acceptee(fake_edit_banana_tree, tmp_path):
    racine, python_bin, sam3_ckpt = fake_edit_banana_tree
    config = ConfigurationEditBanana(
        racine=racine,
        python=python_bin,
        sam3_checkpoint=sam3_ckpt,
        sorties=tmp_path / "rendered" / "diagrams",
        licence_acceptee=False,
        verifier_runtime=False,
        verifier_revision=False,
    )
    service = ServiceEditBanana(config)
    connecteur = ConnecteurEditBanana(configuration=config, service_moteur=service)

    sante = connecteur.sonder()
    assert sante.etat == EtatSante.NON_CONFIGURE
    assert "LICENSE" in sante.ce_qui_manque or "licence" in sante.message.lower()


def test_connecteur_non_configure_quand_sam3_manquant(fake_edit_banana_tree, tmp_path):
    racine, python_bin, sam3_ckpt = fake_edit_banana_tree
    sam3_ckpt.unlink()

    config = ConfigurationEditBanana(
        racine=racine,
        python=python_bin,
        sam3_checkpoint=racine / "models" / "sam3.pt",
        sorties=tmp_path / "rendered" / "diagrams",
        licence_acceptee=True,
        verifier_runtime=False,
        verifier_revision=False,
    )
    service = ServiceEditBanana(config)
    connecteur = ConnecteurEditBanana(configuration=config, service_moteur=service)

    sante = connecteur.sonder()
    assert sante.etat == EtatSante.NON_CONFIGURE
    assert "sam3" in sante.message.lower() or "sam3" in sante.ce_qui_manque.lower()


def test_connecteur_en_panne_quand_point_entree_absent(fake_edit_banana_tree, tmp_path):
    racine, python_bin, sam3_ckpt = fake_edit_banana_tree
    (racine / "main.py").unlink()

    config = ConfigurationEditBanana(
        racine=racine,
        python=python_bin,
        sam3_checkpoint=sam3_ckpt,
        sorties=tmp_path / "rendered" / "diagrams",
        licence_acceptee=True,
        verifier_runtime=False,
        verifier_revision=False,
    )
    service = ServiceEditBanana(config)
    connecteur = ConnecteurEditBanana(configuration=config, service_moteur=service)

    sante = connecteur.sonder()
    assert sante.etat == EtatSante.EN_PANNE
    assert "main.py" in sante.message or "main.py" in sante.ce_qui_manque


def test_connecteur_operationnel_quand_tout_est_configure(fake_edit_banana_tree, tmp_path):
    racine, python_bin, sam3_ckpt = fake_edit_banana_tree

    config = ConfigurationEditBanana(
        racine=racine,
        python=python_bin,
        sam3_checkpoint=sam3_ckpt,
        sorties=tmp_path / "rendered" / "diagrams",
        licence_acceptee=True,
        verifier_runtime=False,
        verifier_revision=False,
    )
    service = ServiceEditBanana(config)
    connecteur = ConnecteurEditBanana(configuration=config, service_moteur=service)

    sante = connecteur.sonder()
    assert sante.etat == EtatSante.OPERATIONNEL
    assert sante.utilisable
    assert connecteur.authentifier() is True


def test_execution_connecteur_succes_avec_mock_service(tmp_path, monkeypatch):
    sorties = tmp_path / "rendered" / "diagrams"
    sorties.mkdir(parents=True)
    fichier_drawio = sorties / "diagramme-test.drawio"
    fichier_drawio.write_text(SAMPLE_DRAWIO_XML, encoding="utf-8")
    provenance = fichier_drawio.with_suffix(".drawio.json")
    provenance.write_text('{"operation": "diagram_to_drawio"}', encoding="utf-8")

    resultat_mock = ResultatDiagramme(
        sortie=fichier_drawio,
        url="/media/rendered/diagrams/diagramme-test.drawio",
        provenance=provenance,
        format_cible="drawio",
        largeur=800,
        hauteur=600,
        taille_octets=fichier_drawio.stat().st_size,
        device="cpu",
        duree_secondes=1.2,
        source_sha256="abc123sha",
        limites_qualite="Test notice",
    )

    class MockService:
        def etat(self):
            from core.diagramme.edit_banana import EtatEditBanana
            return EtatEditBanana(
                disponible=True, raison="OK", ce_qui_manque="", device="cpu",
                cpu_lent=True, sam3_disponible=True, version="88c6e28",
            )

        async def convertir(self, source, nom_source="diagram.png"):
            return resultat_mock

    connecteur = ConnecteurEditBanana(service_moteur=MockService())
    action_res = connecteur.executer("diagram_to_drawio", image=str(fichier_drawio))

    assert action_res.statut == Statut.SUCCES
    assert action_res.preuve == str(fichier_drawio)
    assert action_res.detail["url"] == "/media/rendered/diagrams/diagramme-test.drawio"
    assert action_res.detail["format_cible"] == "drawio"
    assert action_res.detail["moteur"] == "Edit-Banana"


def test_execution_connecteur_echec_quand_service_leve(monkeypatch):
    class MockServiceEchec:
        def etat(self):
            from core.diagramme.edit_banana import EtatEditBanana
            return EtatEditBanana(
                disponible=True, raison="OK", ce_qui_manque="", device="cpu",
                cpu_lent=True, sam3_disponible=True, version="88c6e28",
            )

        async def convertir(self, source, nom_source="diagram.png"):
            raise ErreurEditBanana("Erreur interne lors de l'inférence SAM3")

    connecteur = ConnecteurEditBanana(service_moteur=MockServiceEchec())
    action_res = connecteur.executer("diagram_to_drawio", image="/tmp/fake.png")

    assert action_res.statut == Statut.ECHEC
    assert "inférence SAM3" in action_res.message
