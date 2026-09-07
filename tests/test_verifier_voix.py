"""`scripts/verifier_voix.py` : la mesure qui attrape un fichier muet.

Un WAV de la bonne taille, de la bonne durée et parfaitement silencieux passe
tous les contrôles habituels — et n'est pas une voix. C'est exactement le
piège que la règle 2 du connecteur cherche à éviter (`ffprobe` mesure une
durée, pas du son), et la seule mesure qui l'attrape est l'amplitude.

Ces tests tiennent cette mesure. Ils n'ont besoin ni de VoiceStudio, ni de
ffmpeg : le module `wave` de la bibliothèque standard suffit, et c'est
volontaire — le CI n'a ni l'un ni l'autre, sa machine n'a pas toujours ffmpeg.
"""
import math
import struct
import wave
from pathlib import Path

from scripts.verifier_voix import _verdict, mesurer_le_wav


def _wav(chemin: Path, *, amplitude: int, secondes: float = 0.5,
         cadence: int = 16000) -> Path:
    with wave.open(str(chemin), "wb") as flux:
        flux.setnchannels(1)
        flux.setsampwidth(2)
        flux.setframerate(cadence)
        images = int(cadence * secondes)
        flux.writeframes(b"".join(
            struct.pack("<h", int(amplitude * math.sin(2 * math.pi * 440 * i / cadence)))
            for i in range(images)))
    return chemin


class TestUnFichierMuetEstUnEchec:
    def test_le_silence_parfait_est_refuse_malgre_une_duree_correcte(self, tmp_path):
        """Le piège exact : durée juste, taille juste, aucun son."""
        mesure = mesurer_le_wav(_wav(tmp_path / "muet.wav", amplitude=0))

        assert mesure["secondes"] == 0.5, "la durée est bien là"
        assert mesure["octets"] > 0, "le fichier pèse bien quelque chose"
        assert mesure["amplitude_max"] == 0
        assert _verdict(mesure) == "ECHEC (fichier parfaitement silencieux)"

    def test_un_vrai_son_passe(self, tmp_path):
        mesure = mesurer_le_wav(_wav(tmp_path / "son.wav", amplitude=12000))

        assert mesure["amplitude_max"] > 0
        assert mesure["cadence"] == 16000
        assert mesure["canaux"] == 1
        assert _verdict(mesure) == "OK"


class TestCeQuiNEstPasDuSon:
    def test_un_fichier_absent_ne_rend_aucun_zero(self, tmp_path):
        """Une mesure impossible vaut `None`, jamais `0` — qui se lirait « muet »."""
        mesure = mesurer_le_wav(tmp_path / "fantome.wav")

        assert mesure["octets"] is None
        assert mesure["secondes"] is None
        assert mesure["amplitude_max"] is None
        assert mesure["lisible"] is False

    def test_une_erreur_json_deguisee_en_wav_est_illisible(self, tmp_path):
        faux = tmp_path / "faux.wav"
        faux.write_bytes(b'{"error": "modele absent"}')

        mesure = mesurer_le_wav(faux)

        assert mesure["lisible"] is False
        assert mesure["octets"] > 0, "le fichier existe bel et bien"
        assert _verdict(mesure) == "ECHEC (fichier illisible)"
