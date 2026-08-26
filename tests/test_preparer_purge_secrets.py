"""Le script de préparation de la purge trouve-t-il bien les secrets, et rien d'autre ?

Un script qui rate un secret laisse la fuite en place ; un script qui prend une
référence `${VAR}` pour un secret réécrirait l'historique pour rien.
"""
import importlib.util
import subprocess
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "preparer_purge_secrets", RACINE / "scripts" / "preparer_purge_secrets.py"
)
purge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(purge)


# Valeurs inventées, de la même forme que celles trouvées dans l'historique.
# Aucune valeur réelle ici : ce fichier serait sinon lui-même une fuite, et la
# purge le réécrirait — faisant échouer l'étape de vérification du runbook.
VALEURS_DE_FORME_SECRETE = [
    "exemple-cle-2099",
    "exemple_secret_key_00000",
    "0123456789abcdef0123456789abcdef",
]


@pytest.mark.parametrize("valeur", VALEURS_DE_FORME_SECRETE)
def test_une_vraie_valeur_est_reconnue(valeur):
    assert purge.est_un_secret(valeur) is True


@pytest.mark.parametrize(
    "valeur",
    ["${ARENA_API_KEY}", "${CREDS_KEY}", "", "   ", "court", "abc"],
)
def test_une_reference_ou_une_valeur_courte_est_ignoree(valeur):
    assert purge.est_un_secret(valeur) is False


def test_les_guillemets_ne_font_pas_passer_une_reference_pour_un_secret():
    assert purge.est_un_secret('"${ARENA_API_KEY}"') is False


def test_le_masquage_ne_revele_pas_la_valeur():
    valeur = "exemple-cle-2099"          # 16 caractères, valeur inventée

    masque = purge.masquer(valeur)

    assert valeur not in masque
    assert masque.startswith("exem")
    assert masque.endswith("(16 car.)")
    assert "cle" not in masque, "le milieu de la valeur ne doit pas apparaître"


def test_une_valeur_tres_courte_est_entierement_masquee():
    assert purge.masquer("abc") == "…" * 3


def test_le_motif_librechat_isole_la_cle():
    fichier, motif = purge.EMPLACEMENTS[0]
    contenu = '      apiKey: "valeur-secrete-ici"\n      baseURL: "http://x"\n'

    assert fichier == "librechat.yaml"
    assert motif.findall(contenu) == ["valeur-secrete-ici"]


def test_le_motif_compose_isole_les_variables_sensibles():
    _, motif = purge.EMPLACEMENTS[1]
    contenu = (
        "      - CREDS_KEY=valeur-une\n"
        "      - JWT_SECRET=valeur-deux\n"
        "      - WEBUI_NAME=ARENA\n"          # pas un secret : ne doit pas sortir
        "      - ARENA_API_KEY=${ARENA_API_KEY}\n"
    )

    trouves = motif.findall(contenu)

    assert "valeur-une" in trouves
    assert "valeur-deux" in trouves
    assert "ARENA" not in trouves
    assert [v for v in trouves if purge.est_un_secret(v)] == ["valeur-une", "valeur-deux"]


# --- Lecture d'un vrai historique Git -----------------------------------------
#
# La version precedente de ces tests interrogeait l'historique de CE depot et
# exigeait d'y trouver au moins 5 secrets. Deux defauts :
#   - en integration continue, `actions/checkout` ne recupere qu'un seul commit :
#     la recherche ne trouvait rien et le test echouait ;
#   - une fois la purge (T-01) faite, il n'y aura plus aucun secret a trouver :
#     le test aurait echoue une seconde fois, pour la raison inverse.
# Un test ne doit pas dependre d'un etat temporaire du depot qu'il habite.


def depot_git(dossier: Path, commits: list[tuple[str, str]]) -> Path:
    """Fabrique un vrai dépôt Git, un commit par entrée `(fichier, contenu)`."""
    subprocess.run(["git", "init", "-q", "-b", "principal", str(dossier)], check=True)
    for cle, valeur in [("user.email", "test@test"), ("user.name", "test")]:
        subprocess.run(["git", "-C", str(dossier), "config", cle, valeur], check=True)

    for nom, contenu in commits:
        (dossier / nom).write_text(contenu, encoding="utf-8")
        subprocess.run(["git", "-C", str(dossier), "add", nom], check=True)
        subprocess.run(["git", "-C", str(dossier), "commit", "-q", "-m", f"ajout {nom}"],
                       check=True)
    return dossier


def test_une_cle_versionnee_puis_retiree_est_retrouvee(tmp_path):
    """Le cas réel : la valeur ne figure plus dans le fichier, mais reste dans l'historique."""
    depot = depot_git(tmp_path / "depot", [
        ("librechat.yaml", 'endpoints:\n  custom:\n    - apiKey: "cle-fuitee-2099"\n'),
        ("librechat.yaml", 'endpoints:\n  custom:\n    - apiKey: "${ARENA_API_KEY}"\n'),
    ])

    trouves = purge.secrets_de_l_historique(depot)

    assert list(trouves) == ["cle-fuitee-2099"]
    assert trouves["cle-fuitee-2099"] == "librechat.yaml"


def test_les_variables_de_docker_compose_sont_retrouvees(tmp_path):
    depot = depot_git(tmp_path / "depot", [
        ("docker-compose.yml",
         "services:\n  x:\n    environment:\n"
         "      - CREDS_KEY=valeur-creds-0099\n"
         "      - JWT_SECRET=valeur-jwt-0099\n"
         "      - WEBUI_NAME=ARENA\n"),
    ])

    trouves = purge.secrets_de_l_historique(depot)

    assert sorted(trouves) == ["valeur-creds-0099", "valeur-jwt-0099"]
    assert "ARENA" not in trouves


def test_une_reference_a_une_variable_n_est_pas_prise_pour_un_secret(tmp_path):
    depot = depot_git(tmp_path / "depot", [
        ("docker-compose.yml",
         "services:\n  x:\n    environment:\n      - CREDS_KEY=${CREDS_KEY}\n"),
    ])

    assert purge.secrets_de_l_historique(depot) == {}


def test_un_depot_sans_secret_ne_renvoie_rien(tmp_path):
    """Après la purge, c'est l'état attendu — et il ne doit pas faire échouer un test."""
    depot = depot_git(tmp_path / "depot", [
        ("librechat.yaml", 'apiKey: "${ARENA_API_KEY}"\n'),
        ("README.md", "Rien de sensible ici.\n"),
    ])

    assert purge.secrets_de_l_historique(depot) == {}


def test_un_clone_superficiel_est_reconnu(tmp_path):
    """`actions/checkout` n'en récupère qu'un commit : y chercher ne prouve rien."""
    complet = depot_git(tmp_path / "complet", [
        ("librechat.yaml", 'apiKey: "cle-fuitee-2099"\n'),
        ("librechat.yaml", 'apiKey: "${ARENA_API_KEY}"\n'),
    ])
    superficiel = tmp_path / "superficiel"
    subprocess.run(["git", "clone", "-q", "--depth", "1", "--no-local",
                    f"file://{complet}", str(superficiel)], check=True)

    assert purge.historique_complet(complet) is True
    assert purge.historique_complet(superficiel) is False


def test_le_script_fonctionne_sur_l_historique_de_ce_depot():
    """Sur ce dépôt : il doit s'exécuter sans erreur, quel que soit ce qu'il trouve.

    Rien n'est affirmé sur le nombre de secrets — il vaut zéro sur un clone
    superficiel, et vaudra zéro pour de bon une fois la purge faite.
    """
    trouves = purge.secrets_de_l_historique()

    assert isinstance(trouves, dict)
    assert all(purge.est_un_secret(v) for v in trouves)
    assert not any(v.startswith("${") for v in trouves)
