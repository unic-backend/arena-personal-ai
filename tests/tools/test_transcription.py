"""Transcription locale Whisper : exige ffmpeg et le modèle faster-whisper."""
import subprocess

import pytest

from tools.audio.transcription_tool import TranscriptionTool


@pytest.fixture
def echantillon_audio(ffmpeg_disponible, tmp_path):
    chemin = tmp_path / "echantillon.wav"
    subprocess.run(
        [
            ffmpeg_disponible.get_executable(), "-y",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=2",
            "-ar", "16000", "-ac", "1", str(chemin),
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    )
    return chemin


@pytest.mark.integration
def test_la_duree_detectee_correspond_a_l_audio(echantillon_audio):
    res = TranscriptionTool(model_size="tiny").transcribe(str(echantillon_audio))

    assert res["duration"] == pytest.approx(2.0, abs=0.5)
    assert res["language"] is not None
