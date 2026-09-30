"""Tests de validation des sorties DrawIO XML."""
from __future__ import annotations

import pytest

from core.diagramme.edit_banana import valider_fichier_drawio, valider_xml_drawio
from core.production.conversion.validation import verifier

VALID_MXFILE = """<mxfile host="app.diagrams.net" modified="2026-09-30T10:00:00.000Z" agent="Edit-Banana" version="1.0">
  <diagram id="d1" name="Page-1">
    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <mxCell id="2" value="Box A" vertex="1" parent="1">
          <mxGeometry x="40" y="40" width="80" height="40" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>"""

VALID_MXGRAPHMODEL = """<mxGraphModel dx="800" dy="600">
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
    <mxCell id="2" value="Test" vertex="1" parent="1"/>
  </root>
</mxGraphModel>"""

VALID_DIAGRAM = """<diagram name="Page-1" id="d1">
  <mxGraphModel>
    <root>
      <mxCell id="0"/>
      <mxCell id="1" parent="0"/>
    </root>
  </mxGraphModel>
</diagram>"""

MALFORMED_XML = "<mxfile><diagram>unclosed tags"
EMPTY_XML = ""
WRONG_XML_ROOT = "<svg xmlns='http://www.w3.org/2000/svg'><circle cx='10' cy='10' r='5'/></svg>"
HTML_PAGE = "<html><body><h1>Not a diagram</h1></body></html>"


@pytest.mark.parametrize("xml_content", [VALID_MXFILE, VALID_MXGRAPHMODEL, VALID_DIAGRAM])
def test_validation_xml_valide(xml_content):
    valide, raison = valider_xml_drawio(xml_content)
    assert valide is True
    assert raison == ""


@pytest.mark.parametrize("xml_content,motif", [
    (EMPTY_XML, "vide"),
    (MALFORMED_XML, "XML malformé"),
    (WRONG_XML_ROOT, "Structure DrawIO non reconnue"),
    (HTML_PAGE, "Structure DrawIO non reconnue"),
])
def test_validation_xml_invalide(xml_content, motif):
    valide, raison = valider_xml_drawio(xml_content)
    assert valide is False
    assert motif in raison


def test_valider_fichier_drawio_sur_disque(tmp_path):
    fichier_valide = tmp_path / "diagram.drawio"
    fichier_valide.write_text(VALID_MXFILE, encoding="utf-8")

    valide, raison = valider_fichier_drawio(fichier_valide)
    assert valide is True
    assert raison == ""

    # Test avec la fonction générique du sous-système de conversion
    erreur = verifier(fichier_valide, "drawio")
    assert erreur is None


def test_valider_fichier_drawio_vide_ou_manquant(tmp_path):
    fichier_vide = tmp_path / "vide.drawio"
    fichier_vide.write_bytes(b"")

    valide, raison = valider_fichier_drawio(fichier_vide)
    assert valide is False
    assert "vide" in raison

    erreur = verifier(fichier_vide, "drawio")
    assert "vide" in erreur

    fichier_manquant = tmp_path / "absent.drawio"
    valide_m, raison_m = valider_fichier_drawio(fichier_manquant)
    assert valide_m is False
    assert "introuvable" in raison_m

    erreur_m = verifier(fichier_manquant, "drawio")
    assert "aucun fichier" in erreur_m or "introuvable" in erreur_m
