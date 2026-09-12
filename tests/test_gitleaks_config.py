"""Configuration du scan de secrets.

Ces tests existent parce que la valeur d'une clé a été réintroduite trois fois
dans le dépôt en une seule journée — à chaque fois par inadvertance, à chaque
fois attrapée par un contrôle et non par une relecture.
"""
import re
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


# --- Le nom de la branche de base ---------------------------------------------
#
# Ces deux tests existent a cause d'une panne silencieuse reelle. Le 12/09/2026
# le proprietaire a renomme la branche par defaut `master` -> `main` (les outils
# tiers supposent `main` et repondaient 404 sur son depot public). Le workflow
# ecrivait `master` en dur a quatre endroits : les declencheurs ne tournaient
# plus du tout, et le scan DIFFERENTIEL de secrets tombait dans son repli
# « Pas de branche master a comparer, etape ignoree » — il ne scannait plus
# rien, sans echouer.

def _workflow() -> str:
    return (RACINE / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_la_ci_se_declenche_sur_la_branche_par_defaut():
    import yaml

    declencheurs = yaml.safe_load(_workflow())[True]

    assert "main" in declencheurs["push"]["branches"], (
        "la CI ne tourne plus sur la branche par defaut : aucun check sur main")
    assert "main" in declencheurs["pull_request"]["branches"], (
        "aucun check ne tourne sur une pull request qui vise main")


def test_aucune_branche_de_base_ecrite_en_dur_dans_la_ci():
    """Un nom de branche en dur est exactement ce qui a casse le scan en
    silence. La base se lit sur l'evenement GitHub, jamais dans le texte.

    Le test porte sur le SCRIPT de l'etape et cherche le nom de branche sous
    TOUTES ses formes. Une premiere version ne regardait que `origin/master`
    et `refs/heads/master` : le sabotage `git fetch origin master` (un nom en
    dur passe en ARGUMENT, sans slash) passait a travers. Mesure du
    12/09/2026 — le trou etait dans le test, pas dans le workflow.
    """
    etape = _etape_du_scan_differentiel()
    script = etape["run"]

    for nom in ("master", "main"):
        assert not re.search(rf"\b{nom}\b", script), (
            f"la branche « {nom} » est ecrite en dur dans le script du scan "
            f"differentiel : c'est ce qui l'a fait tomber en silence au "
            f"renommage du 12/09/2026")
    assert "$BASE" in script, "le script doit lire la base dans son environnement"
    assert "github.event.repository.default_branch" in etape["env"]["BASE"], (
        "la base du scan differentiel doit venir de l'evenement GitHub")
    assert "master" not in etape["if"], (
        "la condition de l'etape ne doit pas nommer une branche en dur")


def _etape_du_scan_differentiel() -> dict:
    import yaml

    for etape in yaml.safe_load(_workflow())["jobs"]["secrets"]["steps"]:
        if str(etape.get("name", "")).startswith("No secret added"):
            return etape
    raise AssertionError("l'etape du scan differentiel a disparu du workflow")


def test_le_scan_differentiel_echoue_plutot_que_de_s_ignorer():
    """La regression a ete invisible parce que l'etape se desactivait toute
    seule. Un controle de securite qui se tait n'en est pas un.

    Le test lit le SCRIPT de l'etape, pas le texte du fichier : les
    commentaires du workflow racontent justement cette panne, et un test qui
    cherchait la phrase n'importe ou tombait sur eux.
    """
    script = _etape_du_scan_differentiel()["run"]

    assert "ignoree" not in script, (
        "le scan differentiel a retrouve un repli silencieux")
    assert script.count("::error::") >= 2, (
        "base absente ou introuvable doivent toutes deux echouer bruyamment")
    assert "exit 1" in script


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


def test_les_exceptions_ajoutees_visent_une_valeur_et_pas_un_fichier(config):
    """Une exception large laisserait passer un vrai secret sans qu'on le voie.

    Mesuré le 01/09/2026, quand le budget CI est revenu et que le scan a pu
    tourner : 4 fuites, toutes fausses — deux affectations à une variable
    (`USMAN_API_KEY = CLE_DE_TEST`, `= originale`) et une fixture de 32 hex
    qui sert à prouver que le classificateur repère une clé.

    Ce test ne passe PAS par gitleaks : dans ces fichiers, un secret planté
    est de toute façon rattrapé par les règles génériques, donc un test
    « je plante, il détecte » passerait même avec une exception trop large —
    mesuré aussi, en le sabotant. Il vérifie donc la seule chose qui compte
    ici : que chaque motif ajouté reconnaît la valeur factice **et refuse**
    une vraie affectation de clé.
    """
    regle = next(r for r in config["rules"] if r["id"] == "usman-compose-secret")
    motifs = [re.compile(m) for m in regle["allowlist"]["regexes"]]

    def ecarte(ligne: str) -> bool:
        return any(m.search(ligne) for m in motifs)

    # Les lignes d'exemple sont assemblées à l'exécution, comme le fait déjà
    # `test_un_secret_introduit_est_bien_detecte` plus bas : écrites d'un seul
    # tenant, elles feraient de ce fichier une cible du scanner qu'il teste.
    # Mesuré en les écrivant entières : 5 faux positifs de plus.
    champ = "USMAN_API" + "_KEY"
    hexa = "4409dde4" + "2d4099b9" + "296b5cca" + "987b7c00"

    # Ce qui DOIT être écarté : les faux positifs mesurés.
    assert ecarte(f"{champ} = CLE_DE_TEST")
    assert ecarte(f"{champ} = originale")
    assert ecarte(f'{champ}={hexa}"')

    # Ce qui ne doit JAMAIS l'être : une vraie clé, y compris à faible
    # entropie, et y compris affectée à une variable au nom voisin.
    assert not ecarte(f'{champ} = "arena-cle-de-prod-2026"')
    assert not ecarte(f"{champ}={hexa[:-1]}1"), "une valeur voisine passe aussi"
    assert not ecarte(f'{champ} = "CLE_DE_TEST-mais-vraie-2026"')
