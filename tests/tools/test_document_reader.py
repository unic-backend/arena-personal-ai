"""Lecture des documents du propriétaire.

Les fichiers d'essai sont de **vrais** PDF et de **vrais** `.docx`, fabriqués
dans le test : un lecteur de PDF vérifié sur une chaîne de caractères ne prouve
rien.
"""
import pytest

from tools.documents.reader import Passage, lire_document

pytest.importorskip("pypdf", reason="pypdf n'est pas installe.")
pytest.importorskip("docx", reason="python-docx n'est pas installe.")


def fabriquer_pdf(pages: list[str]) -> bytes:
    """Construit un PDF valide, une page par entrée, sans dépendance d'écriture."""
    flux = []
    for texte in pages:
        echappe = texte.replace("\\\\", r"\\\\").replace("(", r"\(").replace(")", r"\)")
        flux.append(f"BT /F1 12 Tf 72 720 Td ({echappe}) Tj ET".encode("latin-1"))

    n = len(pages)
    objets = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{' '.join(f'{3 + 2 * i} 0 R' for i in range(n))}] "
        f"/Count {n} >>".encode(),
    ]
    for i, f in enumerate(flux):
        objets.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {4 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 {3 + 2 * n} 0 R >> >> >>".encode()
        )
        objets.append(b"<< /Length " + str(len(f)).encode() + b" >>\nstream\n" + f + b"\nendstream")
    objets.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    sortie, positions = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objets, 1):
        positions.append(len(sortie))
        sortie += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    debut = len(sortie)
    sortie += f"xref\n0 {len(objets) + 1}\n0000000000 65535 f \n".encode()
    for p in positions:
        sortie += f"{p:010d} 00000 n \n".encode()
    sortie += (f"trailer\n<< /Size {len(objets) + 1} /Root 1 0 R >>\n"
               f"startxref\n{debut}\n%%EOF\n").encode()
    return bytes(sortie)


@pytest.fixture
def devis_pdf(tmp_path):
    chemin = tmp_path / "devis_2026_041.pdf"
    chemin.write_bytes(fabriquer_pdf([
        "Devis numero 2026-041 - cloison BA13 salon",
        "Total HT 450000 FCFA - validite 30 jours",
    ]))
    return chemin


@pytest.fixture
def facture_docx(tmp_path):
    from docx import Document as DocxDocument

    document = DocxDocument()
    document.add_paragraph("Facture 2026-118 - UniC Plaquiste")
    tableau = document.add_table(rows=2, cols=3)
    tableau.rows[0].cells[0].text = "Designation"
    tableau.rows[0].cells[1].text = "Quantite"
    tableau.rows[0].cells[2].text = "Prix"
    tableau.rows[1].cells[0].text = "Plaque BA13"
    tableau.rows[1].cells[1].text = "40"
    tableau.rows[1].cells[2].text = "180000"

    chemin = tmp_path / "facture_2026_118.docx"
    document.save(str(chemin))
    return chemin


# --- PDF -----------------------------------------------------------------------

def test_un_pdf_est_lu_page_par_page(devis_pdf):
    document = lire_document(devis_pdf)

    assert document.lu
    assert len(document.passages) == 2
    assert "cloison BA13" in document.passages[0].texte
    assert "450000" in document.passages[1].texte


def test_chaque_passage_d_un_pdf_garde_son_numero_de_page(devis_pdf):
    """Sans la page, une réponse ne peut pas citer précisément sa source."""
    document = lire_document(devis_pdf)

    assert [p.page for p in document.passages] == [1, 2]
    assert document.passages[1].source == "devis_2026_041.pdf, page 2"


def test_un_pdf_sans_texte_est_signale_pas_invente(tmp_path):
    """Un PDF scanné ne contient que des images : le dire vaut mieux que deviner."""
    chemin = tmp_path / "scan.pdf"
    chemin.write_bytes(fabriquer_pdf([""]))

    document = lire_document(chemin)

    assert document.statut == "VIDE"
    assert "scanne" in document.raison
    assert document.texte == ""


def test_un_pdf_corrompu_ne_fait_pas_tomber_la_lecture(tmp_path):
    chemin = tmp_path / "casse.pdf"
    chemin.write_bytes(b"%PDF-1.4\nceci n'est pas un PDF valide")

    document = lire_document(chemin)

    assert document.statut in {"ECHEC", "VIDE"}
    assert document.raison


# --- Word ----------------------------------------------------------------------

def test_un_docx_est_lu(facture_docx):
    document = lire_document(facture_docx)

    assert document.lu
    assert "Facture 2026-118" in document.texte


def test_le_contenu_des_tableaux_est_conserve(facture_docx):
    """Un devis vit souvent dans un tableau : l'ignorer viderait le document."""
    document = lire_document(facture_docx)

    assert "Plaque BA13" in document.texte
    assert "180000" in document.texte
    assert "Designation | Quantite | Prix" in document.texte


# --- Texte ---------------------------------------------------------------------

@pytest.mark.parametrize("extension", [".txt", ".md", ".csv"])
def test_un_fichier_texte_est_lu(tmp_path, extension):
    chemin = tmp_path / f"note{extension}"
    chemin.write_text("Chantier Almadies\nCloison 12 m2", encoding="utf-8")

    document = lire_document(chemin)

    assert document.lu
    assert "Almadies" in document.texte


def test_un_encodage_inattendu_ne_fait_pas_echouer_la_lecture(tmp_path):
    chemin = tmp_path / "ancien.txt"
    chemin.write_bytes("Réunion à Dakar".encode("latin-1"))

    document = lire_document(chemin)

    assert document.lu
    assert "union" in document.texte


def test_les_lignes_vides_en_trop_sont_reduites(tmp_path):
    chemin = tmp_path / "aere.txt"
    chemin.write_text("Titre\n\n\n\n\nContenu", encoding="utf-8")

    assert lire_document(chemin).texte == "Titre\n\nContenu"


# --- Refus ---------------------------------------------------------------------

@pytest.mark.parametrize("nom", ["photo.jpg", "archive.zip", "video.mp4", "tableur.xlsx"])
def test_un_format_non_pris_en_charge_est_refuse_explicitement(tmp_path, nom):
    chemin = tmp_path / nom
    chemin.write_bytes(b"contenu quelconque")

    document = lire_document(chemin)

    assert document.statut == "NON_PRIS_EN_CHARGE"
    assert "formats lus" in document.raison


def test_un_fichier_absent_est_signale(tmp_path):
    document = lire_document(tmp_path / "jamais_vu.pdf")

    assert document.statut == "ECHEC"
    assert "introuvable" in document.raison


def test_un_fichier_trop_volumineux_est_refuse(tmp_path):
    chemin = tmp_path / "enorme.txt"
    chemin.write_bytes(b"x" * 5000)

    document = lire_document(chemin, taille_max=1000)

    assert document.statut == "ECHEC"
    assert "volumineux" in document.raison


def test_un_fichier_vide_est_signale(tmp_path):
    chemin = tmp_path / "vide.txt"
    chemin.write_text("", encoding="utf-8")

    assert lire_document(chemin).statut == "VIDE"


# --- Résumé --------------------------------------------------------------------

def test_le_resume_ne_contient_pas_le_texte(devis_pdf):
    """Il part dans les journaux : y mettre le contenu d'une facture serait une fuite."""
    resume = lire_document(devis_pdf).resume()

    assert resume["statut"] == "LU"
    assert resume["passages"] == 2
    assert resume["caracteres"] > 0
    assert "450000" not in str(resume)


def test_la_provenance_sans_page_reste_le_nom_du_fichier():
    assert Passage(texte="x", fichier="note.txt").source == "note.txt"
