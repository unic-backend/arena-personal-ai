"""Configuration du scan de secrets.

Ces tests existent parce que la valeur d'une clé a été réintroduite trois fois
dans le dépôt en une seule journée — à chaque fois par inadvertance, à chaque
fois attrapée par un contrôle et non par une relecture.
"""
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
CONFIG = RACINE / ".gitleaks.toml"


@pytest.fixture(scope="module")
def config() -> dict:
    with CONFIG.open("rb") as f:
        return tomllib.load(f)


def test_la_configuration_est_un_toml_valide(config):
    assert config["title"]


def test_les_regles_par_defaut_de_gitleaks_sont_conservees(config):
    """Nos règles s'ajoutent aux règles standard, elles ne les remplacent pas."""
    assert config["extend"]["useDefault"] is True


def test_les_deux_regles_propres_au_projet_existent(config):
    identifiants = {r["id"] for r in config["rules"]}

    assert "usman-librechat-apikey" in identifiants
    assert "usman-compose-secret" in identifiants


def test_chaque_regle_propre_au_projet_est_documentee(config):
    for regle in config["rules"]:
        assert regle.get("description"), f"la règle {regle['id']} n'explique pas ce qu'elle cherche"
        assert regle.get("secretGroup"), f"la règle {regle['id']} ne désigne pas la valeur à masquer"


def test_les_variables_sensibles_du_projet_sont_toutes_couvertes(config):
    """Les cinq variables qui ont réellement fui doivent être dans la règle."""
    regle = next(r for r in config["rules"] if r["id"] == "usman-compose-secret")

    for variable in [
        "CREDS_KEY", "JWT_SECRET", "JWT_REFRESH_SECRET",
        "WEBUI_SECRET_KEY", "ARENA_API_KEY",
    ]:
        assert variable in regle["regex"], f"{variable} a fui et n'est pas surveillée"


def test_aucun_motif_de_chemin_n_est_ancre_au_debut(config):
    """Un motif ancré par `^` cesse de s'appliquer si la source est un chemin absolu.

    Mesuré le 26/08/2026 : `gitleaks --source /chemin/absolu` produisait alors
    3 faux positifs, et la CI aurait échoué sans raison.
    """
    ancres = [c for c in config["allowlist"]["paths"] if c.startswith("^")]

    assert ancres == [], f"motifs ancrés, fragiles au chemin absolu : {ancres}"


def test_les_fichiers_de_test_sont_exclus_du_scan(config):
    """Ils contiennent des valeurs inventées, de forme secrète, volontairement."""
    chemins = config["allowlist"]["paths"]

    assert any("test_preparer_purge_secrets" in c for c in chemins)
    assert any("env" in c and "example" in c for c in chemins)


def test_la_ci_execute_le_scan():
    workflow = (RACINE / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "gitleaks detect" in workflow
    assert "--config .gitleaks.toml" in workflow


# --- Documents du propriétaire ------------------------------------------------

@pytest.mark.parametrize(
    "chemin",
    [
        "data/documents/devis_2026_041.pdf",
        "data/documents/2026/facture_118.docx",
        "data/rag/storage/index.json",
    ],
)
def test_les_documents_du_proprietaire_ne_peuvent_pas_etre_versionnes(chemin):
    """Le dépôt est public. Un devis client qui y entre n'en ressort pas."""
    # check-ignore n'a de sens que dans un dépôt Git. Un extrait ZIP ou un
    # dossier copié sans .git ne doit pas faire échouer la suite hors ligne.
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=RACINE, capture_output=True, text=True,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        pytest.skip("pas un dépôt git (ex. extrait ZIP) — check-ignore inapplicable")

    resultat = subprocess.run(
        ["git", "check-ignore", "-q", chemin],
        cwd=RACINE, capture_output=True,
    )

    assert resultat.returncode == 0, f"{chemin} n'est pas ignore par git"


def test_le_dossier_des_documents_existe_pour_y_deposer_des_fichiers():
    dossier = RACINE / "data" / "documents"

    assert dossier.is_dir()
    assert (dossier / ".gitkeep").exists(), "le dossier doit survivre a un clone"


# --- Exécution réelle, si le binaire est installé -----------------------------

@pytest.fixture
def gitleaks() -> str:
    chemin = shutil.which("gitleaks")
    if not chemin:
        pytest.skip("gitleaks n'est pas installé sur cette machine.")
    return chemin


@pytest.mark.integration
@pytest.mark.parametrize("source", [".", "absolu"])
def test_aucun_secret_dans_les_fichiers_actuels(gitleaks, source):
    """Les deux formes de chemin doivent donner le même résultat."""
    chemin = str(RACINE) if source == "absolu" else "."
    resultat = subprocess.run(
        [gitleaks, "detect", "--source", chemin, "--no-git",
         "--no-banner", "--redact", "--config", str(CONFIG)],
        capture_output=True, text=True, cwd=RACINE,
    )

    assert resultat.returncode == 0, resultat.stderr[-2000:]


@pytest.mark.integration
def test_un_secret_introduit_est_bien_detecte(gitleaks, tmp_path):
    """Un scan qui ne trouve jamais rien ne prouve rien."""
    # La valeur est assemblée à l'exécution : écrite d'un seul tenant, elle
    # ferait de ce fichier une cible du scanner qu'il est censé tester.
    valeur_piege = "b7f3a91c" + "4e2d8065" + "af13cc9e" + "07b2d418"
    piege = tmp_path / "docker-compose.yml"
    piege.write_text(
        "services:\n  x:\n    environment:\n"
        f"      - CREDS_KEY={valeur_piege}\n",
        encoding="utf-8",
    )

    resultat = subprocess.run(
        [gitleaks, "detect", "--source", str(tmp_path), "--no-git",
         "--no-banner", "--redact", "--config", str(CONFIG)],
        capture_output=True, text=True,
    )

    assert resultat.returncode != 0, "un secret évident n'a pas été détecté"