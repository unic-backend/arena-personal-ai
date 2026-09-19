"""Tests du depot de pieces jointes, avec garde stricte des images."""

import base64

import pytest

from apps.backend.pieces_jointes import (
    CARACTERES_MAX,
    MENTION_TRONQUE,
    DepotPiecesJointes,
    PieceJointe,
)


@pytest.fixture
def depot():
    return DepotPiecesJointes()


TEXTE = b"Cloison BA13, 18 parois de 5,40 x 2,50 m, 486 m2 developpes."
PNG = b"\x89PNG\r\n\x1a\n" + b"contenu-test"
JPEG = b"\xff\xd8\xff\xe0" + b"contenu-test"
GIF = b"GIF89a" + b"contenu-test"
WEBP = b"RIFF" + (12).to_bytes(4, "little") + b"WEBP" + b"contenu-test"


def test_le_fichier_est_efface_apres_lecture(depot, monkeypatch):
    crees = []
    import tempfile as tempfile_module
    vrai_mkdtemp = tempfile_module.mkdtemp

    def _tracer(*args, **kwargs):
        dossier = vrai_mkdtemp(*args, **kwargs)
        crees.append(dossier)
        return dossier

    monkeypatch.setattr("apps.backend.pieces_jointes.tempfile.mkdtemp", _tracer)
    depot.deposer("devis.txt", TEXTE)

    from pathlib import Path
    assert crees
    assert not Path(crees[0]).exists()


def test_le_texte_survit_au_fichier(depot):
    piece = depot.deposer("devis.txt", TEXTE)
    assert "486 m2" in depot.lire(piece.identifiant).texte


def test_un_fichier_texte_est_lu(depot):
    piece = depot.deposer("devis.txt", TEXTE)
    assert piece.statut == "LU"
    assert piece.lisible is True


def _pdf_valide() -> bytes:
    from io import BytesIO
    from reportlab.pdfgen import canvas
    tampon = BytesIO()
    c = canvas.Canvas(tampon)
    c.drawString(100, 700, "plan")
    c.save()
    return tampon.getvalue()


def test_un_pdf_garde_ses_octets_pour_une_mesure_eventuelle(depot):
    contenu = _pdf_valide()
    piece = depot.deposer("plan.pdf", contenu)
    assert piece.pdf_base64
    assert base64.b64decode(piece.pdf_base64) == contenu


def test_un_document_non_pdf_ne_garde_aucun_octet(depot):
    assert depot.deposer("devis.txt", TEXTE).pdf_base64 == ""


def test_le_pdf_n_est_pas_dans_la_forme_transportable(depot):
    assert "pdf_base64" not in depot.deposer("plan.pdf", _pdf_valide()).to_dict()


@pytest.mark.parametrize("nom", ["photo.exe", "video.mp4", "archive.zip", "sans_extension"])
def test_un_format_non_lu_est_refuse_en_le_disant(depot, nom):
    piece = depot.deposer(nom, b"contenu")
    assert piece.statut == "NON_PRIS_EN_CHARGE"
    assert piece.lisible is False
    assert ".pdf" in piece.raison and ".docx" in piece.raison


def test_un_format_refuse_ne_touche_jamais_le_disque(depot, monkeypatch):
    appels = []
    monkeypatch.setattr("apps.backend.pieces_jointes.tempfile.mkdtemp", lambda *a, **k: appels.append(1))
    depot.deposer("virus.exe", b"MZ\x90\x00")
    assert appels == []


def test_un_refus_rend_quand_meme_une_piece_avec_un_identifiant(depot):
    piece = depot.deposer("photo.exe", b"MZ")
    assert piece.identifiant
    assert depot.lire(piece.identifiant) is not None


def test_un_fichier_trop_gros_est_refuse_avec_les_deux_tailles():
    piece = DepotPiecesJointes(taille_max=100).deposer("devis.txt", b"x" * 500)
    assert piece.statut == "ECHEC"
    assert "trop volumineux" in piece.raison


def test_deposer_ne_leve_jamais(depot):
    for nom, contenu in [("a.pdf", b"pas un vrai pdf"), ("b.docx", b""), ("c.txt", b"\xff\xfe")]:
        assert depot.deposer(nom, contenu) is not None


@pytest.mark.parametrize("nom,attendu", [
    ("../../.env", ".env"),
    ("C:\\Users\\Saer\\secret.txt", "secret.txt"),
    ("dossier/devis.txt", "devis.txt"),
])
def test_le_chemin_du_nom_est_retire(depot, nom, attendu):
    assert depot.deposer(nom, TEXTE).nom == attendu


def test_un_nom_vide_recoit_un_nom(depot):
    assert depot.deposer("", TEXTE).nom == "sans-nom"


def test_un_document_enorme_est_tronque_et_le_dit():
    piece = DepotPiecesJointes(caracteres_max=100).deposer("long.txt", ("mot " * 500).encode())
    assert piece.tronque is True
    assert piece.texte.endswith(MENTION_TRONQUE)


def test_un_document_normal_n_est_pas_marque_tronque(depot):
    assert depot.deposer("devis.txt", TEXTE).tronque is False


def test_le_plafond_par_defaut_est_borne():
    assert 0 < CARACTERES_MAX <= 200_000


def test_une_piece_perimee_n_est_plus_servie():
    expire = DepotPiecesJointes(duree_vie_minutes=0)
    piece = expire.deposer("devis.txt", TEXTE)
    assert expire.lire(piece.identifiant) is None


def test_une_piece_dans_le_delai_est_servie(depot):
    piece = depot.deposer("devis.txt", TEXTE)
    assert depot.lire(piece.identifiant) is not None


def test_purger_retire_les_perimees():
    expire = DepotPiecesJointes(duree_vie_minutes=0)
    expire.deposer("a.txt", TEXTE)
    expire.deposer("b.txt", TEXTE)
    assert expire.purger() == 2
    assert expire.nombre() == 0


def test_une_date_illisible_est_traitee_comme_perimee():
    piece = PieceJointe("id", "a.txt", 10, "LU", texte="x", expire_le="pas une date")
    assert piece.est_perimee() is True


def test_un_identifiant_inconnu_rend_none(depot):
    assert depot.lire("jamais-depose") is None


def test_le_texte_n_est_pas_dans_la_forme_transportable(depot):
    piece = depot.deposer("devis.txt", b"NINEA 013141677 confidentiel")
    assert "013141677" not in str(piece.to_dict())


def test_la_forme_transportable_dit_l_etat_reel(depot):
    corps = depot.deposer("photo.exe", b"MZ").to_dict()
    assert corps["status"] == "NON_PRIS_EN_CHARGE"
    assert corps["readable"] is False
    assert corps["reason"]


# --- Images : la signature reelle compte, pas seulement le nom ---------------

@pytest.mark.parametrize("nom,contenu", [
    ("plan.png", PNG),
    ("photo.jpg", JPEG),
    ("photo.jpeg", JPEG),
    ("schema.gif", GIF),
    ("chantier.webp", WEBP),
])
def test_une_vraie_image_est_lue(depot, nom, contenu):
    piece = depot.deposer(nom, contenu)
    assert piece.statut == "LU"
    assert piece.lisible is True
    assert piece.est_image is True
    assert piece.texte == ""
    assert base64.b64decode(piece.image_base64) == contenu


@pytest.mark.parametrize("nom", ["photo.jpg", "photo.jpeg", "plan.png", "chantier.webp", "schema.gif"])
def test_une_extension_image_avec_des_octets_arbitraires_est_refusee(depot, nom):
    piece = depot.deposer(nom, b"MZ ceci n'est pas une image")
    assert piece.statut == "ECHEC"
    assert piece.lisible is False
    assert piece.est_image is False
    assert "signature" in piece.raison


def test_une_image_renommee_avec_une_mauvaise_extension_est_refusee(depot):
    piece = depot.deposer("faux.jpg", PNG)
    assert piece.statut == "ECHEC"
    assert piece.est_image is False
    assert "incoherente" in piece.raison


def test_jpeg_et_jpeg_long_sont_equivalents(depot):
    assert depot.deposer("a.jpg", JPEG).lisible is True
    assert depot.deposer("b.jpeg", JPEG).lisible is True


def test_une_image_ne_touche_jamais_le_disque(depot, monkeypatch):
    appels = []
    monkeypatch.setattr("apps.backend.pieces_jointes.tempfile.mkdtemp", lambda *a, **k: appels.append(1))
    depot.deposer("plan.png", PNG)
    assert appels == []


def test_une_image_invalide_ne_touche_jamais_le_disque(depot, monkeypatch):
    appels = []
    monkeypatch.setattr("apps.backend.pieces_jointes.tempfile.mkdtemp", lambda *a, **k: appels.append(1))
    depot.deposer("plan.png", b"not-an-image")
    assert appels == []


def test_une_image_trop_grosse_est_refusee():
    piece = DepotPiecesJointes(taille_max=4).deposer("plan.png", PNG)
    assert piece.statut == "ECHEC"
    assert "trop volumineux" in piece.raison
    assert piece.est_image is False


def test_l_image_n_est_pas_dans_la_forme_transportable(depot):
    piece = depot.deposer("plan.png", PNG)
    assert "image_base64" not in piece.to_dict()
    assert piece.image_base64 not in str(piece.to_dict())


def test_la_forme_transportable_distingue_image_et_document(depot):
    image = depot.deposer("plan.png", PNG).to_dict()
    document = depot.deposer("devis.txt", TEXTE).to_dict()
    assert image["nature"] == "image"
    assert document["nature"] == "document"


def test_les_formats_image_apparaissent_dans_le_refus(depot):
    piece = depot.deposer("video.mp4", b"contenu")
    assert ".png" in piece.raison
