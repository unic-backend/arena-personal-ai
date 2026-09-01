"""Les deux langues de l'interface portent exactement les mêmes clés.

Une clé ajoutée dans une seule langue n'échoue pas : elle affiche **le nom de
la clé** à l'écran du propriétaire. `sync.refused` en anglais seulement lui
aurait montré « sync.refused » au lieu de lui dire que sa conversation n'a pas
été sauvegardée.

Aucun test ne couvrait ce fichier avant le 01/09/2026, alors que c'est le seul
endroit du dépôt où une erreur est **invisible à la compilation** : TypeScript
ne compare pas deux littéraux d'objet entre eux.
"""
import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
FICHIER = RACINE / "apps" / "pwa" / "src" / "lib" / "i18n" / "index.ts"

#: `'cle': ...` en début de ligne indentée — la forme de toutes les entrées.
LIGNE_DE_CLE = re.compile(r"^\s{2}'([^']+)':")


def bloc(nom: str) -> str:
    """Le corps du dictionnaire `const <nom>: Dict = { ... };`."""
    source = FICHIER.read_text(encoding="utf-8")
    debut = source.index(f"const {nom}: Dict = {{")
    fin = source.index("\n};", debut)
    return source[debut:fin]


def cles(nom: str) -> set:
    return {m.group(1) for ligne in bloc(nom).splitlines()
            if (m := LIGNE_DE_CLE.match(ligne))}


@pytest.fixture(scope="module")
def dictionnaires():
    return cles("en"), cles("fr")


def test_le_fichier_de_traductions_existe_et_est_lisible():
    """Sans ça, les tests suivants passeraient en ne mesurant rien."""
    assert FICHIER.exists()
    assert len(cles("en")) > 100, "le decoupage n'a presque rien trouve"


def test_aucune_cle_ne_manque_en_francais(dictionnaires):
    """Le propriétaire lit le français : une clé manquante s'affiche crue."""
    en, fr = dictionnaires

    manquantes = sorted(en - fr)

    assert manquantes == [], f"cles sans traduction francaise : {manquantes}"


def test_aucune_cle_ne_manque_en_anglais(dictionnaires):
    en, fr = dictionnaires

    manquantes = sorted(fr - en)

    assert manquantes == [], f"cles sans version anglaise : {manquantes}"


def test_la_cle_de_synchronisation_refusee_est_dans_les_deux(dictionnaires):
    """Elle dit à quelqu'un que sa conversation n'est PAS sauvegardée."""
    en, fr = dictionnaires

    assert "sync.refused" in en and "sync.refused" in fr
