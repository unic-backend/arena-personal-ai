"""Structured FFmpeg operations: closed plans, boundaries, and verified artifacts."""
import json
import shutil
import subprocess

import pytest

from tools.video.ffmpeg_tool import PROFILS_LIVRAISON, FFmpegTool


class Completed:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _probe_json(*, video=True, audio=True, duration="2.000", width=320, height=240,
                fps="25/1") -> bytes:
    streams = []
    if video:
        streams.append({"codec_type": "video", "codec_name": "h264", "width": width,
                        "height": height, "avg_frame_rate": fps})
    if audio:
        streams.append({"codec_type": "audio", "codec_name": "aac", "channels": 2})
    return json.dumps({"format": {"duration": duration}, "streams": streams}).encode()


def test_plan_refuse_traversee_source_et_sortie(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    source = root / "source.mp4"
    source.write_bytes(b"media")
    outil = FFmpegTool("ffmpeg", "ffprobe")

    with pytest.raises(ValueError, match="MEDIA_DIR"):
        outil.planifier("trim", tmp_path / "secret.mp4", root / "out.mp4",
                        media_root=root, options={"duration": 1})
    with pytest.raises(ValueError, match="MEDIA_DIR"):
        outil.planifier("trim", source, tmp_path / "out.mp4",
                        media_root=root, options={"duration": 1})


def test_plan_refuse_ecrasement_et_operation_inconnue(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"media")
    outil = FFmpegTool("ffmpeg", "ffprobe")
    with pytest.raises(ValueError, match="ecrasee"):
        outil.planifier("trim", source, source, media_root=tmp_path,
                        options={"duration": 1})
    with pytest.raises(ValueError, match="inconnue"):
        outil.planifier("shell", source, tmp_path / "out.mp4", media_root=tmp_path)


def test_plan_est_une_liste_arguments_et_valide_les_parametres(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"media")
    outil = FFmpegTool("ffmpeg", "ffprobe")
    plan = outil.planifier("fit", source, tmp_path / "out.mp4", media_root=tmp_path,
                           options={"width": 1080, "height": 1920, "mode": "blur"})
    assert isinstance(plan.command, list)
    assert "-vf" in plan.command and "gblur" in plan.command[plan.command.index("-vf") + 1]
    assert plan.expected == {"width": 1080, "height": 1920, "stream": "video"}

    with pytest.raises(ValueError, match="mode"):
        outil.planifier("fit", source, tmp_path / "bad.mp4", media_root=tmp_path,
                        options={"mode": "movie=/etc/passwd"})


def test_dry_run_ne_lance_ni_ffmpeg_ni_ffprobe(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"media")
    outil = FFmpegTool("ffmpeg", "ffprobe")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("subprocess lance"))

    resultat = outil.executer("mirror", source, tmp_path / "out.mp4",
                              media_root=tmp_path, dry_run=True)
    assert resultat.status == "planned"
    assert resultat.verification == {"executed": False, "input_validated": True}
    assert not (tmp_path / "out.mp4").exists()


def test_ffmpeg_absent_est_not_configured(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"media")
    outil = FFmpegTool("absent", "ffprobe")
    monkeypatch.setattr(outil, "is_available", lambda: False)
    resultat = outil.executer("mirror", source, tmp_path / "out.mp4", media_root=tmp_path)
    assert resultat.status == "not_configured"
    assert resultat.error_code == "NOT_CONFIGURED"


def test_entree_invalide_est_refusee_avant_ffmpeg(tmp_path, monkeypatch):
    source = tmp_path / "bad.mp4"
    source.write_bytes(b"not media")
    outil = FFmpegTool("ffmpeg", "ffprobe")
    monkeypatch.setattr(outil, "is_available", lambda: True)
    monkeypatch.setattr(outil, "probe", lambda _p: {"ok": False, "error": "illisible"})
    resultat = outil.executer("mirror", source, tmp_path / "out.mp4", media_root=tmp_path)
    assert resultat.error_code == "INPUT_INVALID"


@pytest.mark.parametrize("mode", ["failed", "empty", "corrupt", "timeout"])
def test_echec_ne_laisse_ni_sortie_ni_temporaire(tmp_path, monkeypatch, mode):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"media")
    output = tmp_path / "out.mp4"
    outil = FFmpegTool("ffmpeg", "ffprobe")
    monkeypatch.setattr(outil, "is_available", lambda: True)
    calls = {"probe": 0}

    def probe(path):
        calls["probe"] += 1
        if calls["probe"] == 1:
            return {"ok": True, "video_codec": "h264", "audio_codec": "aac"}
        if mode == "corrupt":
            return {"ok": False, "file_size": 9, "video_codec": None, "audio_codec": None,
                    "error": "corrompu", "duration": None, "width": None, "height": None,
                    "fps": None, "audio_channels": None}
        size = 0 if mode == "empty" else 10
        return {"ok": bool(size), "file_size": size, "video_codec": "h264",
                "audio_codec": "aac", "duration": 2.0, "width": 320, "height": 240,
                "fps": 25.0, "audio_channels": 2}

    monkeypatch.setattr(outil, "probe", probe)

    def run(command, **kwargs):
        if mode == "timeout":
            raise subprocess.TimeoutExpired(command, 1)
        if mode in {"empty", "corrupt"}:
            open(command[-1], "wb").write(b"" if mode == "empty" else b"corrupted")
        return Completed(returncode=1 if mode == "failed" else 0, stderr=b"failure")

    monkeypatch.setattr(subprocess, "run", run)
    resultat = outil.executer("mirror", source, output, media_root=tmp_path, timeout=1)
    assert not resultat.ok
    assert not output.exists()
    assert not list(tmp_path.glob(".out-*"))


def test_sortie_verifiee_est_publiee_et_structuree(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"media")
    output = tmp_path / "out.mp4"
    outil = FFmpegTool("ffmpeg", "ffprobe")
    monkeypatch.setattr(outil, "is_available", lambda: True)
    calls = {"probe": 0}

    def probe(_path):
        calls["probe"] += 1
        return {"ok": True, "video_codec": "h264", "audio_codec": "aac",
                "file_size": 1234, "duration": 2.0, "width": 320, "height": 240,
                "fps": 25.0, "audio_channels": 2, "error": ""}

    monkeypatch.setattr(outil, "probe", probe)

    def run(command, **_kwargs):
        open(command[-1], "wb").write(b"valid-media")
        return Completed()

    monkeypatch.setattr(subprocess, "run", run)
    resultat = outil.executer("mirror", source, output, media_root=tmp_path)
    assert resultat.ok and output.read_bytes() == b"valid-media"
    assert resultat.video_codec == "h264" and resultat.file_size == 1234
    assert resultat.verification["checks"]["stream"] is True


def test_sortie_creee_pendant_le_rendu_n_est_jamais_ecrasee(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"media")
    output = tmp_path / "out.mp4"
    outil = FFmpegTool("ffmpeg", "ffprobe")
    monkeypatch.setattr(outil, "is_available", lambda: True)
    monkeypatch.setattr(outil, "probe", lambda _path: {
        "ok": True, "video_codec": "h264", "audio_codec": "aac", "file_size": 10,
        "duration": 2.0, "width": 320, "height": 240, "fps": 25.0,
        "audio_channels": 2, "error": "",
    })

    def run(command, **_kwargs):
        open(command[-1], "wb").write(b"nouveau")
        output.write_bytes(b"concurrent")
        return Completed()

    monkeypatch.setattr(subprocess, "run", run)
    resultat = outil.executer("mirror", source, output, media_root=tmp_path)
    assert resultat.error_code == "OUTPUT_INVALID"
    assert output.read_bytes() == b"concurrent"
    assert not list(tmp_path.glob(".out-*"))


def test_profiles_are_closed_and_platform_dimensions_are_declared():
    assert set(PROFILS_LIVRAISON) == {
        "youtube", "shorts", "reels", "tiktok", "x", "linkedin", "facebook"
    }
    assert PROFILS_LIVRAISON["reels"]["height"] == 1920


@pytest.mark.integration
def test_trim_reel_est_precis_et_verifie(tmp_path):
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg/ffprobe absents")
    source = tmp_path / "source.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc=size=320x240:rate=25:duration=3", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=3", "-shortest", "-pix_fmt", "yuv420p",
                    str(source)], check=True)
    resultat = FFmpegTool(ffmpeg, ffprobe).executer(
        "trim", source, tmp_path / "cut.mp4", media_root=tmp_path,
        options={"start": 0.5, "duration": 1.25})
    assert resultat.ok, resultat.to_dict()
    assert resultat.duration == pytest.approx(1.25, abs=0.15)
    assert resultat.verification["checks"]["duration"] is True
