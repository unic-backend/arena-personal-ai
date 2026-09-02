"""L'incrustation de sous-titres : un nom de fichier ordinaire ne doit pas la casser.

Mesuré le 01/09/2026 : « chantier d'Ouakam.ass » faisait échouer TOUTE
l'incrustation. Même vidéo, mêmes sous-titres — seul le nom change, et le
rendu passe de `True` à `False`. Un nom avec apostrophe est on ne peut plus
ordinaire en français.

Les trois échappements possibles ont été essayés contre le vrai ffmpeg
(`\\'`, `\\\\'`, sans guillemets) : **les trois perdent l'apostrophe**, le
parseur de filtergraph la mange. D'où le contournement — une copie au nom
sûr — qui marche pour n'importe quel caractère, y compris celui qu'on
n'aura pas prévu.
"""
import subprocess
import sys

import pytest

from tools.video.ffmpeg_tool import CARACTERES_PIEGES, FFmpegTool, _chemin_sans_piege

#: `:` piège le parseur de filtergraph ffmpeg (Linux/macOS) mais Windows
#: refuse d'écrire un nom qui le contient — il le lit comme une lettre de
#: lecteur. Ce n'est pas un défaut d'ARENA : un tel fichier ne peut pas
#: exister sur cet OS, donc rien à recopier. Mesuré le 01/09/2026.
_DEUX_POINTS_IMPOSSIBLE_SOUS_WINDOWS = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="':' est un caractere de nom de fichier interdit sous Windows",
)

ASS = """[Script Info]
ScriptType: v4.00+
[V4+ Styles]
Format: Name, Fontname, Fontsize
Style: Default,Arial,20
[Events]
Format: Layer, Start, End, Style, Text
Dialogue: 0,0:00:00.00,0:00:02.00,Default,bonjour
"""


class TestLeContournementDuNom:
    """Sans ffmpeg : la logique du chemin sûr se teste seule."""

    def test_un_nom_sage_n_est_pas_copie(self, tmp_path):
        fichier = tmp_path / "sous_titres.ass"
        fichier.write_text(ASS, encoding="utf-8")
        with _chemin_sans_piege(fichier) as chemin:
            assert chemin == fichier, "un nom sûr ne doit rien coûter"

    @pytest.mark.parametrize("nom", [
        "chantier d'Ouakam.ass", "reunion d'equipe.ass",
        pytest.param("a:b.ass", marks=_DEUX_POINTS_IMPOSSIBLE_SOUS_WINDOWS),
        "a,b.ass", "a[b].ass", "a;b.ass",
    ])
    def test_un_nom_piege_est_recopie_ailleurs(self, tmp_path, nom):
        fichier = tmp_path / nom
        fichier.write_text(ASS, encoding="utf-8")
        with _chemin_sans_piege(fichier) as chemin:
            assert chemin != fichier
            assert not (CARACTERES_PIEGES & set(chemin.name))
            assert chemin.read_text(encoding="utf-8") == ASS, "la copie a perdu le contenu"

    def test_la_copie_disparait_apres_usage(self, tmp_path):
        fichier = tmp_path / "chantier d'Ouakam.ass"
        fichier.write_text(ASS, encoding="utf-8")
        with _chemin_sans_piege(fichier) as chemin:
            temporaire = chemin
        assert not temporaire.exists(), "une copie temporaire est restée sur le disque"

    def test_la_copie_disparait_meme_apres_une_erreur(self, tmp_path):
        fichier = tmp_path / "chantier d'Ouakam.ass"
        fichier.write_text(ASS, encoding="utf-8")
        temporaire = None
        with pytest.raises(RuntimeError):
            with _chemin_sans_piege(fichier) as chemin:
                temporaire = chemin
                raise RuntimeError("ffmpeg a echoue")
        assert temporaire is not None and not temporaire.exists()


@pytest.mark.integration
class TestIncrustationReelle:
    """Avec un vrai ffmpeg : le nom ne doit plus rien changer au résultat."""

    @pytest.fixture
    def video(self, ffmpeg_disponible, tmp_path):
        chemin = tmp_path / "source.mp4"
        subprocess.run(
            [ffmpeg_disponible.get_executable(), "-v", "error", "-y", "-f", "lavfi",
             "-i", "testsrc=size=320x240:rate=10:duration=2",
             "-pix_fmt", "yuv420p", str(chemin)],
            check=True, capture_output=True)
        return chemin

    @pytest.mark.parametrize("nom", [
        "chantier d'Ouakam", "reunion d'equipe", "sans_apostrophe",
    ])
    def test_le_nom_ne_change_pas_le_resultat(self, video, tmp_path, nom):
        sous_titres = tmp_path / f"{nom}.ass"
        sous_titres.write_text(ASS, encoding="utf-8")
        sortie = tmp_path / f"{nom}.out.mp4"

        assert FFmpegTool().burn_subtitles(str(video), str(sous_titres), str(sortie)), (
            f"l'incrustation a échoué pour le seul nom « {nom} »"
        )
        assert sortie.exists() and sortie.stat().st_size > 1_000

    def test_un_fichier_de_sous_titres_absent_reste_un_refus(self, video, tmp_path):
        assert not FFmpegTool().burn_subtitles(
            str(video), str(tmp_path / "fantome.ass"), str(tmp_path / "o.mp4"))
