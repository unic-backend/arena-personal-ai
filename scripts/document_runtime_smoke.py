"""Smoke test du runtime Docker pour les capacités documentaires natives.

Exécuté DANS l'image finale, sous l'utilisateur normal arena.
"""
from __future__ import annotations

import os
import pwd
import tempfile
from pathlib import Path

from docx import Document as DocxDocument
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader

from apps.backend.config import RENDERED_DIR
from core.actions.resultat import Statut
from core.connectors.file_conversion import ConnecteurFileConversion
from tools.documents.reader import lire_document


def _scan_pdf(dossier: Path) -> Path:
    image = Image.new("RGB", (2480, 3508), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 96)
    draw.text((180, 400), "BONJOUR CHANTIER SENEGAL", font=font, fill="black")
    chemin = dossier / "scan-francais.pdf"
    image.save(chemin, "PDF", resolution=300.0)
    return chemin


def main() -> None:
    assert pwd.getpwuid(os.geteuid()).pw_name == "arena", "smoke test exécuté en root"
    assert os.environ.get("USMAN_API_KEY"), "USMAN_API_KEY requis pour tester le téléchargement"

    with tempfile.TemporaryDirectory(prefix="arena-doc-smoke-") as tmp:
        dossier = Path(tmp)

        # 1. OCR réel d'un PDF image-only, avec le modèle français Tesseract.
        scan = _scan_pdf(dossier)
        lu = lire_document(scan)
        texte = lu.texte.lower()
        assert lu.statut == "LU", lu.raison
        assert "bonjour" in texte and "chantier" in texte, texte
        assert any(p.via_ocr for p in lu.passages)

        # 2. Conversion réelle DOCX -> PDF par LibreOffice.
        source = dossier / "source.docx"
        doc = DocxDocument()
        doc.add_paragraph("Devis chantier Dakar")
        doc.save(source)
        conversion = ConnecteurFileConversion(dossier=dossier).executer(
            "convertir", entree=str(source), format_cible="pdf"
        )
        assert conversion.statut is Statut.SUCCES, conversion.message
        pdf_converti = Path(conversion.preuve)
        assert pdf_converti.is_file() and pdf_converti.stat().st_size > 0
        texte_pdf = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf_converti)).pages)
        assert "Devis chantier Dakar" in texte_pdf

        # 3. Génération PDF réelle + relecture + route de téléchargement protégée.
        genere = ConnecteurFileConversion().executer(
            "rediger",
            texte="# Rapport chantier\n\nDocument généré dans le conteneur.",
            format_cible="pdf",
            titre="smoke-runtime",
        )
        assert genere.statut is Statut.SUCCES, genere.message
        pdf_genere = Path(genere.preuve)
        assert pdf_genere.is_file() and pdf_genere.stat().st_size > 0
        assert len(PdfReader(str(pdf_genere)).pages) >= 1
        url = genere.detail.get("url")
        assert url and url.startswith("/media/rendered/"), genere.detail
        assert pdf_genere.resolve().is_relative_to(RENDERED_DIR.resolve())

        # Import tardif : la clé d'API vient de l'environnement du conteneur.
        from apps.backend.main import app

        client = TestClient(app)
        refuse = client.get(url)
        assert refuse.status_code == 401, refuse.text
        accepte = client.get(url, headers={"Authorization": f"Bearer {os.environ['USMAN_API_KEY']}"})
        assert accepte.status_code == 200, accepte.text
        assert accepte.content.startswith(b"%PDF-") and len(accepte.content) > 100

    print("document-runtime-smoke: OK")


if __name__ == "__main__":
    main()
