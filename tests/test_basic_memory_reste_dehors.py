"""Basic Memory a été audité, puis refusé. Ce fichier tient le refus (DEC-0203).

Un refus écrit dans un document vieillit sans qu'on le voie : six mois plus
tard, quelqu'un trouve le projet, ne trouve pas la raison, et l'installe. Ce
test mesure les deux moitiés de la décision — celle qui interdit, et celle sur
laquelle l'interdiction **repose**.

**Première moitié — rien n'est entré.** Aucune dépendance, aucun import, aucun
fichier. Trois blocages indépendants la justifient (audit complet →
`docs/audits/basic_memory_audit.md`) :

1. **AGPL-3.0-or-later** contre le `LICENSE` « tous droits réservés » d'un dépôt
   PUBLIC — même règle que DEC-0200 (Edit-Banana) et DEC-0202 (Netronome), déjà
   tenue par `tests/test_moteurs_externes_restent_dehors.py`. Sa clôture
   d'exécution porte en plus du GPL-2.0+ (`unidecode`) et du LGPL-3.0
   (`psycopg`), mesurés sur PyPI le 30/09/2026.
2. **`requires-python = ">=3.12"`** alors qu'ARENA tourne en 3.11 (CI et
   Dockerfile). Mesuré : `pip install --dry-run basic-memory` sous 3.11.2 rend
   « No matching distribution found », pour **toutes** les versions publiées.
3. **Ce serait une seconde mémoire**, pas une meilleure : Markdown, wikiliens,
   graphe, recherche hybride, projets et outils MCP de mémoire existent déjà.

**Seconde moitié, et c'est elle qui compte — pourquoi il n'entre pas.** Le
blocage 3 est le seul qui resterait si les deux autres tombaient, et c'est une
affirmation sur ARENA, pas sur l'amont : « nous avons déjà tout ça ». Une
affirmation sur du code se périme quand le code change. Si le Knowledge Vault
perdait son graphe, si la recherche hybride cessait de dire son repli, si le
serveur MCP de mémoire disparaissait, si l'isolation de projet fuyait — alors le
refus ne serait plus fondé, et personne ne le saurait. Ces tests-là échouent
avant.

Ils ne mesurent donc pas « le document dit la bonne chose ». Ils mesurent la
**capacité réelle**, en l'exécutant.
"""
import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent

#: Les deux orthographes : celle de PyPI et celle du paquet Python.
NOMS = ("basic-memory", "basic_memory")

#: Ce que le propriétaire installe, et qui ne doit pas se retrouver épinglé ici.
FICHIERS_DE_DEPENDANCES = (
    "requirements.txt",
    "requirements-dev.txt",
    "requirements.lock.txt",
    "pyproject.toml",
)


def _fichiers_suivis() -> list[str]:
    """Ce que git suit réellement. La question est posée à git, pas déduite."""
    return subprocess.run(
        ["git", "ls-files"], cwd=RACINE, capture_output=True, text=True, check=False,
    ).stdout.splitlines()


# --- Première moitié : rien n'est entré ---------------------------------------


@pytest.mark.parametrize("fichier", FICHIERS_DE_DEPENDANCES)
def test_aucune_dependance_basic_memory_declaree(fichier):
    """§18 de la mission : pas d'ajout aveugle. Et ici, pas d'ajout du tout.

    Le commentaire d'un fichier de dépendances peut parfaitement CITER le nom
    (c'est même souhaitable : une ligne qui dit pourquoi une dépendance n'est
    pas là se relit). On ne refuse donc que les lignes qui DÉCLARENT.
    """
    chemin = RACINE / fichier
    if not chemin.exists():
        pytest.skip(f"{fichier} absent")

    for numero, ligne in enumerate(chemin.read_text(encoding="utf-8").splitlines(), 1):
        nue = ligne.strip()
        if not nue or nue.startswith("#"):
            continue
        assert not any(nom in nue.lower() for nom in NOMS), (
            f"{fichier}:{numero} déclare basic-memory : {nue!r}. "
            "AGPL-3.0-or-later sur un dépôt « tous droits réservés », et "
            "requires-python >= 3.12 quand ARENA tourne en 3.11. Voir DEC-0203."
        )


def test_aucun_module_arena_n_importe_basic_memory():
    """Mesuré sur l'AST, pas sur une recherche de texte.

    Une recherche de texte confondrait l'import réel avec la prose d'un
    commentaire ou d'un docstring — c'est-à-dire avec ce fichier-ci, et avec
    l'audit. L'AST, lui, ne voit que les imports.
    """
    coupables = []
    for relatif in _fichiers_suivis():
        if not relatif.endswith(".py"):
            continue
        chemin = RACINE / relatif
        try:
            arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=relatif)
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue  # un fichier illisible est le problème d'un autre test
        for noeud in ast.walk(arbre):
            modules = []
            if isinstance(noeud, ast.Import):
                modules = [alias.name for alias in noeud.names]
            elif isinstance(noeud, ast.ImportFrom):
                modules = [noeud.module or ""]
            for module in modules:
                if module == "basic_memory" or module.startswith("basic_memory."):
                    coupables.append(f"{relatif}:{noeud.lineno} → {module}")

    assert coupables == [], (
        "ARENA importe du code AGPL-3.0 : " + ", ".join(coupables) + ". Voir DEC-0203."
    )


def test_aucun_fichier_de_basic_memory_nest_versionne():
    """Une règle d'ignore n'a aucun effet sur un fichier déjà suivi.

    C'est le seul cas où un `.gitignore` donne une fausse assurance, et c'est
    pour ça que la question est posée à `git ls-files` et pas au `.gitignore`.
    """
    autorises = ("docs/audits/", "docs/DECISIONS.md", "PROJECT_MEMORY/", "tests/")
    dedans = [
        f for f in _fichiers_suivis()
        if any(nom in f.lower() for nom in NOMS) and not f.startswith(autorises)
    ]
    assert dedans == [], f"du contenu de Basic Memory est versionné : {dedans}"


def test_la_raison_du_refus_est_ecrite_et_nommee():
    """Une interdiction sans sa raison se fait lever par le prochain pressé.

    Les trois blocages doivent rester nommés : celui qui les lit doit pouvoir
    vérifier LEQUEL est tombé avant de rouvrir la décision. Un seul suffit à
    maintenir le refus, donc les trois doivent être lisibles séparément.
    """
    audit = (RACINE / "docs" / "audits" / "basic_memory_audit.md")
    assert audit.exists(), "l'audit qui fonde DEC-0203 a disparu"
    texte = audit.read_text(encoding="utf-8").lower()

    for marqueur, ce_que_c_est in (
        ("agpl-3.0", "le blocage de licence"),
        (">=3.12", "le blocage de version de Python"),
        ("seconde mémoire", "le blocage architectural"),
        ("unknown — non mesuré", "l'absence de mesure de performance"),
    ):
        assert marqueur in texte, f"l'audit ne porte plus {ce_que_c_est} ({marqueur!r})"

    decisions = (RACINE / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
    assert "## DEC-0203" in decisions, "DEC-0203 a disparu du registre"


def test_aucun_chiffre_de_performance_n_est_revendique():
    """§12 : « Do not claim performance improvements without measurements. »

    Rien n'a été mesuré — ni latence, ni indexation, ni disque, ni concurrence.
    Ce test ne cherche donc pas les mots « plus rapide » : la phrase qui compte
    dans l'audit est justement celle qui les NIE (« elle ne dit pas qu'ARENA est
    plus rapide »), et un motif qui ne sait pas distinguer une affirmation de
    son démenti ne mesure rien. Il cherche ce qu'un démenti ne peut pas
    produire : **un chiffre**. « 3x plus rapide », « 40 % de latence en moins »,
    « 200 ms » — aucun de ces énoncés n'existe sans banc d'essai.

    L'autre moitié de la garantie (la présence de `UNKNOWN — non mesuré`) est
    tenue par `test_la_raison_du_refus_est_ecrite_et_nommee`.
    """
    texte = (RACINE / "docs" / "audits" / "basic_memory_audit.md").read_text(
        encoding="utf-8"
    ).lower()
    motifs = (
        r"\d+\s*(?:x|fois)\s+plus\s+(?:rapide|lent|l[ée]ger)",
        r"\d+\s*%\s*(?:de\s+)?(?:plus|moins|gain|latence)",
        r"\d+\s*(?:ms|millisecondes?)\b",
    )
    for motif in motifs:
        trouve = re.search(motif, texte)
        assert trouve is None, (
            f"l'audit chiffre une performance jamais mesurée : {trouve.group(0)!r}"
        )


# --- Seconde moitié : ce sur quoi le refus repose tient toujours ---------------


def test_le_knowledge_vault_fait_bien_ce_que_basic_memory_promet(tmp_path):
    """Markdown ingéré, wikiliens résolus, graphe construit, liens cassés vus.

    C'est la ligne « nous avons déjà ça » du blocage 3, exécutée. Si elle
    échoue, ARENA n'a plus de couche documentaire et DEC-0203 n'est plus fondée.
    """
    from core.knowledge.vault import KnowledgeVault

    vault = KnowledgeVault(tmp_path / "vault")
    vault.initialize()

    source = tmp_path / "tarif.md"
    source.write_text(
        "# Tarif de pose\n\nLe tarif de pose BA13 est 5000 F/m2 a Dakar.\n"
        "Voir [[Chantier Medina]].\n",
        encoding="utf-8",
    )
    resultat = vault.ingest(source, title="Tarif de pose")
    assert resultat["status"] == "INGESTED"
    assert resultat["sha256"], "la source brute n'est plus empreintée"

    graphe = vault.graph()
    assert len(graphe["nodes"]) >= 2, "le graphe de wikiliens a disparu"
    assert len(graphe["edges"]) >= 1, "les wikiliens ne font plus d'arêtes"
    assert len(graphe["broken_links"]) >= 1, (
        "un wikilien vers une page absente n'est plus signalé"
    )

    trouves = vault.search("tarif pose BA13")
    assert trouves, "BM25 ne retrouve plus une note qu'il vient d'ingérer"
    assert trouves[0].mode == "BM25"

    rapport = vault.lint()
    assert rapport.broken_links, "le lint ne voit plus un lien cassé"


async def test_la_recherche_hybride_dit_son_repli_au_lieu_de_le_taire():
    """Sans embeddings, le mode rendu est « BM25 » — jamais un faux sémantique.

    Basic Memory est vendu sur la recherche sémantique. ARENA l'a, avec en plus
    la règle qui compte : une capacité absente se RAPPORTE. Si ce test tombe,
    ARENA s'est mise à prétendre, et l'argument du blocage 3 s'effondre avec.
    """
    import tempfile

    from core.knowledge.vault import KnowledgeVault

    with tempfile.TemporaryDirectory() as dossier:
        vault = KnowledgeVault(Path(dossier) / "vault")
        vault.initialize()
        source = Path(dossier) / "note.md"
        source.write_text("# Pose\n\nLa pose de cloison BA13 se facture au m2.\n",
                          encoding="utf-8")
        vault.ingest(source, title="Pose")

        async def aucun_vecteur(textes):
            return []  # serveur d'embeddings absent, comme hors de sa machine

        resultats = await vault.hybrid_search(
            "combien coute la pose", limit=3, embedder=aucun_vecteur
        )

    assert resultats, "le repli lexical ne rend plus rien"
    assert all(hit.mode == "BM25" for hit in resultats), (
        "un classement sémantique est annoncé sans embeddings"
    )


def test_la_memoire_personnelle_isole_toujours_les_projets(tmp_path):
    """§9 : une question sur un projet ne ramène jamais un autre projet.

    Basic Memory, lui, retombe sur `default_project` quand le paramètre manque
    (`config_models.py` : « acts as fallback when no project parameter is
    specified »). ARENA filtre en SQL et n'a pas de projet par défaut. Ce test
    est la moitié ARENA de cette comparaison.
    """
    from core.memory.personnelle import MemoirePersonnelle, Nature, TypeSouvenir
    from core.memory.recuperation import recuperer

    memoire = MemoirePersonnelle(db_path=str(tmp_path / "memoire.db"))
    memoire.retenir(contenu="18 parois posees pour Fast Group.",
                    type=TypeSouvenir.EPISODIQUE, nature=Nature.FAIT,
                    source="proprietaire", projet="Fast Group")
    memoire.retenir(contenu="18 parois posees a Medina.",
                    type=TypeSouvenir.EPISODIQUE, nature=Nature.FAIT,
                    source="proprietaire", projet="Medina")

    medina = [r.souvenir.contenu for r in recuperer(memoire, "parois", projet="Medina")]
    assert medina == ["18 parois posees a Medina."], (
        f"fuite entre projets : une question sur Medina rend {medina}"
    )

    fast = [r.souvenir.contenu for r in recuperer(memoire, "parois", projet="Fast Group")]
    assert fast == ["18 parois posees pour Fast Group."]


def test_le_serveur_mcp_de_memoire_existe_toujours(tmp_path, monkeypatch):
    """Six outils MCP de mémoire (DEC-0090) : c'est déjà la surface que Basic
    Memory aurait apportée, et elle est gouvernée — voir le test suivant.
    """
    import importlib

    monkeypatch.setenv("USMAN_MEMORY_DB_PATH", str(tmp_path / "memoire.db"))
    monkeypatch.delenv("USMAN_MEMORY_VAULT_PASSPHRASE", raising=False)
    module = importlib.import_module("core.mcp.memory_server")
    importlib.reload(module)
    try:
        for outil in ("search_memory", "create_memory", "list_memory",
                      "approve_memory", "reject_memory", "delete_memory"):
            assert callable(getattr(module, outil, None)), (
                f"l'outil MCP {outil} a disparu : ARENA n'expose plus sa mémoire"
            )
    finally:
        module._memoire = None


def test_un_client_mcp_externe_ne_peut_pas_fabriquer_un_fait(tmp_path, monkeypatch):
    """Ce que Basic Memory n'a pas : une écriture externe reste une INFERENCE.

    C'est la garantie qui interdisait l'option B de l'audit — router la mémoire
    vers un système sans distinction FAIT / INFERENCE la ferait disparaître en
    silence.
    """
    import importlib

    monkeypatch.setenv("USMAN_MEMORY_DB_PATH", str(tmp_path / "memoire.db"))
    monkeypatch.delenv("USMAN_MEMORY_VAULT_PASSPHRASE", raising=False)
    module = importlib.import_module("core.mcp.memory_server")
    importlib.reload(module)
    try:
        cree = module.create_memory(contenu="Le tarif est 9000 F/m2.", type="semantic",
                                    source="un-client-mcp-quelconque")
        assert cree["nature"] == "INFERENCE", (
            "un client MCP externe écrit directement un FAIT"
        )
    finally:
        module._memoire = None


def test_un_secret_ne_peut_pas_entrer_en_memoire(tmp_path):
    """Ce que Basic Memory n'a pas non plus, et §10 l'exige.

    Le motif vient de `scripts/scanner_secrets.py` — la même liste qui protège
    un commit, jamais une seconde inventée pour l'occasion.
    """
    from core.memory.personnelle import MemoirePersonnelle, Nature, TypeSouvenir

    memoire = MemoirePersonnelle(db_path=str(tmp_path / "memoire.db"))
    # Assemble à l'exécution, jamais écrit d'un seul tenant : la VALEUR a la
    # forme d'un jeton GitHub (c'est le but — `retenir()` doit la refuser),
    # mais le FICHIER n'en contient aucun, donc aucun scanner statique n'a de
    # raison de s'en alarmer. Le test resterait vrai sans cette précaution ;
    # le scan de secrets de la CI, lui, ne le saurait pas.
    jeton_factice = "gh" + "p_" + ("A1b2C3d4E5f6G7h8I9j0" "K1l2M3n4O5p6Q7r8")

    with pytest.raises(ValueError):
        memoire.retenir(contenu=f"Le jeton est {jeton_factice}",
                        type=TypeSouvenir.SEMANTIQUE, nature=Nature.FAIT,
                        source="proprietaire")

    assert memoire.souvenirs() == [], "un secret a été écrit malgré le refus"


def test_arena_tourne_bien_sur_une_version_que_basic_memory_refuse():
    """Le blocage 2, mesuré ici plutôt que recopié.

    `requires-python = ">=3.12"` chez l'amont. Ce test ne fige pas 3.11 comme
    un objectif : il fige le fait que **la CI et l'image décident ensemble**.
    Le jour où les deux passent en 3.12, il le dit — et c'est précisément le
    moment où ce blocage-là tombe et où DEC-0203 doit être relue.
    """
    ci = (RACINE / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    dockerfile = (RACINE / "apps" / "backend" / "Dockerfile").read_text(encoding="utf-8")

    versions_ci = set(re.findall(r'python-version:\s*"(3\.\d+)"', ci))
    version_image = re.search(r"FROM python:(3\.\d+)", dockerfile)

    assert versions_ci, "la CI ne fixe plus aucune version de Python"
    assert version_image, "l'image ne fixe plus de version de Python"

    if version_image.group(1) != "3.11" or "3.11" not in versions_ci:
        pytest.fail(
            "ARENA ne tourne plus en 3.11 (CI "
            f"{sorted(versions_ci)}, image {version_image.group(1)}) : le "
            "blocage 2 de DEC-0203 est peut-être tombé, relire l'audit "
            "avant de conclure quoi que ce soit."
        )

    assert sys.version_info[:2] >= (3, 11)
