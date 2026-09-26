"""Encodage des fichiers du dépôt.

Un BOM UTF-8 en tête de fichier est invisible à la lecture et casse des outils
qui lisent la première ligne : un `grep '^import'` ne voyait pas le premier
import de dix modules, ce qui a failli faire oublier `httpx` et `PyYAML` dans
`requirements.txt`.
"""
import re
from pathlib import Path

import pytest

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

#: Chaque octet relu en cp1252 donne un caractere. Les cinq octets que cp1252
#: ne definit pas (0x81, 0x8D, 0x8F, 0x90, 0x9D) passent tels quels, en
#: caractere de controle — c'est ce que fait Windows, et c'est ce qui rendait
#: `❌` (E2 9D 8C) invisible a la liste fermee ci-dessus.
_OCTET_DU_CARACTERE = {}
for _octet in range(256):
    try:
        _OCTET_DU_CARACTERE[bytes([_octet]).decode("cp1252")] = _octet
    except UnicodeDecodeError:
        _OCTET_DU_CARACTERE[chr(_octet)] = _octet

#: Une tete de sequence UTF-8 (0xC2-0xF4) suivie d'octets de continuation
#: (0x80-0xBF), le tout relu en cp1252.
_SEQUENCE_SUSPECTE = re.compile(
    "[Â-ô]["
    + "".join(re.escape(c) for c, o in _OCTET_DU_CARACTERE.items() if 0x80 <= o <= 0xBF)
    + "]+")


def double_encodages(ligne: str) -> list:
    """Les morceaux de `ligne` qui sont de l'UTF-8 relu en cp1252.

    Generique, et non plus une liste de motifs : mesure du 26/09/2026,
    `apps/backend/routers/chat.py` affichait `âŒ Ollama hors-ligne.` et
    `âš ï¸ Le calcul…` au proprietaire, et la liste fermee — ecrite pour les
    accents et les tirets — ne connaissait aucun emoji. Un morceau n'est
    retenu que s'il redevient de l'UTF-8 **valide** une fois ramene a ses
    octets : « é» » (E9 BB) n'est pas une sequence complete et reste sain.
    """
    generiques = [
        morceau for morceau in _SEQUENCE_SUSPECTE.findall(ligne)
        if _redevient_utf8(morceau)
    ]
    # La liste fermee reste EN PLUS : `Ã ` y figure avec une espace simple (le
    # `\xa0` de « à » perdu en route), qui ne redevient plus de l'UTF-8 et que
    # le detecteur generique ne peut donc pas voir.
    return generiques + [motif for motif in DOUBLE_ENCODAGE if motif in ligne]


def _redevient_utf8(morceau: str) -> bool:
    try:
        bytes(_OCTET_DU_CARACTERE[c] for c in morceau).decode("utf-8")
    except (KeyError, UnicodeDecodeError):
        return False
    return True


@pytest.mark.parametrize("abime", DOUBLE_ENCODAGE + (
    "\u00e2\u009d\u0152",                    # ❌
    "\u00e2\u0161\u00a0\u00ef\u00b8\u008f",  # ⚠️
    "\u00e2\u0153\u2026",                    # ✅
    "\u00f0\u0178\u017d\u00ac",              # 🎬
))
def test_le_detecteur_attrape_les_accents_et_les_emojis(abime):
    assert double_encodages(f"texte {abime} texte")


@pytest.mark.parametrize("sain", [
    "« Qualité » — déjà là, à côté, où, ça, Ça, œuvre, naïf, été»",
    "❌ Ollama hors-ligne.", "⚠️ Le calcul", "✅ fait", "🎬 montage",
])
def test_le_detecteur_laisse_le_texte_sain(sain):
    assert double_encodages(sain) == []

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
            if double_encodages(ligne):
                abimes.append(f"{chemin.relative_to(RACINE)}:{numero}")
                break

    assert not abimes, (
        "double encodage (UTF-8 relu en cp1252) : "
        f"{abimes}. Reparer par encode('cp1252').decode('utf-8'), ligne a "
        "ligne — une ligne saine echoue au decodage et reste intacte.")
