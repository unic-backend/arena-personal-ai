"""`media_metadata` : ce qui est reellement dans le fichier, jamais invente.

Tous les fichiers de test sont produits ICI, reellement — jamais un octet
commis dans le depot. Les fixtures EXIF sont ecrites ET relues par Pillow
(pas piexif : verifie que Pillow seul suffit, `Image.Exif`/`get_ifd`),
exactement comme le fera la machine du proprietaire.

Le test qui compte le plus est `TestGPSConfidentialite` : une coordonnee
GPS EXIF est une donnee sensible, et ce module ne doit jamais avoir la
moindre capacite de l'envoyer ailleurs qu'a l'appelant.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

from core.actions.resultat import Statut
from core.connectors.media_metadata import ConnecteurMediaMetadata

_SANS_FFMPEG = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe absents : la mesure video/audio ne peut pas etre faite ici")


def _jpeg_avec_exif_gps(dossier: Path) -> Path:
    from PIL import Image
    from PIL.ExifTags import GPS as Gps
    from PIL.ExifTags import Base as Tag
    from PIL.TiffImagePlugin import IFDRational

    chemin = dossier / "avec_exif_gps.jpg"
    img = Image.new("RGB", (800, 600), color=(120, 140, 160))
    exif = img.getexif()
    exif[Tag.Make.value] = "ARENA-Test-Cam"
    exif[Tag.Model.value] = "TestModel-42"
    exif[Tag.Software.value] = "PillowTestSuite"
    exif[Tag.DateTimeOriginal.value] = "2026:09:10 12:00:00"
    exif[Tag.Orientation.value] = 6
    exif[Tag.Copyright.value] = "Test Copyright ARENA"
    sous_ifd = exif.get_ifd(Tag.ExifOffset.value)
    sous_ifd[Tag.ISOSpeedRatings.value] = 400
    sous_ifd[Tag.FNumber.value] = IFDRational(28, 10)
    sous_ifd[Tag.ExposureTime.value] = IFDRational(1, 250)
    sous_ifd[Tag.FocalLength.value] = IFDRational(50, 1)
    sous_ifd[Tag.LensModel.value] = "ARENA 50mm f/2.8"
    # 14°41'00"N, 17°26'00"W — coordonnees CONTROLEES, jamais reelles.
    exif[Tag.GPSInfo.value] = {
        Gps.GPSLatitudeRef.value: "N",
        Gps.GPSLatitude.value: (IFDRational(14, 1), IFDRational(41, 1), IFDRational(0, 1)),
        Gps.GPSLongitudeRef.value: "W",
        Gps.GPSLongitude.value: (IFDRational(17, 1), IFDRational(26, 1), IFDRational(0, 1)),
    }
    img.save(chemin, format="JPEG", exif=exif)
    return chemin


def _jpeg_sans_exif(dossier: Path) -> Path:
    from PIL import Image
    chemin = dossier / "sans_exif.jpg"
    Image.new("RGB", (400, 300), color=(10, 20, 30)).save(chemin, format="JPEG")
    return chemin


@pytest.fixture
def connecteur() -> ConnecteurMediaMetadata:
    return ConnecteurMediaMetadata()


class TestCapacitesDeclarees:
    def test_seule_analyser_existe_et_n_ecrit_rien(self):
        capacites = ConnecteurMediaMetadata().capacites()
        assert set(capacites) == {"analyser"}
        assert capacites["analyser"].ecriture is False


class TestSante:
    def test_operationnel_quand_pillow_est_la(self, connecteur):
        sante = connecteur.sante()
        assert sante.utilisable


class TestExifComplet:
    """Chaque champ demande par la mission, verifie individuellement contre
    un fichier reel ecrit par Pillow — jamais une valeur supposee."""

    @pytest.fixture
    def resultat(self, tmp_path, connecteur):
        chemin = _jpeg_avec_exif_gps(tmp_path)
        return connecteur.executer("analyser", chemin=str(chemin))

    def test_succes(self, resultat):
        assert resultat.statut is Statut.SUCCES

    def test_dimensions_et_format(self, resultat):
        assert resultat.detail["format_reel"] == "JPEG"
        assert resultat.detail["largeur"] == 800
        assert resultat.detail["hauteur"] == 600

    def test_appareil(self, resultat):
        assert resultat.detail["fabricant"] == "ARENA-Test-Cam"
        assert resultat.detail["modele_appareil"] == "TestModel-42"

    def test_objectif_et_prise_de_vue(self, resultat):
        assert resultat.detail["objectif"] == "ARENA 50mm f/2.8"
        assert resultat.detail["iso"] == 400
        assert resultat.detail["ouverture"] == "f/2.8"
        assert resultat.detail["vitesse_obturation"] == "1/250s"
        assert resultat.detail["focale_mm"] == 50.0

    def test_orientation_et_dates(self, resultat):
        assert resultat.detail["orientation"] == 6
        assert resultat.detail["date_prise"] == "2026:09:10 12:00:00"

    def test_logiciel_et_copyright(self, resultat):
        assert resultat.detail["logiciel"] == "PillowTestSuite"
        assert resultat.detail["copyright"] == "Test Copyright ARENA"

    def test_gps_converti_en_degres_decimaux(self, resultat):
        """14°41'00"N, 17°26'00"W -> (14.683333, -17.433333)."""
        assert resultat.detail["gps_present"] is True
        assert resultat.detail["gps_latitude"] == pytest.approx(14.683333, abs=1e-5)
        assert resultat.detail["gps_longitude"] == pytest.approx(-17.433333, abs=1e-5)


class TestSansExif:
    def test_aucun_champ_exif_n_est_invente(self, tmp_path, connecteur):
        chemin = _jpeg_sans_exif(tmp_path)
        r = connecteur.executer("analyser", chemin=str(chemin))

        assert r.statut is Statut.SUCCES
        assert r.detail["format_reel"] == "JPEG"
        assert r.detail["largeur"] == 400
        assert r.detail["hauteur"] == 300
        for champ in ("fabricant", "modele_appareil", "objectif", "iso", "ouverture",
                     "vitesse_obturation", "focale_mm", "orientation", "date_prise",
                     "logiciel", "copyright", "gps_latitude", "gps_longitude"):
            assert r.detail[champ] is None, f"{champ} n'a pas ete mesure, il ne doit pas etre rempli"
        assert r.detail["gps_present"] is False


class TestAutresFormatsImage:
    def test_png(self, tmp_path, connecteur):
        from PIL import Image
        chemin = tmp_path / "image.png"
        Image.new("RGB", (200, 150), color=(50, 60, 70)).save(chemin, format="PNG")

        r = connecteur.executer("analyser", chemin=str(chemin))

        assert r.statut is Statut.SUCCES
        assert r.detail["format_reel"] == "PNG"
        assert (r.detail["largeur"], r.detail["hauteur"]) == (200, 150)

    def test_webp(self, tmp_path, connecteur):
        from PIL import Image
        chemin = tmp_path / "image.webp"
        Image.new("RGB", (150, 150), color=(80, 90, 100)).save(chemin, format="WEBP")

        r = connecteur.executer("analyser", chemin=str(chemin))

        assert r.statut is Statut.SUCCES
        assert r.detail["format_reel"] == "WEBP"


class TestFichiersProblematiques:
    """Mission §6/§9 : corrompu, mauvaise extension, absent, tres volumineux."""

    def test_fichier_corrompu_est_un_echec_jamais_un_crash(self, tmp_path, connecteur):
        chemin = tmp_path / "corrompu.jpg"
        chemin.write_bytes(b"ceci n'est pas une image, juste du texte")

        r = connecteur.executer("analyser", chemin=str(chemin))

        assert r.statut is Statut.ECHEC
        assert "corrompu.jpg" in r.message

    def test_extension_incorrecte_est_signalee_pas_masquee(self, tmp_path, connecteur):
        """Un PNG enregistre sous `.jpg` : le format REEL est dit, pas devine
        depuis le nom du fichier — regle 3 du module."""
        from PIL import Image
        chemin = tmp_path / "faux.jpg"
        Image.new("RGB", (100, 100), color=(200, 10, 10)).save(chemin, format="PNG")

        r = connecteur.executer("analyser", chemin=str(chemin))

        assert r.statut is Statut.SUCCES, "le contenu reste lisible, meme mal nomme"
        assert r.detail["format_reel"] == "PNG"
        assert r.detail["alerte_extension"] is not None
        assert "PNG" in r.detail["alerte_extension"]

    def test_fichier_absent_est_un_echec_nomme(self, tmp_path, connecteur):
        r = connecteur.executer("analyser", chemin=str(tmp_path / "fantome.jpg"))

        assert r.statut is Statut.ECHEC
        assert "introuvable" in r.message.lower() or "fantome" in r.message

    def test_extension_non_reconnue_est_un_echec_explicite(self, tmp_path, connecteur):
        chemin = tmp_path / "fichier.xyz"
        chemin.write_bytes(b"donnees quelconques")

        r = connecteur.executer("analyser", chemin=str(chemin))

        assert r.statut is Statut.ECHEC
        assert "xyz" in r.message

    def test_exif_malformee_ne_fait_pas_planter_la_lecture(self, tmp_path, connecteur):
        """L'image reste lisible meme si son segment EXIF est corrompu :
        Pillow degrade proprement, ce module ne doit ni planter ni inventer."""
        from PIL import Image
        chemin = tmp_path / "exif_malforme.jpg"
        img = Image.new("RGB", (400, 300))
        exif = img.getexif()
        exif[271] = "ARENA"  # Make
        img.save(chemin, format="JPEG", exif=exif)

        donnees = bytearray(chemin.read_bytes())
        idx = donnees.find(b"\xff\xe1")
        assert idx != -1, "le marqueur EXIF (APP1) doit exister pour ce test"
        for i in range(idx + 14, min(idx + 24, len(donnees))):
            donnees[i] = 0xFF
        chemin.write_bytes(bytes(donnees))

        r = connecteur.executer("analyser", chemin=str(chemin))

        assert r.statut is Statut.SUCCES, "l'image elle-meme reste lisible"
        assert r.detail["format_reel"] == "JPEG"

    def test_fichier_volumineux_ne_bloque_pas(self, tmp_path, connecteur):
        """Pas un test de charge extreme — juste la preuve qu'une image
        au-dela des tailles ordinaires est lue sans immobiliser la reponse."""
        import time

        from PIL import Image
        chemin = tmp_path / "volumineux.jpg"
        Image.new("RGB", (6000, 4000), color=(33, 66, 99)).save(
            chemin, format="JPEG", quality=85)

        depart = time.monotonic()
        r = connecteur.executer("analyser", chemin=str(chemin))
        duree = time.monotonic() - depart

        assert r.statut is Statut.SUCCES
        assert (r.detail["largeur"], r.detail["hauteur"]) == (6000, 4000)
        assert duree < 10.0, "la lecture d'un seul fichier ne doit pas trainer"


@_SANS_FFMPEG
class TestVideoReelle:
    @pytest.fixture
    def video(self, tmp_path):
        chemin = tmp_path / "video.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=25",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-c:a", "aac", "-metadata", "title=Video de test ARENA",
            str(chemin),
        ], capture_output=True, timeout=60, check=True)
        return chemin

    def test_metadonnees_video_reelles(self, video, connecteur):
        r = connecteur.executer("analyser", chemin=str(video))

        assert r.statut is Statut.SUCCES
        assert r.detail["genre"] == "video"
        assert r.detail["codec_video"] == "h264"
        assert (r.detail["largeur"], r.detail["hauteur"]) == (320, 240)
        assert r.detail["fps"] == pytest.approx(25.0, abs=0.1)
        assert r.detail["duree_ms"] == pytest.approx(2000, abs=200)
        assert r.detail["bitrate_kbps"] is not None and r.detail["bitrate_kbps"] > 0
        assert len(r.detail["pistes_audio"]) == 1
        assert r.detail["pistes_audio"][0]["codec"] == "aac"
        assert r.detail["tags"].get("title") == "Video de test ARENA"


@_SANS_FFMPEG
class TestAudioReel:
    @pytest.fixture
    def audio(self, tmp_path):
        chemin = tmp_path / "audio.mp3"
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-c:a", "libmp3lame", "-b:a", "128k",
            "-metadata", "artist=ARENA Test", "-metadata", "title=Audio de test",
            str(chemin),
        ], capture_output=True, timeout=60, check=True)
        return chemin

    def test_metadonnees_audio_reelles(self, audio, connecteur):
        r = connecteur.executer("analyser", chemin=str(audio))

        assert r.statut is Statut.SUCCES
        assert r.detail["genre"] == "audio"
        assert r.detail["codec"] == "mp3"
        assert r.detail["duree_ms"] == pytest.approx(3000, abs=300)
        assert r.detail["echantillonnage_hz"] == 44100
        assert r.detail["bitrate_kbps"] is not None and r.detail["bitrate_kbps"] > 0
        assert r.detail["tags"].get("artist") == "ARENA Test"
        assert r.detail["tags"].get("title") == "Audio de test"


class TestGPSConfidentialite:
    """Mission §5 — la garantie qui compte le plus dans ce fichier."""

    def test_aucune_bibliotheque_reseau_n_est_importee_par_le_module(self):
        """Une coordonnee GPS lue ici ne PEUT PAS partir vers un service
        externe : ce module n'importe ni httpx, ni requests, ni urllib —
        verifie sur son propre source, pas sur un comportement observe."""
        import core.connectors.media_metadata as module
        source = Path(module.__file__).read_text(encoding="utf-8")
        for interdit in ("httpx", "requests", "urllib.request", "socket"):
            assert interdit not in source, (
                f"« {interdit} » apparait dans media_metadata.py : "
                "une capacite reseau n'a rien a y faire")

    def test_le_gps_n_est_present_que_si_reellement_lu(self, tmp_path, connecteur):
        chemin = _jpeg_sans_exif(tmp_path)
        r = connecteur.executer("analyser", chemin=str(chemin))

        assert r.detail["gps_present"] is False
        assert r.detail["gps_latitude"] is None
        assert r.detail["gps_longitude"] is None

    def test_coordonnees_gps_incompletes_ne_sont_pas_devinees(self, tmp_path, connecteur):
        """Latitude presente, reference ('N'/'S') absente : `_dms_vers_decimal`
        doit refuser de deviner un hemisphere."""
        from PIL.TiffImagePlugin import IFDRational

        from core.connectors.media_metadata import _dms_vers_decimal

        assert _dms_vers_decimal(
            (IFDRational(14, 1), IFDRational(41, 1), IFDRational(0, 1)), None) is None
        assert _dms_vers_decimal(None, "N") is None


class TestImageEnMemoire:
    """Le chemin qu'utilise `VisionAgent` : une piece jointe n'existe qu'en
    base64 (`apps/backend/pieces_jointes.py`), jamais ecrite sur disque."""

    def test_exif_lu_depuis_le_base64_sans_ecrire_de_fichier(self, tmp_path, connecteur):
        import base64
        chemin = _jpeg_avec_exif_gps(tmp_path)
        b64 = base64.b64encode(chemin.read_bytes()).decode("ascii")

        r = connecteur.executer(
            "analyser", image_base64=b64, nom_fichier="photo-jointe.jpg")

        assert r.statut is Statut.SUCCES
        assert r.detail["fichier"] is None, "rien n'a ete ecrit sur le disque"
        assert r.detail["modele_appareil"] == "TestModel-42"
        assert r.detail["gps_present"] is True
        assert r.detail["gps_latitude"] == pytest.approx(14.683333, abs=1e-5)

    def test_base64_invalide_est_un_echec_jamais_un_crash(self, connecteur):
        r = connecteur.executer("analyser", image_base64="!!! pas du base64 !!!")
        assert r.statut is Statut.ECHEC

    def test_ni_chemin_ni_base64_est_un_echec(self, connecteur):
        r = connecteur.executer("analyser")
        assert r.statut is Statut.ECHEC
