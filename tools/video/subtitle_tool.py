import logging
import re
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("usman.tools.video.subtitle")

#: Ce qu'on donne à un mot quand le segment n'a **aucune** durée mesurable
#: (`fin <= debut`). On avance d'un pas plutôt que de perdre le texte : des
#: sous-titres un peu décalés valent mieux que pas de sous-titres du tout.
DUREE_PAR_MOT_PAR_DEFAUT = 0.4

#: Le minimum qu'on laisse à une ligne dont les temps mesurés sont inversés ou
#: nuls. Sans ce plancher, la ligne est écrite avec une fin **avant** son
#: début, et libass ne l'affiche jamais.
DUREE_MINIMALE_VISIBLE = 0.2


class SubtitleTool:
    """Générateur de sous-titres dynamiques CapCut/TikTok avec protection des apostrophes françaises.

    **Défaut mesuré le 02/09/2026, sur un segment ordinaire :** « on pose le
    BA13 sur les rails puis on visse tout », 10 mots en 1 seconde — un débit
    normal à l'oral. Sur les 6 lignes produites, **4 avaient leur fin avant
    leur début** et n'étaient donc jamais affichées.

    La cause : un plancher de 0,4 s par mot était appliqué **avant** de vérifier
    qu'il tenait dans le segment. Au troisième mot, le départ dépassait déjà la
    fin du segment. Les mots sont maintenant répartis sur la durée **réelle**,
    et aucune ligne ne peut sortir avec une fin antérieure à son début.

    Ce fichier n'avait aucun test jusqu'au 02/09/2026, avec `CropTool` : les
    deux outils qui font le résultat visible étaient les deux seuls sans
    mesure. C'est ce qui a permis au défaut de tenir.
    """

    @staticmethod
    def format_ass_time(seconds: float) -> str:
        centisecs = int((seconds % 1) * 100)
        secs = int(seconds) % 60
        mins = int(seconds // 60) % 60
        hours = int(seconds // 3600)
        return f"{hours}:{mins:02d}:{secs:02d}.{centisecs:02d}"

    def clean_french_text(self, text: str) -> str:
        """Nettoie les erreurs de ponctuations et recolle les contractions (c', d', l')."""
        text = re.sub(r"\b([cCdDlLjJmMnNsStT])\s*['’]\s*", r"\1'", text)
        return text.strip()

    @staticmethod
    def repartir_les_mots(mots: List[str], debut: float, fin: float) -> List[Dict[str, Any]]:
        """Répartit les mots sur la durée **réelle** du segment.

        Chaque mot reçoit une part égale de ce que dure vraiment le segment.
        Aucun plancher n'est appliqué ici : un plancher fait déborder les mots
        hors du segment, et un mot qui commence après la fin de son segment ne
        s'affiche jamais. Un sous-titre rapide reste lisible ; un sous-titre
        absent, non.

        Un segment sans durée mesurable (`fin <= debut`, ce que rend un
        transcripteur qui n'a pas su chronométrer) avance d'un pas par défaut :
        des temps approximatifs valent mieux qu'un texte perdu.
        """
        duree = fin - debut
        pas = duree / len(mots) if duree > 0 else DUREE_PAR_MOT_PAR_DEFAUT
        return [{"start": debut + i * pas, "end": debut + (i + 1) * pas, "word": mot}
                for i, mot in enumerate(mots)]

    def generate_capcut_ass(self, words_or_segments: List[Dict[str, Any]], output_path: str) -> str:
        out_file = Path(output_path).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)

        ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TikTok,Arial,65,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,50,50,280,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        # Reconstitution de paires de mots propres sans isoler d'apostrophes
        raw_words = []
        if words_or_segments and "word" in words_or_segments[0]:
            for item in words_or_segments:
                w_text = self.clean_french_text(item.get("word", ""))
                if w_text and w_text not in ["C", "c", "D", "d", "L", "l", "'", "’"]:
                    raw_words.append({
                        "start": item.get("start", 0.0),
                        "end": item.get("end", 0.0),
                        "word": w_text
                    })
        else:
            for seg in words_or_segments:
                cleaned_seg = self.clean_french_text(seg.get("text", ""))
                words = cleaned_seg.split()
                if not words:
                    continue
                raw_words.extend(self.repartir_les_mots(
                    words, float(seg.get("start", 0.0)), float(seg.get("end", 0.0))))

        # Regroupement par 2 à 3 mots max
        chunks = []
        current_chunk = []
        for w in raw_words:
            current_chunk.append(w)
            # Ne coupe pas si le mot finit par une apostrophe
            if len(current_chunk) >= 2 and not w["word"].endswith("'"):
                chunks.append(current_chunk)
                current_chunk = []
        if current_chunk:
            chunks.append(current_chunk)

        dialogue_lines = []
        for chunk in chunks:
            if not chunk:
                continue
            # La garantie de sortie : une ligne dont la fin precede le debut
            # n'est pas affichee par libass — elle disparait en silence, ce qui
            # se lit comme un sous-titre oublie. Les temps viennent parfois du
            # transcripteur et pas de nous : le plancher est pose ICI, au
            # dernier endroit par lequel toutes les lignes passent.
            debut = chunk[0]["start"]
            fin = chunk[-1]["end"]
            if fin <= debut:
                fin = debut + DUREE_MINIMALE_VISIBLE
            start_t = self.format_ass_time(debut)
            end_t = self.format_ass_time(fin)

            words_str = [w["word"] for w in chunk]
            if len(words_str) > 1:
                # Mettre le dernier mot en JAUNE BRILLANT {\c&H00FFFF&}
                highlighted_text = " ".join(words_str[:-1]) + r" {\c&H00FFFF&}" + words_str[-1] + r"{\c&H00FFFFFF&}"
            else:
                highlighted_text = r"{\c&H00FFFF&}" + words_str[0] + r"{\c&H00FFFFFF&}"

            dialogue_lines.append(f"Dialogue: 0,{start_t},{end_t},TikTok,,0,0,0,,{highlighted_text}")

        full_ass = ass_header + "\n".join(dialogue_lines)
        out_file.write_text(full_ass, encoding="utf-8")
        logger.info(f"Fichier ASS CapCut généré : {out_file.name}")
        return str(out_file)
