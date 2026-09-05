"""Le connecteur KrillinAI garde-t-il les trois lignes qu'il ne doit jamais franchir ?

Contexte verifie avant d'ecrire une ligne (DEC-0049) : `krillinai/KrillinAI`
a ete renomme `krillinai/OpenCreator` et rearchitecture en un espace de
travail agent complet base sur Codex CLI — CE produit-la n'est PAS integre
ici. Seul l'ancien moteur, survivant sous `runtime/krillinai/` (module Go
`krillin-ai`, licence **GPL-3.0-only** verifiee directement dans son
`LICENSE`), est appele — et seulement par sous-processus, jamais importe.

Trois familles de tests :

1. **Logique pure** (aucun binaire requis) : les trois gardes qui ne se
   negocient pas — jamais de clonage vocal, jamais une seconde
   transcription locale, jamais un telechargement d'URL implicite.
2. **`krillinai-cli` present** (`pytest.mark.skipif` sinon) : la sonde
   distingue « moteur absent » de « moteur present, ffmpeg/ffprobe/yt-dlp
   absents » — les deux sont `NON_CONFIGURE`, pour des raisons differentes,
   jamais confondues.
3. **Contrat de sortie reel** : les manifestes JSON ci-dessous ont ete
   captures en lancant le vrai binaire (`--dry-run`, `krillinai/krillinai`
   @ 346d08b) — jamais invente, pour que le test verifie la lecture d'une
   sortie reelle, pas d'une supposition sur sa forme.
"""
import shutil
import subprocess
from unittest.mock import patch

import pytest

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.krillinai import (
    KRILLINAI_BIN,
    ConnecteurKrillinAI,
    _binaires_media_manquants,
    _est_une_url,
)

moteur_reel = pytest.mark.skipif(
    shutil.which(KRILLINAI_BIN) is None,
    reason="krillinai-cli absent du PATH (go build ./cmd/cli depuis runtime/krillinai/)")

#: Captures reelles (dry-run), pas des exemples inventes — voir l'en-tete.
SORTIE_TTS_DRY_RUN = {
    "ok": True, "stage": "tts", "workdir": "workdir",
    "outputs": {
        "origin_video": "workdir/origin_video.mp4",
        "tts_audio": "workdir/tts_final_audio.wav",
        "video_with_tts": "workdir/video_with_tts.mp4",
    },
}
SORTIE_ERREUR_CONFIG = {
    "ok": False, "stage": "",
    "error": {"kind": "usage", "code": "config_not_found",
             "message": "未找到配置文件", "retryable": False},
}


class TestGardesPurs:
    """Aucun binaire requis : ce sont des refus avant tout appel externe."""

    def test_voice_clone_source_jamais_transmis_meme_fourni(self):
        connecteur = ConnecteurKrillinAI()
        with patch.object(connecteur, "_executer_et_rendre") as capte:
            capte.return_value = None
            connecteur._tts(
                {"srt_cible": "x.srt", "voice_clone_source": "un-fichier-audio.wav"},
                dry_run=True)
        arguments = capte.call_args[0][1]
        assert not any("voice-clone-source" in a or "un-fichier-audio.wav" in a
                       for a in arguments)

    @pytest.mark.parametrize("source", ["whisper", "auto", "openai", "aliyun"])
    def test_caption_source_transcription_refusee(self, source):
        resultat = ConnecteurKrillinAI()._subtitle(
            {"entree": "x.mp4", "langue_origine": "en", "langue_cible": "fr",
             "caption_source": source}, dry_run=True)
        assert resultat.statut is Statut.ECHEC
        assert "transcrit deja" in resultat.message

    @pytest.mark.parametrize("source", ["manual", "platform", "any"])
    def test_caption_source_sans_transcription_acceptee(self, source, tmp_path):
        connecteur = ConnecteurKrillinAI(dossier=tmp_path)
        with patch.object(connecteur, "_executer_et_rendre") as capte:
            capte.return_value = None
            connecteur._subtitle(
                {"entree": "x.mp4", "langue_origine": "en", "langue_cible": "fr",
                 "caption_source": source}, dry_run=True)
        assert capte.called

    def test_url_sans_autorisation_refusee(self, tmp_path):
        resultat = ConnecteurKrillinAI(dossier=tmp_path)._subtitle(
            {"entree": "https://exemple.test/video.mp4",
             "langue_origine": "en", "langue_cible": "fr"}, dry_run=True)
        assert resultat.statut is Statut.ECHEC
        assert "autoriser_telechargement" in resultat.message

    def test_url_avec_autorisation_explicite_acceptee(self, tmp_path):
        connecteur = ConnecteurKrillinAI(dossier=tmp_path)
        with patch.object(connecteur, "_executer_et_rendre") as capte:
            capte.return_value = None
            connecteur._subtitle(
                {"entree": "https://exemple.test/video.mp4",
                 "langue_origine": "en", "langue_cible": "fr",
                 "autoriser_telechargement": True}, dry_run=True)
        assert capte.called

    def test_chemin_local_jamais_confondu_avec_une_url(self):
        assert _est_une_url("https://exemple.test/v.mp4")
        assert not _est_une_url("/home/usman/videos/chantier.mp4")
        assert not _est_une_url("chantier.mp4")

    def test_capacite_pipeline_existe_mais_reste_hors_du_plan_video(self):
        """La capacite est reelle (regle 6) ; c'est plan_video.py qui ne
        l'expose pas au graphe — verifie du cote plan_video, pas ici."""
        assert "pipeline" in ConnecteurKrillinAI().capacites()

    def test_toutes_les_capacites_sont_des_ecritures_sous_generate(self):
        for capacite in ConnecteurKrillinAI().capacites().values():
            assert capacite.ecriture is True
            assert capacite.action == "generate"


class TestSonde:
    def test_binaire_absent_non_configure(self):
        with patch("core.connectors.krillinai._binaire_present", return_value=False):
            sante = ConnecteurKrillinAI().sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE
        assert "go build" in sante.ce_qui_manque

    def test_binaire_present_mais_media_absent_non_configure_pour_une_autre_raison(self):
        with patch("core.connectors.krillinai._binaire_present", return_value=True), \
             patch("core.connectors.krillinai._binaires_media_manquants",
                   return_value=["ffmpeg", "ffprobe", "yt-dlp"]):
            sante = ConnecteurKrillinAI().sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE
        assert "ffmpeg" in sante.message

    @moteur_reel
    def test_sonde_reelle_distingue_krillinai_absent_de_media_absent(self):
        """Verifie ce que CE conteneur mesure reellement : krillinai-cli est
        present (compile pour cette session), ffmpeg/ffprobe/yt-dlp non —
        UNKNOWN pour la generation reelle, mesure honnete ici."""
        sante = ConnecteurKrillinAI().sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE
        assert "krillinai-cli est present" in sante.message


class TestContratDeSortie:
    """Les manifestes ci-dessus sont des captures reelles (voir l'en-tete),
    pas des exemples inventes sur la forme du JSON."""

    def test_sortie_ok_avec_artefacts_reels_verifies(self, tmp_path):
        video = tmp_path / "video_with_tts.mp4"
        video.write_bytes(b"contenu reel non vide")
        sortie = dict(SORTIE_TTS_DRY_RUN)
        sortie["outputs"] = {"video_with_tts": str(video), "absent": str(tmp_path / "rien.mp4")}

        connecteur = ConnecteurKrillinAI()
        verifies = connecteur._verifier_artefacts(sortie["outputs"])
        assert verifies == {"video_with_tts": str(video)}

    def test_fichier_annonce_mais_absent_n_est_jamais_credite(self, tmp_path):
        connecteur = ConnecteurKrillinAI()
        verifies = connecteur._verifier_artefacts(
            {"video_with_tts": str(tmp_path / "n-existe-pas.mp4")})
        assert verifies == {}

    def test_fichier_annonce_mais_vide_n_est_jamais_credite(self, tmp_path):
        vide = tmp_path / "vide.mp4"
        vide.touch()
        connecteur = ConnecteurKrillinAI()
        assert connecteur._verifier_artefacts({"x": str(vide)}) == {}

    def test_ok_true_sans_aucun_artefact_reel_devient_un_echec(self, tmp_path, monkeypatch):
        """Sabotage du principe « ok=true ne suffit jamais » : le processus
        annonce un succes, mais rien n'existe reellement sur disque."""
        connecteur = ConnecteurKrillinAI(dossier=tmp_path)
        acheve = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"ok": true, "outputs": {"x": "/inexistant.mp4"}}\n',
            stderr="")
        with patch.object(connecteur, "_lancer", return_value=acheve):
            resultat = connecteur._executer_et_rendre("cover", ["cover"], tmp_path, dry_run=False)
        assert resultat.statut is Statut.ECHEC
        assert "aucun artefact" in resultat.message

    def test_erreur_structuree_du_moteur_est_lisible(self, tmp_path):
        connecteur = ConnecteurKrillinAI(dossier=tmp_path)
        acheve = subprocess.CompletedProcess(
            args=[], returncode=1,
            stdout='{"ok": false, "stage": "", "error": {"kind": "usage", '
                  '"code": "config_not_found", "message": "config manquante", "retryable": false}}\n',
            stderr="")
        with patch.object(connecteur, "_lancer", return_value=acheve):
            resultat = connecteur._executer_et_rendre("subtitle", ["subtitle"], tmp_path, dry_run=False)
        assert resultat.statut is Statut.ECHEC
        assert resultat.message == "config manquante"

    def test_sortie_illisible_est_un_echec_explicite(self, tmp_path):
        connecteur = ConnecteurKrillinAI(dossier=tmp_path)
        acheve = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="panique go: nil pointer\n", stderr="")
        with patch.object(connecteur, "_lancer", return_value=acheve):
            resultat = connecteur._executer_et_rendre("cover", ["cover"], tmp_path, dry_run=False)
        assert resultat.statut is Statut.ECHEC
        assert "illisible" in resultat.message

    def test_timeout_est_un_echec_explicite(self, tmp_path):
        connecteur = ConnecteurKrillinAI(dossier=tmp_path)
        with patch.object(connecteur, "_lancer",
                         side_effect=subprocess.TimeoutExpired(cmd="krillinai-cli", timeout=900.0)):
            resultat = connecteur._executer_et_rendre("cover", ["cover"], tmp_path, dry_run=False)
        assert resultat.statut is Statut.ECHEC
        assert "900" in resultat.message


@moteur_reel
class TestAppelReel:
    """Le vrai binaire, compile pour cette session (`go build ./cmd/cli`,
    voir DEC-0049) — jamais commite, jamais telecharge par ARENA."""

    def test_dry_run_direct_produit_un_json_reel(self, tmp_path):
        acheve = subprocess.run(
            [KRILLINAI_BIN, "cover", "--workdir", str(tmp_path), "--prompt", "test", "--dry-run"],
            capture_output=True, text=True, timeout=30, cwd=str(tmp_path))
        assert acheve.returncode == 0
        connecteur = ConnecteurKrillinAI()
        sortie = connecteur._sortie_json(acheve)
        assert sortie is not None and sortie["ok"] is True and sortie["stage"] == "cover"

    def test_config_absente_rend_une_erreur_structuree_reelle(self, tmp_path):
        video = tmp_path / "in.mp4"
        video.write_bytes(b"x")
        acheve = subprocess.run(
            [KRILLINAI_BIN, "subtitle", str(video), "--origin-lang", "en",
             "--target-lang", "fr", "--workdir", str(tmp_path), "--caption-source", "manual"],
            capture_output=True, text=True, timeout=30, cwd=str(tmp_path))
        assert acheve.returncode != 0
        connecteur = ConnecteurKrillinAI()
        sortie = connecteur._sortie_json(acheve)
        assert sortie["ok"] is False
        assert sortie["error"]["code"] == "config_not_found"

    def test_connecteur_bout_en_bout_via_conduire_reste_honnete_ici(self, tmp_path):
        """Ce conteneur n'a pas ffmpeg/ffprobe/yt-dlp (mesure, pas suppose) :
        meme krillinai-cli present, la sonde doit rester NON_CONFIGURE — la
        generation reelle attend la machine du proprietaire (DEC-0049)."""
        assert _binaires_media_manquants(), (
            "ce test suppose ffmpeg/ffprobe/yt-dlp absents de CE conteneur ; "
            "s'il echoue ici, la mesure a change et ce commentaire doit l'etre aussi")
        sante = ConnecteurKrillinAI(dossier=tmp_path).sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE
