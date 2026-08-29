"""Le depot de pieces jointes : lu, puis efface.

Le test qui compte le plus est `test_le_fichier_est_efface_apres_lecture` :
ses devis, ses plans et ses courriers de clients ne doivent pas s'accumuler
dans un dossier que personne ne surveille.
"""

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


# --- La regle de vie privee ---------------------------------------------------

def test_le_fichier_est_efface_apres_lecture(depot, tmp_path, monkeypatch):
    """Seul le texte reste. Le fichier disparait, lu ou non."""
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
    assert crees, "aucun dossier temporaire cree"
    assert not Path(crees[0]).exists(), "le dossier temporaire n'a pas ete efface"


def test_le_texte_survit_au_fichier(depot):
    piece = depot.deposer("devis.txt", TEXTE)

    assert "486 m2" in depot.lire(piece.identifiant).texte


# --- Les formats --------------------------------------------------------------

def test_un_fichier_texte_est_lu(depot):
    piece = depot.deposer("devis.txt", TEXTE)

    assert piece.statut == "LU"
    assert piece.lisible is True


@pytest.mark.parametrize("nom", ["photo.exe", "video.mp4", "archive.zip", "sans_extension"])
def test_un_format_non_lu_est_refuse_en_le_disant(depot, nom):
    piece = depot.deposer(nom, b"contenu")

    assert piece.statut == "NON_PRIS_EN_CHARGE"
    assert piece.lisible is False
    assert ".pdf" in piece.raison and ".docx" in piece.raison


def test_un_format_refuse_ne_touche_jamais_le_disque(depot, monkeypatch):
    """Le lecteur refuserait de toute facon — mais apres avoir ecrit le fichier.

    Ecrire des octets inconnus dans un dossier temporaire pour les relire et les
    effacer aussitot est un risque gratuit. Mesure le 2026-08-27 : en retirant
    le controle d'extension, aucun test n'echouait. Celui-ci le tient.
    """
    import tempfile as tempfile_module

    appels = []
    vrai_mkdtemp = tempfile_module.mkdtemp

    def _tracer(*args, **kwargs):
        appels.append(1)
        return vrai_mkdtemp(*args, **kwargs)

    monkeypatch.setattr("apps.backend.pieces_jointes.tempfile.mkdtemp", _tracer)

    depot.deposer("virus.exe", b"MZ\x90\x00")

    assert appels == [], "un format refuse a ete ecrit sur le disque"


def test_un_format_accepte_passe_bien_par_le_disque(depot, monkeypatch):
    """Le contre-exemple : sans lui, le test ci-dessus passerait meme si plus
    aucun fichier n'etait jamais ecrit."""
    import tempfile as tempfile_module

    appels = []
    vrai_mkdtemp = tempfile_module.mkdtemp

    def _tracer(*args, **kwargs):
        appels.append(1)
        return vrai_mkdtemp(*args, **kwargs)

    monkeypatch.setattr("apps.backend.pieces_jointes.tempfile.mkdtemp", _tracer)

    depot.deposer("devis.txt", TEXTE)

    assert appels == [1]


def test_un_refus_rend_quand_meme_une_piece_avec_un_identifiant(depot):
    """L'interface doit pouvoir afficher pourquoi le fichier n'a pas ete pris."""
    piece = depot.deposer("photo.exe", b"MZ")

    assert piece.identifiant
    assert depot.lire(piece.identifiant) is not None


def test_un_fichier_trop_gros_est_refuse_avec_les_deux_tailles():
    petit = DepotPiecesJointes(taille_max=100)

    piece = petit.deposer("devis.txt", b"x" * 500)

    assert piece.statut == "ECHEC"
    assert "trop volumineux" in piece.raison


def test_deposer_ne_leve_jamais(depot):
    """Un fichier casse rend une piece portant son statut, pas une exception."""
    for nom, contenu in [("a.pdf", b"pas un vrai pdf"), ("b.docx", b""), ("c.txt", b"\xff\xfe")]:
        assert depot.deposer(nom, contenu) is not None


# --- Le nom vient du navigateur -----------------------------------------------

@pytest.mark.parametrize("nom,attendu", [
    ("../../.env", ".env"),
    ("C:\\\\Users\\\\Saer\\\\secret.txt", "secret.txt"),
    ("dossier/devis.txt", "devis.txt"),
])
def test_le_chemin_du_nom_est_retire(depot, nom, attendu):
    """Sans cela, « ../../.env » serait un nom de fichier valide."""
    assert depot.deposer(nom, TEXTE).nom == attendu


def test_un_nom_vide_recoit_un_nom(depot):
    assert depot.deposer("", TEXTE).nom == "sans-nom"


# --- La troncature se dit -----------------------------------------------------

def test_un_document_enorme_est_tronque_et_le_dit():
    """Le tronquer en silence ferait croire qu'il a ete lu en entier."""
    petit = DepotPiecesJointes(caracteres_max=100)

    piece = petit.deposer("long.txt", ("mot " * 500).encode())

    assert piece.tronque is True
    assert piece.texte.endswith(MENTION_TRONQUE)


def test_un_document_normal_n_est_pas_marque_tronque(depot):
    assert depot.deposer("devis.txt", TEXTE).tronque is False


def test_le_plafond_par_defaut_est_borne():
    assert 0 < CARACTERES_MAX <= 200_000


# --- La peremption ------------------------------------------------------------

def test_une_piece_perimee_n_est_plus_servie():
    """Une piece jointe d'hier n'a rien a faire dans la question d'aujourd'hui."""
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


# --- Ce que l'interface recoit ------------------------------------------------

def test_le_texte_n_est_pas_dans_la_forme_transportable(depot):
    """Il ne ferait que des allers-retours inutiles, et il contient ses documents."""
    piece = depot.deposer("devis.txt", b"NINEA 013141677 confidentiel")

    assert "013141677" not in str(piece.to_dict())


def test_la_forme_transportable_dit_l_etat_reel(depot):
    corps = depot.deposer("photo.exe", b"MZ").to_dict()

    assert corps["status"] == "NON_PRIS_EN_CHARGE"
    assert corps["readable"] is False
    assert corps["reason"]


# --- Les images (DEC-0019) -----------------------------------------------------

OCTETS_IMAGE = b"\x89PNG\r\n\x1a\n" + b"faux-png-mais-suffit-pour-le-test"


@pytest.mark.parametrize("nom", ["photo.jpg", "photo.jpeg", "plan.png", "chantier.webp", "schema.gif"])
def test_une_image_est_lue_sans_toucher_au_texte(depot, nom):
    piece = depot.deposer(nom, OCTETS_IMAGE)

    assert piece.statut == "LU"
    assert piece.lisible is True
    assert piece.est_image is True
    assert piece.texte == ""


def test_une_image_est_encodee_en_base64(depot):
    piece = depot.deposer("plan.png", OCTETS_IMAGE)

    assert base64.b64decode(piece.image_base64) == OCTETS_IMAGE


def test_une_image_ne_touche_jamais_le_disque(depot, monkeypatch):
    """Meme regle de vie privee que pour un document — mais une image n'a meme
    pas besoin d'un aller-retour par le disque : rien ne l'ecrit."""
    import tempfile as tempfile_module

    appels = []
    monkeypatch.setattr(
        "apps.backend.pieces_jointes.tempfile.mkdtemp",
        lambda *a, **k: appels.append(1) or tempfile_module.mkdtemp(*a, **k),
    )

    depot.deposer("plan.png", OCTETS_IMAGE)

    assert appels == []


def test_une_image_trop_grosse_est_refusee():
    petit = DepotPiecesJointes(taille_max=10)

    piece = petit.deposer("plan.png", OCTETS_IMAGE)

    assert piece.statut == "ECHEC"
    assert "trop volumineux" in piece.raison
    assert piece.est_image is False


def test_l_image_n_est_pas_dans_la_forme_transportable(depot):
    """Meme regle que le texte : elle ne fait que des allers-retours inutiles."""
    piece = depot.deposer("plan.png", OCTETS_IMAGE)

    assert "image_base64" not in piece.to_dict()
    assert piece.image_base64 not in str(piece.to_dict())


def test_la_forme_transportable_distingue_image_et_document(depot):
    image = depot.deposer("plan.png", OCTETS_IMAGE).to_dict()
    document = depot.deposer("devis.txt", TEXTE).to_dict()

    assert image["nature"] == "image"
    assert document["nature"] == "document"


def test_les_formats_image_apparaissent_dans_le_refus(depot):
    """Un format vraiment inconnu doit citer les images comme lisibles aussi."""
    piece = depot.deposer("video.mp4", b"contenu")

    assert ".png" in piece.raison
