"""Encodage des fichiers du dépôt.

Un BOM UTF-8 en tête de fichier est invisible à la lecture et casse des outils
qui lisent la première ligne : un `grep '^import'` ne voyait pas le premier
import de dix modules, ce qui a failli faire oublier `httpx` et `PyYAML` dans
`requirements.txt`.
"""
from pathlib import Path

BOM = b"\xef\xbb\xbf"
RACINE = Path(__file__).resolve().parent.parent
DOSSIERS_IGNORES = {".git", ".venv", "venv", "node_modules", "__pycache__", "data", "media"}


def fichiers_du_depot():
    for chemin in RACINE.rglob("*"):
        if not chemin.is_file():
            continue
        if DOSSIERS_IGNORES & set(chemin.relative_to(RACINE).parts):
            continue
        yield chemin


def test_aucun_fichier_ne_commence_par_un_bom():
    coupables = [
        str(f.relative_to(RACINE))
        for f in fichiers_du_depot()
        if f.read_bytes().startswith(BOM)
    ]

    assert coupables == [], f"BOM UTF-8 en tête de : {coupables}"


def test_le_premier_import_de_chaque_module_est_lisible_ligne_a_ligne():
    """Le symptôme concret du BOM : la première ligne devient illisible telle quelle."""
    illisibles = []
    for f in fichiers_du_depot():
        if f.suffix != ".py":
            continue
        with f.open(encoding="utf-8") as fichier:
            premiere = fichier.readline()
        if premiere.startswith("﻿"):
            illisibles.append(str(f.relative_to(RACINE)))

    assert illisibles == []


#: Les séquences que produit un texte UTF-8 relu en cp1252 puis ré-enregistré
#: en UTF-8. `â€”` (tiret cadratin) est la plus fréquente ; `Â«` et `Â»` suivent,
#: parce que ce dépôt écrit ses guillemets en chevrons.
DOUBLE_ENCODAGE = (
    "â€™", "â€œ", "â€”", "â€“", "Ã©", "Ã¨", "Ã ", "Ã§",
    "Ãª", "Ã´", "Ã®", "Ã¹", "Â«", "Â»",
)

EXTENSIONS_TEXTE = {".py", ".ts", ".tsx", ".md", ".yaml", ".yml", ".json"}


def test_aucun_fichier_ne_porte_de_double_encodage():
    """Un texte UTF-8 relu en cp1252 puis ré-enregistré est corrompu **dans le
    fichier**, pas seulement à l'affichage.

    **Mesuré le 03/09/2026.** Le propriétaire voit `step3 : ne peut pas
    dependre de step1 (narration) â€"` sur son téléphone. Ce n'était pas un
    problème d'affichage : `core/production/plan_video.py` contenait
    littéralement ces trois caractères à la place du tiret cadratin, sur
    13 lignes, et `config/permissions_services.yaml` sur 7.

    La réparation se fait par `encode("cp1252").decode("utf-8")`, **pas
    latin-1** : `€` (U+20AC) n'existe pas en latin-1, et c'est justement lui
    qui compose `â€”`. Un premier essai en latin-1 a laissé intactes exactement
    les lignes qu'il fallait réparer — l'erreur est facile, ce commentaire est
    là pour qu'elle ne se refasse pas.
    """
    abimes = []
    for chemin in fichiers_du_depot():
        if chemin.suffix not in EXTENSIONS_TEXTE:
            continue
        # Ce fichier-ci porte les séquences comme données : il s'exclut.
        if chemin.name == Path(__file__).name:
            continue
        try:
            texte = chemin.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for numero, ligne in enumerate(texte.splitlines(), 1):
            if any(motif in ligne for motif in DOUBLE_ENCODAGE):
                abimes.append(f"{chemin.relative_to(RACINE)}:{numero}")
                break

    assert not abimes, (
        "double encodage (UTF-8 relu en cp1252) : "
        f"{abimes}. Reparer par encode('cp1252').decode('utf-8'), ligne a "
        "ligne — une ligne saine echoue au decodage et reste intacte.")
