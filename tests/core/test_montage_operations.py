"""Les opérations de montage : ce que le modèle a le droit de demander.

La règle que ces tests tiennent : **une opération rend un état lisible, elle
ne lève pas.** L'appelant est un modèle — il doit pouvoir lire un refus et
corriger, pas planter au milieu d'une réponse.

Les tests qui ont besoin du vrai `ffprobe` portent la marque `integration`,
comme le reste du dépôt : ils mesurent un vrai fichier plutôt que de simuler
une durée.
"""
import shutil
import subprocess

import pytest

from core.montage.operations import Montage, Resultat, genre_du_fichier, sonder_le_media


@pytest.fixture
def ffmpeg_reel() -> str:
    chemin = shutil.which("ffmpeg")
    if not chemin:
        pytest.skip("ffmpeg n'est pas installé sur cette machine.")
    return chemin


@pytest.fixture
def video_reelle(ffmpeg_reel, tmp_path):
    """6 secondes de mire, en 1280x720 — une vraie vidéo, pas un fichier vide."""
    sortie = tmp_path / "source.mp4"
    subprocess.run(
        [ffmpeg_reel, "-v", "error", "-y", "-f", "lavfi",
         "-i", "testsrc=size=1280x720:rate=30:duration=6",
         "-pix_fmt", "yuv420p", str(sortie)],
        check=True, capture_output=True)
    return sortie


class FausseSonde:
    """Un `FFmpegTool` de test : il annonce ce qu'on lui dit, sans binaire."""

    def __init__(self, disponible: bool = True):
        self._disponible = disponible

    def is_available(self) -> bool:
        return self._disponible

    def get_executable(self) -> str:
        return "/faux/ffmpeg"


class TestSansProjet:
    """Chaque opération doit dire qu'il n'y a pas de projet, pas planter."""

    @pytest.mark.parametrize("appel", [
        lambda m: m.importer_media("/x/a.mp4"),
        lambda m: m.ajouter_piste("video"),
        lambda m: m.ajouter_clip("p", "m"),
        lambda m: m.ajouter_texte("p", "bonjour", 0, 1000),
        lambda m: m.couper_clip("p", "e", 500),
        lambda m: m.retirer_element("p", "e"),
        lambda m: m.definir_format(1080, 1920),
        lambda m: m.resumer(),
    ])
    def test_aucune_operation_ne_leve_sans_projet(self, appel):
        resultat = appel(Montage(ffmpeg=FausseSonde(False)))

        assert isinstance(resultat, Resultat)
        assert resultat.ok is False
        assert "projet" in resultat.message.lower()


class TestProjet:
    def test_creer_un_projet_annonce_son_format(self):
        m = Montage(ffmpeg=FausseSonde(False))

        r = m.creer_projet("reel chantier", 1080, 1920)

        assert r.ok and r.detail["format"] == "1080x1920"

    def test_un_format_impossible_est_refuse_sans_lever(self):
        m = Montage(ffmpeg=FausseSonde(False))

        assert m.creer_projet("x", largeur=0).ok is False

    def test_changer_le_format_pour_un_reel(self):
        m = Montage(ffmpeg=FausseSonde(False))
        m.creer_projet("x")

        assert m.definir_format(1080, 1920).detail["format"] == "1080x1920"
        assert m.definir_format(-1, 100).ok is False


class TestImport:
    def test_un_fichier_absent_est_refuse_et_nomme(self):
        m = Montage(ffmpeg=FausseSonde(False))
        m.creer_projet("x")

        r = m.importer_media("/nulle/part/video.mp4")

        assert r.ok is False and "introuvable" in r.message

    def test_un_format_inconnu_est_refuse(self, tmp_path):
        fichier = tmp_path / "notice.pdf"
        fichier.write_bytes(b"%PDF-1.4")
        m = Montage(ffmpeg=FausseSonde(False))
        m.creer_projet("x")

        r = m.importer_media(str(fichier))

        assert r.ok is False and "non pris en charge" in r.message

    def test_sans_ffmpeg_une_video_n_est_pas_importee_avec_une_duree_inventee(self, tmp_path):
        """Le cas qui compte : plutôt refuser que poser une durée supposée."""
        faux = tmp_path / "clip.mp4"
        faux.write_bytes(b"pas vraiment une video")
        m = Montage(ffmpeg=FausseSonde(False))
        m.creer_projet("x")

        r = m.importer_media(str(faux))

        assert r.ok is False
        assert r.detail["duree_ms"] is None, "une durée a été inventée"
        assert m.projet.medias == {}, "un média non mesuré est entré dans le projet"

    @pytest.mark.parametrize("nom, attendu", [
        ("a.mp4", "video"), ("b.MOV", "video"), ("c.png", "image"),
        ("d.jpg", "image"), ("e.mp3", "audio"), ("f.wav", "audio"),
        ("g.txt", None), ("sans_extension", None),
    ])
    def test_le_genre_vient_de_l_extension(self, nom, attendu):
        assert genre_du_fichier(nom) == attendu

    @pytest.mark.integration
    def test_la_duree_importee_est_celle_du_vrai_fichier(self, video_reelle):
        """Mesurée par ffprobe, jamais estimée."""
        m = Montage()
        m.creer_projet("x")

        r = m.importer_media(str(video_reelle))

        assert r.ok, r.message
        assert r.detail["duree_ms"] == pytest.approx(6000, abs=100)
        assert (r.detail["largeur"], r.detail["hauteur"]) == (1280, 720)

    @pytest.mark.integration
    def test_un_fichier_abime_ne_rend_aucune_mesure(self, tmp_path, ffmpeg_reel):
        abime = tmp_path / "abime.mp4"
        abime.write_bytes(b"\x00\x01\x02 ceci n'est pas un conteneur")

        mesure = sonder_le_media(str(abime))

        assert mesure == {"duree_ms": None, "largeur": None, "hauteur": None}


@pytest.mark.integration
class TestTimeline:
    @pytest.fixture
    def montage(self, video_reelle):
        m = Montage()
        m.creer_projet("chantier", 1080, 1920)
        self.media = m.importer_media(str(video_reelle)).detail["media_id"]
        self.piste = m.ajouter_piste("video", "principale").detail["piste_id"]
        return m

    def test_un_clip_sans_duree_prend_toute_la_source_mesuree(self, montage):
        r = montage.ajouter_clip(self.piste, self.media)

        assert r.ok and r.detail["duree_ms"] == pytest.approx(6000, abs=100)

    def test_un_clip_qui_depasse_la_source_est_refuse(self, montage):
        r = montage.ajouter_clip(self.piste, self.media, duree_ms=99_000)

        assert r.ok is False and "depasse la source" in r.message

    def test_couper_un_clip_donne_deux_morceaux_qui_se_touchent(self, montage):
        clip = montage.ajouter_clip(self.piste, self.media, duree_ms=6_000)

        r = montage.couper_clip(self.piste, clip.detail["element_id"], 2_000)

        assert r.ok
        piste = montage.projet.piste(self.piste)
        assert [(e.debut_ms, e.duree_ms) for e in piste.elements] == [(0, 2_000), (2_000, 4_000)]

    def test_la_coupe_conserve_le_point_d_entree_dans_la_source(self, montage):
        """Le second morceau doit montrer la SUITE, pas revenir au début."""
        clip = montage.ajouter_clip(self.piste, self.media, duree_ms=6_000)

        montage.couper_clip(self.piste, clip.detail["element_id"], 2_500)

        apres = montage.projet.piste(self.piste).elements[1]
        assert apres.coupe_debut_ms == 2_500, "le second morceau rejoue le début"

    def test_couper_hors_du_clip_ne_coupe_rien(self, montage):
        clip = montage.ajouter_clip(self.piste, self.media, duree_ms=3_000)

        r = montage.couper_clip(self.piste, clip.detail["element_id"], 9_999)

        assert r.ok is False and "hors du clip" in r.message
        assert len(montage.projet.piste(self.piste).elements) == 1

    def test_retirer_un_element_absent_le_dit(self, montage):
        assert montage.retirer_element(self.piste, "jamais-pose").ok is False

    def test_le_resume_rend_l_etat_relisible(self, montage):
        montage.ajouter_clip(self.piste, self.media, duree_ms=4_000)
        titres = montage.ajouter_piste("texte", "titres").detail["piste_id"]
        montage.ajouter_texte(titres, "UniC Plaquiste", 0, 2_000)

        r = montage.resumer()

        assert r.detail["duree_ms"] == 4_000
        assert r.detail["format"] == "1080x1920"
        assert {p["type"] for p in r.detail["pistes"]} == {"video", "texte"}
