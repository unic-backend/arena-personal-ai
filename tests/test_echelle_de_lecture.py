"""La taille du texte de reponse, gardee par un chiffre.

Mesure du 19/09/2026, sur une capture d'ecran de son telephone : le corps de
texte etait a 13 px, et le plus GRAND reglage disponible valait 15 px — sous
les ~16-17 px que Claude affiche a cote, sur le meme ecran. Aucun reglage ne
pouvait donc lui donner ce qu'il demandait. Ce n'etait pas une preference mal
reglee, c'etait une echelle trop basse.

Ce fichier lit du CSS, ce que ce depot evite d'habitude — une garde qui lit du
texte voit une forme, pas un comportement. Elle est ici parce que rien
d'executable ne l'atteint : `jsdom` n'applique pas la feuille de style, donc
aucun test de la PWA ne peut mesurer la taille rendue. Sans ce fichier, un
retour silencieux a 13 px ne ferait tomber aucun test.
"""
import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parent.parent
       / "apps" / "pwa" / "src" / "index.css").read_text(encoding="utf-8")

#: En dessous, on retombe sous ce qu'il lit a cote dans Claude.
PLANCHER_PX = 15


def taille_de(cran: str) -> int:
    """Les pixels declares pour ce cran de lecture."""
    trouve = re.search(
        rf'\[data-reading-size="{cran}"\]\s*\{{\s*--reading-size:\s*(\d+)px', CSS)
    assert trouve, f"le cran de lecture « {cran} » n'existe pas dans index.css"
    return int(trouve.group(1))


@pytest.mark.parametrize("cran", ["compact", "comfortable", "large", "xlarge"])
def test_chaque_cran_tient_le_plancher(cran):
    assert taille_de(cran) >= PLANCHER_PX, (
        f"le cran « {cran} » est repasse sous {PLANCHER_PX} px : c'est "
        "exactement le defaut qu'il a signale le 19/09/2026")


def test_l_echelle_est_croissante():
    tailles = [taille_de(c) for c in ("compact", "comfortable", "large", "xlarge")]
    assert tailles == sorted(set(tailles)), (
        f"deux crans se valent ou se croisent : {tailles}")


def test_le_defaut_de_la_racine_suit_le_meme_plancher():
    """`:root` sert avant que le JavaScript ait pose `data-reading-size` —
    donc pendant le premier rendu, celui qu'il voit en ouvrant l'application."""
    trouve = re.search(r":root \{[^}]*--reading-size:\s*(\d+)px", CSS, re.S)
    assert trouve, "le defaut de `:root` a disparu"
    assert int(trouve.group(1)) >= PLANCHER_PX


@pytest.mark.parametrize("niveau", ["h2", "h3", "h4"])
def test_les_trois_niveaux_de_titre_sont_styles(niveau):
    """Ancre en debut de ligne : `.user-rich .md h2` existe aussi, et sans
    l'ancre il suffisait a faire passer ce test alors que la regle principale
    avait disparu (sabotage du 19/09/2026 qui ne mordait pas).

    `h2` et `h4` n'avaient aucune regle : depuis que tous les niveaux sont
    rendus (15/09/2026), un `#` ou un `####` sortait a la taille et a la
    graisse du corps de texte — un titre qui ne se voyait pas."""
    assert re.search(rf"^\.md {niveau} \{{[^}}]*font-size:", CSS, re.M), (
        f"`.md {niveau}` n'a pas de taille declaree")


@pytest.mark.parametrize("niveau", ["h2", "h3", "h4"])
def test_les_titres_suivent_la_taille_de_lecture(niveau):
    """En `em`, donc relatifs au reglage. En `rem`, un titre resterait fige
    pendant que le corps de texte grossit."""
    trouve = re.search(rf"^\.md {niveau} \{{[^}}]*font-size:\s*([\d.]+)(r?em)",
                       CSS, re.M)
    assert trouve, f"`.md {niveau}` n'a pas de taille declaree"
    assert trouve.group(2) == "em", (
        f"`.md {niveau}` est en {trouve.group(2)} : il ne suivra pas le "
        "reglage de lecture")
