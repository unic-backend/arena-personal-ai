"""Les deux outils qui font le résultat visible, et qui n'avaient aucun test.

`SubtitleTool` et `CropTool` sont ce que le propriétaire regarde : les mots en
bas de l'écran et le format vertical. Le 02/09/2026, ils étaient les **deux
seuls** outils vidéo sans une seule mesure — et c'est là que le défaut se
cachait.

**Le défaut, mesuré :** « on pose le BA13 sur les rails puis on visse tout »,
10 mots en 1 seconde, un débit d'oral tout à fait ordinaire. Sur les 6 lignes
de sous-titres produites, **4 avaient leur fin avant leur début**. libass ne
les affiche jamais : les deux tiers du texte disparaissaient en silence, et
rien dans le rendu ne le signalait.

`test_un_debit_rapide_ne_perd_aucun_sous_titre` est le test qui porte la
correction. Les autres tiennent ce qu'elle ne doit pas abîmer.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.video.crop_tool import CropTool
from tools.video.subtitle_tool import DUREE_MINIMALE_VISIBLE, SubtitleTool

#: Les rendus réels exigent ffmpeg, que le CI n'a pas. Sauter n'est pas passer.
_SANS_FFMPEG = pytest.mark.skipif(
    shutil.which("ffmpeg") is None,
    reason="ffmpeg absent : aucun rendu réel ne peut être mesuré ici")


def _secondes(horodatage: str) -> float:
    """`0:00:01.50` → 1.5. C'est ce que lit libass, donc c'est ce qu'on vérifie."""
    heures, minutes, secondes = horodatage.split(":")
    return int(heures) * 3600 + int(minutes) * 60 + float(secondes)


def _lignes(chemin: str):
    """Les dialogues du fichier ASS, en (début, fin, texte)."""
    trouvees = []
    for ligne in Path(chemin).read_text(encoding="utf-8").splitlines():
        if not ligne.startswith("Dialogue:"):
            continue
        champs = ligne.split(",", 9)
        trouvees.append((_secondes(champs[1]), _secondes(champs[2]), champs[9]))
    return trouvees


# --- Le test qui porte la correction ------------------------------------------------

class TestAucunSousTitreNeDisparait:
    def test_un_debit_rapide_ne_perd_aucun_sous_titre(self, tmp_path):
        """Le cas mesuré : 10 mots en 1 seconde. 4 lignes sur 6 étaient perdues.

        Les deux assertions comptent, et la seconde a été ajoutée après un
        sabotage : avec l'ancienne répartition, le seul plancher de sortie
        rendait bien toutes les lignes « visibles », mais décalées **après** la
        fin de leur segment, où elles chevauchent les mots d'après. Vérifier
        seulement qu'elles s'affichent laissait donc passer le défaut.
        """
        segments = [{"start": 0.0, "end": 1.0,
                     "text": "on pose le BA13 sur les rails puis on visse tout"}]

        lignes = _lignes(SubtitleTool().generate_capcut_ass(
            segments, str(tmp_path / "st.ass")))

        assert lignes, "aucun sous-titre produit"
        invisibles = [(d, f) for d, f, _ in lignes if f <= d]
        assert invisibles == [], f"{len(invisibles)} ligne(s) ne s'afficheront jamais"
        assert max(fin for _, fin, _ in lignes) <= 1.0 + 1e-6, (
            "des sous-titres debordent apres la fin de leur segment")

    def test_les_mots_restent_dans_leur_segment(self, tmp_path):
        """Un mot qui commence après la fin de son segment est un mot perdu."""
        segments = [{"start": 0.0, "end": 1.0, "text": "un deux trois quatre cinq six"}]

        lignes = _lignes(SubtitleTool().generate_capcut_ass(
            segments, str(tmp_path / "st.ass")))

        assert max(fin for _, fin, _ in lignes) <= 1.0 + 1e-6
        assert min(debut for debut, _, _ in lignes) >= 0.0

    def test_les_lignes_se_suivent_sans_retour_en_arriere(self, tmp_path):
        segments = [{"start": 0.0, "end": 4.0, "text": "un deux trois quatre cinq six"}]

        lignes = _lignes(SubtitleTool().generate_capcut_ass(
            segments, str(tmp_path / "st.ass")))

        departs = [debut for debut, _, _ in lignes]
        assert departs == sorted(departs)

    def test_un_segment_sans_duree_reste_affichable(self, tmp_path):
        """Un transcripteur qui n'a pas su chronométrer rend `fin == debut`.
        Des temps approximatifs valent mieux qu'un texte perdu."""
        segments = [{"start": 5.0, "end": 5.0, "text": "aucune duree mesuree"}]

        lignes = _lignes(SubtitleTool().generate_capcut_ass(
            segments, str(tmp_path / "st.ass")))

        assert lignes
        assert all(fin > debut for debut, fin, _ in lignes)

    def test_des_temps_inverses_recoivent_le_plancher(self, tmp_path):
        """Les temps viennent parfois du transcripteur, pas de nous."""
        mots = [{"word": "bonjour", "start": 3.0, "end": 1.0},
                {"word": "monsieur", "start": 3.0, "end": 1.0}]

        (debut, fin, _), = _lignes(SubtitleTool().generate_capcut_ass(
            mots, str(tmp_path / "st.ass")))

        assert fin == pytest.approx(debut + DUREE_MINIMALE_VISIBLE)


class TestLaRepartitionDesMots:
    def test_chaque_mot_recoit_une_part_egale_de_la_duree_reelle(self):
        repartis = SubtitleTool.repartir_les_mots(["un", "deux", "trois", "quatre"],
                                                  0.0, 2.0)

        assert [m["start"] for m in repartis] == [0.0, 0.5, 1.0, 1.5]
        assert repartis[-1]["end"] == pytest.approx(2.0)

    def test_aucun_plancher_ne_pousse_un_mot_hors_du_segment(self):
        """Le plancher de 0,4 s était la cause : au troisième mot, le départ
        dépassait déjà la fin du segment."""
        repartis = SubtitleTool.repartir_les_mots(["a", "b", "c", "d", "e"], 0.0, 1.0)

        assert all(m["end"] <= 1.0 + 1e-6 for m in repartis)


class TestCeQueLaCorrectionNeDoitPasAbimer:
    def test_le_dernier_mot_du_groupe_est_mis_en_jaune(self, tmp_path):
        """La marque CapCut : c'est elle qui fait le style TikTok."""
        segments = [{"start": 0.0, "end": 2.0, "text": "bonjour tout le monde"}]

        _, _, texte = _lignes(SubtitleTool().generate_capcut_ass(
            segments, str(tmp_path / "st.ass")))[0]

        assert r"{\c&H00FFFF&}" in texte

    def test_les_contractions_francaises_restent_collees(self, tmp_path):
        """« c'est » ne doit jamais devenir « c » puis « est »."""
        segments = [{"start": 0.0, "end": 2.0, "text": "c ' est du BA13"}]

        contenu = Path(SubtitleTool().generate_capcut_ass(
            segments, str(tmp_path / "st.ass"))).read_text(encoding="utf-8")

        assert "c'est" in contenu

    def test_l_entete_ass_reste_en_1080x1920(self, tmp_path):
        contenu = Path(SubtitleTool().generate_capcut_ass(
            [{"start": 0.0, "end": 1.0, "text": "test"}],
            str(tmp_path / "st.ass"))).read_text(encoding="utf-8")

        assert "PlayResX: 1080" in contenu
        assert "PlayResY: 1920" in contenu

    def test_un_texte_vide_ne_produit_aucune_ligne(self, tmp_path):
        lignes = _lignes(SubtitleTool().generate_capcut_ass(
            [{"start": 0.0, "end": 1.0, "text": "   "}], str(tmp_path / "st.ass")))

        assert lignes == []


# --- Le format vertical, mesuré sur un vrai rendu ------------------------------------

@_SANS_FFMPEG
class TestLeFormatVertical:
    """`CropTool` n'avait aucun test. Ce qu'il produit se mesure sur le fichier."""

    @staticmethod
    def _une_video(dossier: Path, taille: str = "1280x720") -> Path:
        source = dossier / "source.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi",
             "-i", f"testsrc=size={taille}:rate=25:duration=2",
             "-c:v", "libx264", str(source)], capture_output=True, check=True)
        return source

    @staticmethod
    def _dimensions(fichier: Path) -> str:
        mesure = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height", "-of", "csv=p=0", str(fichier)],
            capture_output=True, text=True, check=True)
        return mesure.stdout.strip().rstrip(",")

    def test_une_video_16_9_devient_vraiment_du_1080x1920(self, tmp_path):
        source = self._une_video(tmp_path)
        sortie = tmp_path / "vertical.mp4"

        assert CropTool().convert_to_vertical_9_16(str(source), str(sortie)) is True
        assert sortie.is_file()
        assert self._dimensions(sortie) == "1080,1920"

    def test_une_video_absente_rend_faux_sans_lever(self, tmp_path):
        """Un échec se rapporte ; il ne remonte pas en exception au milieu
        d'une chaîne de production."""
        assert CropTool().convert_to_vertical_9_16(
            str(tmp_path / "nexiste-pas.mp4"), str(tmp_path / "out.mp4")) is False

    def test_le_dossier_de_sortie_est_cree(self, tmp_path):
        source = self._une_video(tmp_path)
        sortie = tmp_path / "un" / "deux" / "vertical.mp4"

        assert CropTool().convert_to_vertical_9_16(str(source), str(sortie)) is True
        assert sortie.is_file()
