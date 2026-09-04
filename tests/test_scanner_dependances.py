"""Le scanner de dépendances dit-il la vérité — y compris quand il ne sait pas ?

Deux bords, comme pour tout garde de ce dépôt :
- il **voit** une faille présente dans le rapport de pip-audit ;
- et surtout, quand la mesure échoue (outil absent, réseau coupé, sortie
  illisible), il répond `INCONNU`, jamais `PROPRE`. Un « aucune faille » qui
  n'a pas été mesuré est le mensonge le plus cher : il endort une alerte.

Aucun test ici ne touche le réseau. L'exécuteur de pip-audit est injecté :
chaque cas fournit exactement la sortie qu'il veut éprouver — un vrai rapport,
un rapport vide, un `None` (outil/réseau absent), ou du charabia.
"""
import importlib.util
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "scanner_dependances", RACINE / "scripts" / "scanner_dependances.py")
dep = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = dep          # requis avant exec : @dataclass relit son module
_spec.loader.exec_module(dep)


def _rapport_json(paquets):
    """Fabrique un JSON de la forme exacte que produit `pip-audit -f json`."""
    return json.dumps({"dependencies": paquets, "fixes": []})


UN_PAQUET_VULNERABLE = [{
    "name": "pypdf", "version": "6.14.2",
    "vulns": [{"id": "CVE-2026-84310", "fix_versions": ["6.16.1"],
               "aliases": ["GHSA-xxxx"], "description": "## Résumé\nUn dépassement…"}],
}]


# --- Ce qui DOIT être vu -------------------------------------------------------

def test_une_faille_du_rapport_est_lue():
    failles = dep.analyser_rapport(_rapport_json(UN_PAQUET_VULNERABLE))

    assert len(failles) == 1
    assert failles[0].paquet == "pypdf"
    assert failles[0].identifiant == "CVE-2026-84310"
    assert failles[0].corrige_dans == "6.16.1"


def test_le_resume_tient_sur_une_ligne_sans_markdown():
    failles = dep.analyser_rapport(_rapport_json(UN_PAQUET_VULNERABLE))

    assert "\n" not in failles[0].resume
    assert not failles[0].resume.startswith("#")


def test_la_meme_faille_listee_deux_fois_ne_compte_qu_une():
    deux_fois = [UN_PAQUET_VULNERABLE[0], UN_PAQUET_VULNERABLE[0]]

    assert len(dep.analyser_rapport(_rapport_json(deux_fois))) == 1


# --- Ce qui NE DOIT PAS crier ---------------------------------------------------

def test_un_rapport_sans_faille_est_propre():
    propre = [{"name": "fastapi", "version": "0.141.1", "vulns": []}]

    assert dep.analyser_rapport(_rapport_json(propre)) == []


# --- Les trois états d'`auditer` -----------------------------------------------

def test_auditer_propre(tmp_path):
    fichier = tmp_path / "requirements.txt"
    fichier.write_text("fastapi==0.141.1\n")
    rapport = dep.auditer(fichier, executeur=lambda _f: _rapport_json(
        [{"name": "fastapi", "version": "0.141.1", "vulns": []}]))

    assert rapport.etat == "PROPRE"
    assert rapport.code_de_sortie == 0


def test_auditer_failles(tmp_path):
    fichier = tmp_path / "requirements.txt"
    fichier.write_text("pypdf==6.14.2\n")
    rapport = dep.auditer(fichier, executeur=lambda _f: _rapport_json(UN_PAQUET_VULNERABLE))

    assert rapport.etat == "FAILLES"
    assert rapport.code_de_sortie == 1
    assert rapport.failles[0].paquet == "pypdf"


def test_auditer_inconnu_quand_l_outil_ne_repond_pas(tmp_path):
    """L'exécuteur renvoie None : outil absent ou base injoignable."""
    fichier = tmp_path / "requirements.txt"
    fichier.write_text("pypdf==6.14.2\n")
    rapport = dep.auditer(fichier, executeur=lambda _f: None)

    assert rapport.etat == "INCONNU", "un échec de mesure ne doit jamais passer pour PROPRE"
    assert rapport.code_de_sortie == 2
    assert rapport.raison


def test_auditer_inconnu_sur_une_sortie_illisible(tmp_path):
    fichier = tmp_path / "requirements.txt"
    fichier.write_text("pypdf==6.14.2\n")
    rapport = dep.auditer(fichier, executeur=lambda _f: "ce n'est pas du JSON")

    assert rapport.etat == "INCONNU"
    assert rapport.failles == []


def test_auditer_inconnu_si_le_fichier_manque(tmp_path):
    rapport = dep.auditer(tmp_path / "absent.txt", executeur=lambda _f: "{}")

    assert rapport.etat == "INCONNU"
    assert "introuvable" in rapport.raison


# --- Robustesse du parseur -----------------------------------------------------

def test_un_json_sans_dependencies_est_une_erreur():
    import pytest
    with pytest.raises(ValueError):
        dep.analyser_rapport('{"autre_chose": []}')


def test_un_json_casse_est_une_erreur():
    import pytest
    with pytest.raises(ValueError):
        dep.analyser_rapport("{pas du json")
