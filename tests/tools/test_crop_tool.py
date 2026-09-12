"""`convert_to_vertical_9_16` ne rend `True` que si le fichier ecrit existe
vraiment, n'est pas vide, et `ffprobe` y lit un flux video.

Avant ce correctif (audit externe, commit f7f0478) : la fonction rendait
`True` sur le seul code de retour 0 d'ffmpeg, et `/api/process-video`
(apps/backend/routers/media.py) ignorait meme CE retour — un rendu qui
plantait en cours d'ecriture (disque plein, processus tue) laissait un
fichier tronque, et la reponse annoncait quand meme `"status": "success"`
avec une URL qui pointait dessus.

Ces tests utilisent un vrai ffmpeg (deja requis par Step 1 de cette meme
mission) — jamais un raccourci qui contournerait le vrai comportement du
binaire.
"""
import subprocess

from tools.video.crop_tool import CropTool


def _source_reelle(tmp_path):
    chemin = tmp_path / "source.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", "testsrc=size=320x240:rate=10:duration=1",
         "-pix_fmt", "yuv420p", str(chemin)],
        check=True, capture_output=True, timeout=30)
    return chemin


class TestConversionReelle:
    def test_une_video_reelle_produit_un_rendu_valide(self, tmp_path):
        source = _source_reelle(tmp_path)
        sortie = tmp_path / "rendu_9_16.mp4"
        outil = CropTool()

        reussi = outil.convert_to_vertical_9_16(str(source), str(sortie))

        assert reussi is True
        assert sortie.exists() and sortie.stat().st_size > 0

    def test_une_entree_introuvable_echoue_proprement(self, tmp_path):
        outil = CropTool()
        sortie = tmp_path / "rendu_9_16.mp4"

        reussi = outil.convert_to_vertical_9_16(str(tmp_path / "n_existe_pas.mp4"), str(sortie))

        assert reussi is False
        assert not sortie.exists() or sortie.stat().st_size == 0

    def test_ffmpeg_indisponible_echoue_sans_lever(self, tmp_path, monkeypatch):
        source = _source_reelle(tmp_path)
        outil = CropTool()
        monkeypatch.setattr(outil.ffmpeg, "is_available", lambda: False)

        reussi = outil.convert_to_vertical_9_16(str(source), str(tmp_path / "rendu.mp4"))

        assert reussi is False


class TestSabotageDeLaVerification:
    """La preuve par le sabotage : un fichier tronque APRES un ffmpeg qui a
    reussi doit faire echouer `_sortie_est_valide` — sinon la verification
    ajoutee ne verifie rien de reel."""

    def test_un_fichier_tronque_est_refuse_meme_si_ffmpeg_a_reussi(self, tmp_path, monkeypatch):
        source = _source_reelle(tmp_path)
        sortie = tmp_path / "rendu_9_16.mp4"
        outil = CropTool()

        # ffmpeg "reussit" (code 0), mais le fichier qu'il aurait du produire
        # est en realite tronque — panne de disque, processus tue juste
        # apres l'ecriture du header, mux jamais termine.
        appel_reel = subprocess.run

        def _ffmpeg_puis_troncature(cmd, *args, **kwargs):
            resultat = appel_reel(cmd, *args, **kwargs)
            if cmd and cmd[0] == outil.ffmpeg.get_executable():
                sortie.write_bytes(b"\x00\x00\x00")  # 3 octets : jamais un mp4 valide
            return resultat

        monkeypatch.setattr(subprocess, "run", _ffmpeg_puis_troncature)

        reussi = outil.convert_to_vertical_9_16(str(source), str(sortie))

        assert reussi is False, (
            "un fichier tronque a ete accepte comme un rendu reussi : "
            "la verification ne verifie rien de reel")

    def test_sans_ffprobe_la_verification_refuse_au_lieu_de_supposer(
        self, tmp_path, monkeypatch,
    ):
        """Le cas le plus sournois, mesure le 12/09/2026 en diagnostic :
        ffmpeg present et content de lui, ffprobe INTROUVABLE. Un repli
        permissif (« pas de verificateur, donc c'est bon ») recreerait
        exactement le defaut que cette etape a corrige — un montage annonce
        pret dont personne n'a lu le fichier. Le fichier est bien ecrit ici,
        et c'est quand meme un refus."""
        import tools.video.crop_tool as module

        source = _source_reelle(tmp_path)
        sortie = tmp_path / "sans_ffprobe.mp4"
        monkeypatch.setattr(
            module, "_trouver_ffprobe", lambda _exe: "/introuvable/ffprobe-absent")

        reussi = CropTool().convert_to_vertical_9_16(str(source), str(sortie))

        assert sortie.exists() and sortie.stat().st_size > 0, (
            "le rendu ffmpeg lui-meme doit avoir eu lieu, sinon le test ne "
            "prouve rien sur la verification")
        assert reussi is False, (
            "sans verificateur, le rendu a ete annonce reussi : une capacite "
            "absente se rapporte, elle ne se suppose pas")

    def test_un_fichier_vide_est_refuse(self, tmp_path):
        outil = CropTool()
        vide = tmp_path / "vide.mp4"
        vide.write_bytes(b"")

        assert outil._sortie_est_valide(vide) is False

    def test_un_vrai_rendu_reste_accepte(self, tmp_path):
        """Le sabotage ci-dessus ne doit pas rendre la verification trop
        stricte pour un rendu authentique."""
        source = _source_reelle(tmp_path)
        sortie = tmp_path / "rendu_9_16.mp4"
        outil = CropTool()
        assert outil.convert_to_vertical_9_16(str(source), str(sortie)) is True
        assert outil._sortie_est_valide(sortie) is True
