"""Transcription locale Whisper : exige ffmpeg et le modèle faster-whisper."""
import subprocess

import pytest

from tools.audio.transcription_tool import ModeleAbsent, TranscriptionTool


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


class TestCapaciteAbsente:
    """Ce qui manque se rapporte, et ce qui n'est pas mesure ne vaut pas zero.

    Trouve en revue le 31/08/2026 : l'import de `faster_whisper` remontait une
    `ImportError` brute au milieu d'une reponse d'agent, et une duree jamais
    obtenue etait rendue `0.0` — un chiffre plausible a la place d'une mesure,
    exactement ce que CLAUDE.md interdit.
    """

    def test_sans_faster_whisper_l_absence_est_nommee(self, monkeypatch):
        import builtins

        vrai_import = builtins.__import__

        def refuser(nom, *args, **kw):
            if nom == "faster_whisper":
                raise ImportError("aucun module faster_whisper")
            return vrai_import(nom, *args, **kw)

        monkeypatch.setattr(builtins, "__import__", refuser)

        with pytest.raises(ModeleAbsent) as erreur:
            TranscriptionTool()._load_model()

        assert "faster-whisper" in str(erreur.value)
        assert "pip install" in str(erreur.value), "l'absence ne dit pas comment la reparer"

    def test_une_duree_non_mesuree_vaut_none_jamais_zero(self, tmp_path):
        """`0.0` se lirait « video de zero seconde », une mesure qui n'a pas eu lieu."""
        audio = tmp_path / "muet.wav"
        audio.write_bytes(b"RIFF....WAVE")

        outil = TranscriptionTool()
        outil.model = type("FauxModele", (), {
            "transcribe": lambda self, *a, **kw: ([], None)})()

        resultat = outil.transcribe(str(audio))

        assert resultat["duration"] is None, "une duree inconnue a ete rendue comme un chiffre"
        assert resultat["full_text"] == ""
