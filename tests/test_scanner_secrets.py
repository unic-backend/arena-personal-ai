"""Le scanner attrape-t-il un secret, et se tait-il sur ce qui n'en est pas un ?

Un scanner qui rate un secret laisse la fuite entrer ; un scanner qui crie à
chaque chaîne longue finit ignoré — et un scanner ignoré ne protège rien. Ce
fichier tient les deux bords : il prouve qu'un vrai secret est vu, et qu'une
référence `${VAR}`, un exemple ou une valeur répétitive ne l'est pas.

Aucune valeur réelle ici. Chaque « secret » de ce fichier est fabriqué de la
forme voulue — un fichier de test qui contiendrait un vrai secret serait
lui-même la fuite qu'il prétend chercher. Les lignes qui portent une valeur de
forme secrète sont marquées `# scanner-secrets: ignore` pour que le scanner,
lancé sur ce dépôt, reste vert.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "scanner_secrets", RACINE / "scripts" / "scanner_secrets.py")
scanner = importlib.util.module_from_spec(_spec)
# Enregistré avant l'exécution : `@dataclass` (avec `from __future__ import
# annotations`) va relire son propre module dans `sys.modules`, et le trouver à
# None y ferait échouer la simple *collecte* du fichier.
sys.modules[_spec.name] = scanner
_spec.loader.exec_module(scanner)


# --- Ce qui DOIT déclencher -----------------------------------------------------

SECRETS_NOMMES = [
    ("clé privée PEM",
     "-----BEGIN RSA PRIVATE KEY-----\nMIIEpQIBAAKCAQEA7q\n-----END RSA PRIVATE KEY-----"),  # noqa: E501  # scanner-secrets: ignore
    ("clé d'accès AWS", 'aws_key = "AKIAIOSFODNN7EXAMPLE"'),  # scanner-secrets: ignore
    ("jeton Slack", "slack = xoxb-2100-99999-abcdefghijklmnop"),  # scanner-secrets: ignore
]


@pytest.mark.parametrize("genre_attendu, contenu", SECRETS_NOMMES)
def test_un_secret_reconnaissable_est_vu(genre_attendu, contenu):
    trouvailles = scanner.scanner_le_texte("faux.txt", contenu)

    assert trouvailles, f"un {genre_attendu} n'a pas été vu"
    assert any(genre_attendu in t.genre for t in trouvailles)


def test_une_affectation_de_cle_api_est_vue():
    # Valeur mélangée et longue, jamais utilisée ailleurs : une tête de secret.
    contenu = 'API_KEY = "Zq7Z-h4T2p-Kw9Rf-Lm3Xv-Nb8Yc-Ud6Ae"'  # scanner-secrets: ignore

    trouvailles = scanner.scanner_le_texte("config.py", contenu)

    assert trouvailles, "une affectation de clé API n'a pas été vue"
    assert "affectation" in trouvailles[0].genre


# --- Ce qui NE DOIT PAS déclencher ---------------------------------------------

RIEN_A_SIGNALER = [
    'API_KEY = "${ARENA_API_KEY}"',              # une référence, pas une valeur
    "api_key = os.environ['ARENA_API_KEY']",     # lu d'un environnement
    'password = "changeme"',                      # placeholder trop connu
    'token = "votre-cle-ici"',                    # placeholder explicite
    'secret = "aaaaaaaaaaaaaaaa"',                # aucune entropie
    'chemin = "/home/usman/un/tres/long/chemin/vers/un/fichier.pdf"',  # nom banal
    'ratio = "0.9290304000000001"',              # un nombre, pas un secret
]


@pytest.mark.parametrize("contenu", RIEN_A_SIGNALER)
def test_ce_qui_n_est_pas_un_secret_reste_muet(contenu):
    assert scanner.scanner_le_texte("faux.py", contenu) == []


def test_le_marqueur_ignore_fait_taire_une_ligne():
    contenu = 'cle = "Zq7Z-h4T2p-Kw9Rf-Lm3Xv"  # scanner-secrets: ignore'

    assert scanner.scanner_le_texte("faux.py", contenu) == []


# --- Le masquage ne révèle jamais la valeur ------------------------------------

def test_le_masque_ne_contient_pas_la_valeur():
    valeur = "Zq7Z-h4T2p-Kw9Rf-Lm3Xv-Nb8Yc"  # 28 caractères, inventée  # scanner-secrets: ignore

    masque = scanner.masquer(valeur)

    assert valeur not in masque
    assert masque.startswith("Zq7Z")
    assert masque.endswith("(28 car.)")
    assert "Kw9Rf" not in masque, "le milieu de la valeur ne doit pas apparaître"


def test_une_valeur_courte_est_entierement_masquee():
    assert scanner.masquer("abcd1234") == "…" * 8


def test_la_trouvaille_montre_le_masque_jamais_la_valeur():
    contenu = 'token = "Zq7Z-h4T2p-Kw9Rf-Lm3Xv-Nb8Yc"'  # scanner-secrets: ignore

    [trouvaille] = scanner.scanner_le_texte("x.py", contenu)
    rendu = trouvaille.rendre()

    assert "Zq7Z-h4T2p-Kw9Rf-Lm3Xv-Nb8Yc" not in rendu
    assert "x.py:1" in rendu


# --- L'entropie sépare le mot de passe factice du vrai secret ------------------

def test_une_valeur_repetitive_a_une_entropie_basse():
    assert scanner.entropie_de_shannon("aaaaaaaaaa") < 1.0


def test_une_valeur_melangee_a_une_entropie_haute():
    assert scanner.entropie_de_shannon("Zq7Z-h4T2p-Kw9Rf") > 3.0  # scanner-secrets: ignore


# --- Le périmètre : fichiers suivis, contenu binaire, dépôt absent -------------

def _depot_git(chemin: Path, fichiers: dict) -> Path:
    chemin.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=chemin, check=True)
    for rel, contenu in fichiers.items():
        f = chemin / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(contenu, bytes):
            f.write_bytes(contenu)
        else:
            f.write_text(contenu, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=chemin, check=True)
    return chemin


def test_un_fichier_non_suivi_est_ignore(tmp_path):
    depot = _depot_git(tmp_path / "d", {"suivi.py": 'x = 1\n'})
    # Écrit APRÈS le `git add` : il existe sur le disque mais n'est pas suivi.
    (depot / "brouillon.py").write_text(
        'key = "Zq7Z-h4T2p-Kw9Rf-Lm3Xv-Nb8Yc"\n', encoding="utf-8")  # scanner-secrets: ignore

    trouvailles = scanner.scanner_le_depot(depot)

    assert trouvailles == [], "un fichier non suivi ne doit pas être scanné"


def test_un_secret_dans_un_fichier_suivi_est_trouve(tmp_path):
    depot = _depot_git(tmp_path / "d", {
        "config.py": 'API_KEY = "Zq7Z-h4T2p-Kw9Rf-Lm3Xv-Nb8Yc"\n'})  # scanner-secrets: ignore

    trouvailles = scanner.scanner_le_depot(depot)

    assert len(trouvailles) == 1
    assert trouvailles[0].fichier == "config.py"


def test_un_fichier_binaire_ne_plante_pas(tmp_path):
    depot = _depot_git(tmp_path / "d", {"image.bin": b"\x00\x01\x02sk-abcdef\x00"})

    assert scanner.scanner_le_depot(depot) == []


def test_hors_d_un_depot_git_le_scan_le_dit(tmp_path):
    assert scanner.fichiers_suivis(tmp_path) is None
    assert scanner.principal(tmp_path) == 2


def test_le_vrai_depot_est_propre():
    """Le dépôt d'Usman ne contient aucun secret probable dans ses fichiers suivis.

    Ce test est le garde vivant : le jour où quelqu'un versionne une vraie clé,
    il vire au rouge ici avant la revue. S'il échoue, ce n'est pas le test qu'il
    faut changer — c'est le secret qu'il faut retirer.
    """
    trouvailles = scanner.scanner_le_depot(RACINE)

    assert trouvailles == [], "\n".join(t.rendre() for t in trouvailles)
