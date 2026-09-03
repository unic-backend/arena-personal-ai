"""Un `.ps1` non-ASCII ne se lance pas du tout sous Windows PowerShell.

**Mesuré le 03/09/2026, sur la machine du propriétaire.** Deux installeurs
refusent de démarrer :

    Le terminateur " est manquant dans la chaîne.
    ... ite-Host "  UI/UX Pro Max â€" intelligence de design, a cote d'ARENA"

Windows PowerShell 5.1 décode un `.ps1` **sans BOM** en cp1252, pas en UTF-8.
Un `—` (trois octets en UTF-8) devient trois caractères parasites, `«` et `»`
en produisent deux chacun. Quand ces octets tombent dans une chaîne, le
guillemet fermant n'est plus trouvé et **le script entier est refusé avant la
première ligne**.

La solution évidente — enregistrer en UTF-8 avec BOM — est fermée ici :
`test_aucun_fichier_ne_commence_par_un_bom` l'interdit, pour de bonnes
raisons de son côté. Reste la seule qui marche partout : **de l'ASCII pur**.

Ce que ça a coûté avant d'être vu : cinq des sept scripts du dépôt en
contenaient. Les trois plus anciens n'avaient pas encore cassé — leurs
caractères ne tombaient pas dans une chaîne. Ils attendaient la mauvaise
ligne au mauvais endroit.
"""
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
SCRIPTS = sorted((RACINE / "scripts").glob("*.ps1"))

#: Ce qu'on écrit spontanément en français et qui casse : les guillemets
#: chevrons et le tiret cadratin. Écrire `"` et `-` à la place ne coûte rien.
PIEGES = {"«": '"', "»": '"', "—": "-", "’": "'"}


def test_il_y_a_bien_des_scripts_a_verifier():
    """Une garde qui ne mesure rien passe toujours."""
    assert SCRIPTS, "aucun .ps1 trouve : ce fichier ne garde plus rien"


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_chaque_script_powershell_est_en_ascii_pur(script):
    texte = script.read_text(encoding="utf-8")
    hors = sorted({c for c in texte if ord(c) > 127})

    conseil = ", ".join(f"« {c} » -> « {PIEGES[c]} »" for c in hors if c in PIEGES)
    assert not hors, (
        f"{script.name} contient {hors} : PowerShell 5.1 lit ce fichier en "
        f"cp1252 et refusera de le lancer. {conseil or 'Remplace par de l ASCII.'}")


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_aucune_ligne_ne_laisse_une_chaine_ouverte(script):
    """Le symptôme exact vu par le propriétaire : « Le terminateur " est
    manquant ». Il vient d'un guillemet en trop dans un `Write-Host`, que
    l'ASCII seul ne garantit pas."""
    impaires = [n for n, ligne in enumerate(script.read_text(encoding="utf-8").split("\n"), 1)
                if ligne.count('"') % 2]

    assert not impaires, (
        f"{script.name} : guillemets impairs lignes {impaires}. PowerShell "
        "refusera le script entier, pas seulement cette ligne.")


def test_le_piege_est_nomme_dans_le_fichier():
    """Une règle sans sa raison se fait retirer par le prochain qui trouve
    l'ASCII inutilement austère dans un dépôt francophone."""
    source = Path(__file__).read_text(encoding="utf-8")

    assert "cp1252" in source
    assert "BOM" in source, "le lecteur ne saura pas pourquoi le BOM est exclu"
