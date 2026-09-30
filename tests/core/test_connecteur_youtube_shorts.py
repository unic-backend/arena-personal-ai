"""Le connecteur youtube_shorts garde-t-il les lignes qu'il ne doit pas franchir ?

Contexte verifie avant d'ecrire une ligne
(`docs/audits/ai_youtube_shorts_audit_2026-09-30.md`) : le moteur amont
(`Anil-matcha/AI-Youtube-Shorts-Generator` @ `a57bb93`, MIT) a deux modes. Le
mode `api` televerse la video vers MuAPI (tiers payant) ; il n'est pas
atteignable depuis ce connecteur. Le mode `local` a ete **execute reellement**
pendant l'audit (video ffmpeg de 12 s, transcription SRT fournie, endpoint
compatible OpenAI local) : deux MP4 404x720 avec audio, aux bonnes durees.

Trois familles de tests :

1. **Gardes purs** — aucun moteur requis : ce sont des refus qui tombent
   AVANT tout appel externe (transcription obligatoire, pas d'URL implicite,
   bornes, formats, mode `api` inatteignable, aucun secret ARENA transmis).
2. **Contrat de sortie reel** — le `result.json` ci-dessous est une capture
   de l'execution reelle de l'audit, jamais une supposition sur sa forme.
   Un extrait annonce sans fichier sur disque n'est pas un succes.
3. **Moteur reellement installe** (`skipif` sinon) — sonde mesuree et
   generation de bout en bout.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.youtube_shorts import (
    COMMIT_AUDITE,
    ConnecteurYoutubeShorts,
    _est_une_url,
)

MANIFESTE = Path("tools/video/YOUTUBE_SHORTS_MANIFEST.json")

moteur_reel = pytest.mark.skipif(
    not os.getenv("YOUTUBE_SHORTS_PATH", "").strip(),
    reason="YOUTUBE_SHORTS_PATH absent : le moteur n'est pas installe a cote d'ARENA")


@pytest.fixture()
def atelier(tmp_path):
    """Un connecteur dont les sorties restent dans tmp_path."""
    return ConnecteurYoutubeShorts(dossier=tmp_path / "rendered")


@pytest.fixture()
def configure(monkeypatch, tmp_path):
    """Un faux dossier moteur + un LLM declare : de quoi depasser les gardes
    de configuration pour tester les gardes d'entree."""
    moteur = tmp_path / "moteur"
    (moteur / "shorts_generator" / "local").mkdir(parents=True)
    (moteur / "main.py").write_text("", encoding="utf-8")
    (moteur / "shorts_generator" / "pipeline.py").write_text("", encoding="utf-8")
    (moteur / "shorts_generator" / "local" / "clipper.py").write_text("", encoding="utf-8")
    monkeypatch.setenv("YOUTUBE_SHORTS_PATH", str(moteur))
    monkeypatch.setenv("YOUTUBE_SHORTS_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("YOUTUBE_SHORTS_LLM_MODEL", "qwen2.5")
    return moteur


def _generer(atelier, **parametres):
    """Appel direct de la capacite, sans passer par la confirmation.

    `generate_shorts` est classee CONFIRMATION (permissions_services.yaml) :
    `executer()` rend A_CONFIRMER avant toute validation d'entree. Ces tests-ci
    portent sur les gardes d'entree ; la confirmation, elle, a son propre test
    (`test_une_generation_passe_par_la_confirmation`).
    """
    return atelier._executer(atelier.capacites()["generate_shorts"], **parametres)


def _srt(chemin: Path) -> Path:
    chemin.write_text("1\n00:00:00,500 --> 00:00:05,000\nUn.\n", encoding="utf-8")
    return chemin


class TestGardesPurs:
    """Aucun moteur requis : ces refus tombent avant tout sous-processus."""

    def test_sans_moteur_installe_cest_non_configure_pas_une_promesse(self, atelier, monkeypatch):
        monkeypatch.delenv("YOUTUBE_SHORTS_PATH", raising=False)
        sante = atelier.sante()
        assert sante.etat is EtatSante.NON_CONFIGURE
        assert "YOUTUBE_SHORTS_PATH" in sante.ce_qui_manque
        assert not sante.utilisable

    def test_generer_sans_moteur_ne_lance_aucun_sous_processus(self, atelier, monkeypatch):
        monkeypatch.delenv("YOUTUBE_SHORTS_PATH", raising=False)
        with patch("subprocess.run") as lance:
            resultat = _generer(atelier, video="/tmp/x.mp4")
        assert resultat.statut is Statut.NON_CONFIGURE
        lance.assert_not_called()

    def test_sans_transcription_cest_un_echec_jamais_un_second_whisper(
            self, atelier, configure, tmp_path):
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00" * 64)
        with patch("subprocess.run") as lance:
            resultat = _generer(atelier, video=str(video))
        assert resultat.statut is Statut.ECHEC
        assert "transcript_srt" in resultat.message
        lance.assert_not_called()

    def test_url_sans_autorisation_ne_telecharge_rien(self, atelier, configure):
        with patch("subprocess.run") as lance:
            resultat = _generer(atelier, video="https://www.youtube.com/watch?v=abc")
        assert resultat.statut is Statut.ECHEC
        assert "autoriser_telechargement" in resultat.message
        lance.assert_not_called()

    def test_url_meme_autorisee_refuse_une_transcription_locale_non_appariable(
            self, atelier, configure, tmp_path):
        srt = _srt(tmp_path / "t.srt")
        with patch("subprocess.run") as lance:
            resultat = _generer(atelier, video="https://youtu.be/abc",
                                autoriser_telechargement=True, transcript_srt=str(srt))
        assert resultat.statut is Statut.ECHEC
        lance.assert_not_called()

    def test_video_absente_est_dite_absente(self, atelier, configure, tmp_path):
        srt = _srt(tmp_path / "t.srt")
        resultat = _generer(atelier, video=str(tmp_path / "rien.mp4"),
                                    transcript_srt=str(srt))
        assert resultat.statut is Statut.ECHEC
        assert "introuvable" in resultat.message

    @pytest.mark.parametrize("nombre", [0, 11, -3, "trois"])
    def test_nombre_de_clips_borne(self, atelier, configure, tmp_path, nombre):
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00" * 64)
        srt = _srt(tmp_path / "v.srt")
        with patch("subprocess.run") as lance:
            resultat = _generer(atelier, video=str(video),
                                        transcript_srt=str(srt), nombre_clips=nombre)
        assert resultat.statut is Statut.ECHEC
        lance.assert_not_called()

    def test_format_inconnu_refuse(self, atelier, configure, tmp_path):
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00" * 64)
        srt = _srt(tmp_path / "v.srt")
        resultat = _generer(atelier, video=str(video),
                                    transcript_srt=str(srt), format="16:9")
        assert resultat.statut is Statut.ECHEC
        assert "9:16" in resultat.message

    def test_sans_llm_declare_cest_non_configure(self, atelier, configure, tmp_path, monkeypatch):
        monkeypatch.delenv("YOUTUBE_SHORTS_LLM_BASE_URL", raising=False)
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00" * 64)
        srt = _srt(tmp_path / "v.srt")
        resultat = _generer(atelier, video=str(video),
                                    transcript_srt=str(srt))
        assert resultat.statut is Statut.NON_CONFIGURE


class TestFrontiereDuSousProcessus:
    """Ce que le moteur recoit — et surtout ce qu'il ne recoit pas."""

    def test_le_moteur_ne_recoit_aucun_secret_arena(self, atelier, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENAI_API_KEY", "cle-arena-secrete")
        monkeypatch.setenv("GITHUB_TOKEN", "jeton-github-secret")
        monkeypatch.setenv("YOUTUBE_SHORTS_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
        monkeypatch.setenv("YOUTUBE_SHORTS_LLM_MODEL", "qwen2.5")
        environnement = atelier._environnement(tmp_path)
        assert "GITHUB_TOKEN" not in environnement
        assert "MUAPI_API_KEY" not in environnement
        assert "cle-arena-secrete" not in "".join(environnement.values())
        assert environnement["OPENAI_API_KEY"] == "local"
        assert environnement["OPENAI_BASE_URL"] == "http://127.0.0.1:11434/v1"

    def test_le_mode_api_nest_pas_atteignable(self, atelier, configure, tmp_path):
        """Le mode qui televerse la video vers MuAPI ne peut pas etre demande."""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00" * 64)
        srt = _srt(tmp_path / "v.srt")
        with patch("subprocess.run") as lance:
            lance.side_effect = OSError("pas de moteur reel ici")
            _generer(atelier, video=str(video), transcript_srt=str(srt),
                             mode="api", muapi_api_key="devrait-etre-ignore")
        arguments = lance.call_args[0][0]
        assert arguments[arguments.index("--mode") + 1] == "local"
        assert "devrait-etre-ignore" not in " ".join(arguments)

    def test_un_delai_depasse_est_un_echec_annonce(self, atelier, configure, tmp_path):
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00" * 64)
        srt = _srt(tmp_path / "v.srt")
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("main.py", 1800)):
            resultat = _generer(atelier, video=str(video),
                                        transcript_srt=str(srt))
        assert resultat.statut is Statut.ECHEC
        assert "rendu la main" in resultat.message

    def test_deux_executions_ne_se_marchent_pas_dessus(self, atelier, configure, tmp_path):
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00" * 64)
        srt = _srt(tmp_path / "v.srt")
        dossiers = []
        with patch("subprocess.run") as lance:
            lance.side_effect = OSError("stop")
            for _ in range(2):
                _generer(atelier, video=str(video), transcript_srt=str(srt))
                dossiers.append(lance.call_args[1]["env"]["LOCAL_OUTPUT_DIR"])
        assert dossiers[0] != dossiers[1]


#: Capture REELLE de l'execution de l'audit (30/09/2026), transcript retire.
RESULTAT_REEL = {
    "mode": "local",
    "source_video_url": "src.mp4",
    "highlights": [
        {"title": "Clip A", "start_time": 1.0, "end_time": 5.0, "score": 91,
         "hook_sentence": "Watch this", "virality_reason": "hook"},
        {"title": "Clip B", "start_time": 6.0, "end_time": 9.0, "score": 77,
         "hook_sentence": "And then", "virality_reason": "payoff"},
    ],
    "shorts": [
        {"title": "Clip A", "start_time": 1.0, "end_time": 5.0, "score": 91,
         "hook_sentence": "Watch this", "virality_reason": "hook", "clip_url": "short_01.mp4"},
        {"title": "Clip B", "start_time": 6.0, "end_time": 9.0, "score": 77,
         "hook_sentence": "And then", "virality_reason": "payoff", "clip_url": "short_02.mp4"},
    ],
}


class TestLectureDuResultatReel:
    """Un succes exige des fichiers, pas un code retour 0."""

    def _brut(self, travail: Path, *, ecrire: int) -> dict:
        brut = json.loads(json.dumps(RESULTAT_REEL))
        for rang, court in enumerate(brut["shorts"], start=1):
            chemin = travail / f"short_{rang:02d}.mp4"
            court["clip_url"] = str(chemin)
            if rang <= ecrire:
                chemin.write_bytes(b"\x00" * 2048)
        return brut

    def test_les_clips_ecrits_sont_credites_avec_leurs_metadonnees(self, atelier, tmp_path):
        travail = tmp_path / "shorts-abcd1234"
        travail.mkdir(parents=True)
        source = travail / "src.mp4"
        source.write_bytes(b"\x00" * 64)
        resultat = atelier._rendre(self._brut(travail, ecrire=2), travail, "9:16", source)
        assert resultat.statut is Statut.SUCCES
        clips = resultat.detail["clips"]
        assert len(clips) == 2
        assert clips[0]["score"] == 91 and clips[0]["hook"] == "Watch this"
        assert clips[0]["mime_type"] == "video/mp4" and clips[0]["format"] == "9:16"
        assert Path(resultat.preuve).is_file()
        assert not source.exists(), "la copie de la source doit etre liberee"

    def test_une_copie_de_source_non_liberee_est_dite_jamais_tue(self, atelier, tmp_path):
        """Le menage qui echoue ne perd pas les shorts — mais il ne se tait pas."""
        travail = tmp_path / "shorts-abcd1234"
        travail.mkdir(parents=True)
        source = travail / "src.mp4"
        source.write_bytes(b"\x00" * 64)
        brut = self._brut(travail, ecrire=2)
        with patch.object(Path, "unlink", side_effect=OSError("disque en lecture seule")):
            resultat = atelier._rendre(brut, travail, "9:16", source)
        assert resultat.statut is Statut.SUCCES, "deux shorts reels restent un succes"
        assert resultat.detail["source_liberee"] is False
        assert any("source" in e for e in resultat.detail["erreurs"])

    def test_un_extrait_annonce_sans_fichier_nest_pas_credite(self, atelier, tmp_path):
        travail = tmp_path / "shorts-abcd1234"
        travail.mkdir(parents=True)
        source = travail / "src.mp4"
        source.write_bytes(b"\x00" * 64)
        resultat = atelier._rendre(self._brut(travail, ecrire=1), travail, "9:16", source)
        assert resultat.statut is Statut.SUCCES
        assert len(resultat.detail["clips"]) == 1
        assert resultat.detail["erreurs"], "l'extrait manquant doit etre rapporte"

    def test_aucun_fichier_sur_disque_est_un_echec_et_nettoie(self, atelier, tmp_path):
        travail = tmp_path / "shorts-abcd1234"
        travail.mkdir(parents=True)
        source = travail / "src.mp4"
        source.write_bytes(b"\x00" * 64)
        resultat = atelier._rendre(self._brut(travail, ecrire=0), travail, "9:16", source)
        assert resultat.statut is Statut.ECHEC
        assert not travail.exists(), "un echec ne laisse pas de dossier de travail"

    def test_les_fichiers_intermediaires_sont_nettoyes(self, atelier, tmp_path):
        travail = tmp_path / "shorts-abcd1234"
        travail.mkdir(parents=True)
        (travail / "short_01.mp4.cut.mp4").write_bytes(b"x")
        (travail / "short_01.mp4.silent.mp4").write_bytes(b"x")
        garde = travail / "short_01.mp4"
        garde.write_bytes(b"x")
        atelier._nettoyer_intermediaires(travail)
        assert list(travail.glob("*.cut.mp4")) == []
        assert list(travail.glob("*.silent.mp4")) == []
        assert garde.exists()


class TestContratDeclare:
    """Ce que le registre, les permissions et le manifeste annoncent."""

    def test_les_capacites_sont_declarees_et_typees(self, atelier):
        capacites = atelier.capacites()
        assert set(capacites) == {"generate_shorts", "inspecter_moteur"}
        assert capacites["generate_shorts"].ecriture is True
        assert capacites["generate_shorts"].action == "generate"
        assert capacites["inspecter_moteur"].ecriture is False

    def test_une_generation_passe_par_la_confirmation(self, atelier, configure, tmp_path):
        """La politique classe `generate` en CONFIRMATION : rien ne part seul."""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"\x00" * 64)
        srt = _srt(tmp_path / "v.srt")
        with patch("subprocess.run") as lance:
            resultat = atelier.executer("generate_shorts", video=str(video),
                                        transcript_srt=str(srt))
        assert resultat.statut is Statut.A_CONFIRMER
        lance.assert_not_called()

    def test_une_capacite_non_declaree_natteint_jamais_le_moteur(self, atelier, configure):
        with patch("subprocess.run") as lance:
            resultat = atelier.executer("generate_from_muapi", video="/tmp/x.mp4")
        assert resultat.statut is not Statut.SUCCES
        lance.assert_not_called()

    def test_le_manifeste_decrit_la_realite_mesuree(self):
        manifeste = json.loads(MANIFESTE.read_text(encoding="utf-8"))
        assert manifeste["id"] == "youtube_shorts"
        assert manifeste["pinned_commit"] == COMMIT_AUDITE
        assert manifeste["license"] == "MIT"
        assert manifeste["vendored_in_arena"] is False
        assert manifeste["api_mode_enabled"] is False
        assert manifeste["downloads_implicitly"] is False
        assert manifeste["receives_arena_secrets"] is False
        assert manifeste["health_is_measured"] is True
        assert manifeste["replaces_existing_arena_capability"] is False
        assert Path(manifeste["audit"]).is_file()

    def test_le_service_est_declare_dans_les_permissions(self):
        import yaml
        politique = yaml.safe_load(Path("config/permissions_services.yaml").read_text(
            encoding="utf-8"))
        services = politique.get("services", politique)
        entree = services["youtube_shorts"]
        assert entree["generate"]["decision"] == "CONFIRMATION"
        assert entree["read"]["decision"] == "ALLOWED"

    def test_le_moteur_nentre_pas_dans_le_depot(self):
        """DEC-0039 : le moteur vit a cote, jamais dans git."""
        suivis = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                                check=True).stdout.splitlines()
        interdits = [f for f in suivis
                     if "shorts_generator/" in f or f.endswith("AI-Youtube-Shorts-Generator")]
        assert interdits == []

    def test_url_detectee_comme_telle(self):
        assert _est_une_url("https://youtu.be/x")
        assert not _est_une_url("/media/video.mp4")


@moteur_reel
class TestMoteurReellementInstalle:
    """Mesure, pas supposition — n'existe que si le moteur est installe."""

    def test_la_sonde_mesure_opencv_dans_linterpreteur_du_moteur(self, atelier):
        sante = atelier.sante()
        assert sante.etat in (EtatSante.OPERATIONNEL, EtatSante.NON_CONFIGURE)
        assert sante.mesure_le, "une sante non mesuree ne vaut rien"
        if sante.etat is EtatSante.NON_CONFIGURE:
            assert sante.ce_qui_manque

    def test_inspecter_rend_la_revision_reellement_installee(self, atelier):
        resultat = atelier.executer("inspecter_moteur")
        assert resultat.statut in (Statut.SUCCES, Statut.NON_CONFIGURE)
        if resultat.statut is Statut.SUCCES:
            assert resultat.detail["revision_auditee"] == COMMIT_AUDITE

    @pytest.mark.integration
    def test_bout_en_bout_produit_de_vrais_mp4_verticaux(self, atelier, tmp_path):
        if (shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None
                or not atelier.sante().utilisable):
            pytest.skip("moteur ou ffmpeg indisponible")
        video = tmp_path / "src.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", "testsrc=size=1280x720:rate=25:duration=12", "-f", "lavfi",
             "-i", "sine=frequency=440:duration=12", "-c:v", "libx264",
             "-pix_fmt", "yuv420p", "-c:a", "aac", str(video)], check=True)
        srt = tmp_path / "src.srt"
        srt.write_text("1\n00:00:00,500 --> 00:00:05,000\nUn.\n\n"
                       "2\n00:00:05,500 --> 00:00:11,500\nDeux.\n", encoding="utf-8")
        resultat = _generer(atelier, video=str(video),
                                    transcript_srt=str(srt), nombre_clips=2)
        assert resultat.statut is Statut.SUCCES, resultat.message
        for clip in resultat.detail["clips"]:
            chemin = Path(clip["chemin"])
            assert chemin.is_file() and chemin.stat().st_size > 0
            sonde = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                 "stream=width,height", "-of", "csv=p=0", str(chemin)],
                capture_output=True, text=True, check=True)
            largeur, hauteur = (int(x) for x in sonde.stdout.strip().split(","))
            assert hauteur > largeur, "un short doit etre vertical"
