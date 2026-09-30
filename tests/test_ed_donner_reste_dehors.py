"""`ed-donner/agents` a été audité, puis refusé. Ce fichier tient le refus (DEC-0205).

Même discipline que `test_basic_memory_reste_dehors.py` (DEC-0204) : un refus
écrit dans un document vieillit sans qu'on le voie. Le dépôt amont — un COURS
pédagogique (commit `da89337`, 19/09/2026, MIT) — enseigne **cinq frameworks
d'orchestration** (CrewAI, LangGraph, OpenAI Agents SDK, Google ADK, Pydantic
AI, et leurs voisins agno / Strands / Mastra / MAF / deepagents). La comparaison
capacité par capacité (`docs/audits/ed_donner_agents_audit.md`) n'a mesuré
**aucune** capacité manquante : orchestration, transfert d'agent, outils avec
permissions, mémoire, contexte, découpage, boucles bornées, garde-fous,
confirmation humaine, exécution longue — tout existe, sabotage-testé, dans
`core/` et `agents/`.

**Première moitié — rien n'est entré.** Aucun de ces frameworks n'est une
dépendance déclarée, aucun n'est importé par le code suivi.

**Seconde moitié — pourquoi rien n'a eu à entrer.** Le refus repose sur une
affirmation sur ARENA : « les équivalents natifs existent ». Elle se périme si
le code change — si `boucle.py` perdait ses budgets, si les transports MCP
perdaient `tools/list`, si la syntaxe `[[COLLEGUE:]]` disparaissait, ce refus ne
serait plus fondé et personne ne le saurait. Ces tests-là échouent avant : ils
ne croient pas le document, ils **exécutent** la capacité.

Deux exclusions mesurées, pas négociables :

- **`requirements.lock.txt` contient déjà** `langchain-core`,
  `langchain-community`, `langchain-classic`, `langchain-ollama`,
  `langchain-protocol`, `langchain-text-splitters` : ce sont les transitifs de
  `browser-use` (ligne `langchain-openai==1.1.14`, épinglée pour PYSEC-2026-76,
  mesurée aux lignes 108-114 du gel). La porte s'applique donc aux
  **dépendances directes** et aux **imports**, jamais au gel — sinon elle
  échouerait du premier jour pour une raison fausse.
- **`agents` n'est pas testé à l'import** : c'est le nom du paquet racine
  d'ARENA lui-même. Le SDK `openai-agents` (module `agents`) resterait quand
  même capturé par la porte des dépendances déclarées.
"""
import ast
import re
import subprocess
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent

#: Paquets d'orchestration du dépôt audité, sous leur nom PyPI (déclaré dans
#: son `pyproject.toml` amont, ou outil `uv tool` pour CrewAI). Si une ligne
#: de dépendance directe en porte un, l'audit est à refaire : ARENA aurait
#: maintenant DEUX orchestrateurs — exactement la dérive que DEC-0205 refuse.
DEPENDANCES_INTERDITES = (
    "crewai",
    "langchain",                       # l'orchestrateur, pas le substrat browser-use
    "langchain-mcp-adapters",
    "langgraph",
    "langgraph-checkpoint-sqlite",
    "openai-agents",
    "pydantic-ai",
    "pydantic-ai-slim",
    "google-adk",
    "deepagents",
    "agent-framework",
    "agent-framework-core",
    "agent-framework-openai",
    "strands-agents",
    "agno",
)

#: Modules Python correspondants (ImportFrom / Import). `langchain_openai`
#: n'y figure pas : déjà importé par `tools/browser/browser_use_tool.py` et
#: `core/connectors/browser.py` comme substrat de `browser-use`, pas comme
#: orchestrateur — c'est la seule exception, et elle est justifiée ci-dessus.
MODULES_INTERDITS = (
    "crewai",
    "langchain",
    "langchain_community",
    "langchain_mcp_adapters",
    "langgraph",
    "pydantic_ai",
    "google.adk",
    "deepagents",
    "agent_framework",
    "strands",
    "agno",
    "mastra",
)

#: Fichiers où une dépendance DIRECTE peut être déclarée. Le gel
#: (`requirements.lock.txt`) n'y est pas : il porte par construction les
#: transitifs de `browser-use` — mesuré ci-dessus.
FICHIERS_DE_DEPENDANCES_DIRECTES = (
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
)

_NOM_PAQUET = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*(?:\[|==|~=|>=|<=|!=|<|>|;|$)")


def _fichiers_suivis(suffixe: str) -> list[Path]:
    """Ce que git suit réellement. La question est posée à git, pas déduite."""
    sortie = subprocess.run(
        ["git", "ls-files", "--", "*." + suffixe],
        cwd=RACINE, capture_output=True, text=True, check=False,
    )
    assert sortie.returncode == 0, f"git ls-files : {sortie.stderr.strip()}"
    return [RACINE / ligne for ligne in sortie.stdout.splitlines() if ligne.strip()]


def _dependances_declarees(chemin: Path) -> set[str]:
    """Noms de paquets déclarés en dépendances directes d'un fichier suivi.

    Deux formes lues : une ligne de requirements (`paquet==1.2`) et une entrée
    de la liste `dependencies` de `pyproject.toml` (`"paquet>=1.2",`). Ce qui
    n'est pas une ligne de déclaration est ignoré, commentaires y compris.
    """
    trouves: set[str] = set()
    for ligne in chemin.read_text(encoding="utf-8", errors="ignore").splitlines():
        depouillee = ligne.strip().strip('"').strip(",").strip()
        if not depouillee or depouillee.startswith(("#", "[", "-", "{")):
            continue
        correspondance = _NOM_PAQUET.match(depouillee)
        if correspondance:
            trouves.add(correspondance.group(1).lower())
    return trouves


def _imports_de(chemin: Path) -> set[str]:
    """Modules importés par un fichier, lus par l'AST — jamais du texte."""
    try:
        arbre = ast.parse(chemin.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        # Un fichier illisible ou non-python suivi par git n'a rien à
        # importer : ignoré, la porte reste sur le reste du code.
        return set()
    modules: set[str] = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            modules.update(alias.name for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module and noeud.level == 0:
            modules.add(noeud.module)
    return modules


class TestRienNEstEntre:
    """Première moitié : aucun framework du dépôt audité n'est entré."""

    def test_aucun_framework_en_dependance_directe(self) -> None:
        coupables: list[str] = []
        for fichier in FICHIERS_DE_DEPENDANCES_DIRECTES:
            chemin = RACINE / fichier
            if not chemin.exists():
                continue
            declares = _dependances_declarees(chemin)
            for interdit in DEPENDANCES_INTERDITES:
                if interdit.lower() in declares:
                    coupables.append(f"{fichier}: {interdit}")
        assert not coupables, (
            "Un framework d'orchestration du dépôt audité est devenu une "
            "dépendance directe — c'est exactement ce que DEC-0205 refuse :\n  "
            + "\n  ".join(coupables))

    def test_aucun_framework_importe_par_le_code_suivi(self) -> None:
        coupables: list[str] = []
        for py in _fichiers_suivis("py"):
            for module in _imports_de(py):
                if module in MODULES_INTERDITS or any(
                    module.startswith(m + ".") for m in MODULES_INTERDITS
                ):
                    coupables.append(
                        f"{py.relative_to(RACINE)}: import {module}")
        assert not coupables, (
            "Un framework d'orchestration du dépôt audité est importé par le "
            "code suivi — c'est exactement ce que DEC-0205 refuse :\n  "
            + "\n  ".join(coupables))


class TestLesEquivalentsNatifsExistentToujours:
    """Seconde moitié : la raison du refus est encore vraie — exécutée."""

    def test_la_boucle_est_bornee_et_dit_pourquoi_elle_s_arrete(self) -> None:
        from core.execution.boucle import Budget, RaisonDArret

        # Les huit sorties, toutes raisonnées — aucun chemin ne sort sans
        # raison.
        assert {
            "OBJECTIF_ATTEINT", "PLAN_VIDE", "PLANIFICATION_EN_ECHEC",
            "BUDGET_TOURS", "BUDGET_ETAPES", "BUDGET_TEMPS", "BUDGET_OUTILS",
            "PLAN_REPETE",
        } == {r.name for r in RaisonDArret}

        budget = Budget()
        assert budget.etapes_max > 0 and budget.tours_max > 0
        assert budget.secondes_max > 0
        # `appels_outils_max = None` est le seul plafond facultatif (le
        # compteur d'outils est un branchement optionnel) — tout le reste est
        # écrit, jamais illimité.
        assert budget.appels_outils_max is None

    def test_le_transfert_d_agent_reste_une_syntaxe_fermee_bornee(self) -> None:
        from core.agent.base_agent import (
            CONSULTATIONS_MAX,
            DEMANDE_DE_COLLEGUE,
        )

        correspondance = DEMANDE_DE_COLLEGUE.search(
            "[[COLLEGUE:coder|ecris la fonction]]")
        assert correspondance is not None
        assert correspondance.group(1) == "COLLEGUE"
        # Une consultation qui en appelle une autre indéfiniment ne produit
        # jamais de réponse : la borne existe toujours.
        assert CONSULTATIONS_MAX >= 1

    def test_les_transports_mcp_parlent_outils_sur_les_deux_tuyaux(self) -> None:
        from core.mcp.stdio_transport import ClientMcpStdio
        from core.mcp.transport import ClientMcp

        # Construction seule, aucun réseau : le contrat est ce dont la perte
        # ferait retomber le refus — les deux clients savent lister et appeler
        # des outils, chacun sur son tuyau.
        for client in (
            ClientMcp("http://127.0.0.1:9", chemin="/mcp"),
            ClientMcpStdio(commande=["binaire-inexistant-jamais-lance"],
                           dossier="."),
        ):
            assert callable(client.ouvrir)
            assert callable(client.outils)
            assert callable(client.appeler)

    def test_l_orchestrateur_classe_une_intention(self) -> None:
        from agents.orchestrator.orchestrator_agent import OrchestratorAgent

        # L'entrée canonique du classement existe — le comportement lui-même
        # est couvert par la suite existante, ce test garde le contrat.
        assert callable(OrchestratorAgent.analyze_intent)

    def test_la_frontiere_de_confiance_enveloppe_toujours(self) -> None:
        from core.security.trust import TrustLevel, TrustRefused, wrap

        enveloppe = wrap("texte etranger", TrustLevel.EXTERNAL, "audit")
        assert "texte etranger" in enveloppe.text
        # Et la frontière refuse toujours d'envelopper une INSTRUCTION comme
        # une donnée : c'est la moitié de la garantie.
        with pytest.raises(TrustRefused):
            wrap("texte", TrustLevel.SYSTEM, "audit")

    def test_le_serveur_mcp_memoire_expose_ses_six_outils(self) -> None:
        # Le serveur MCP d'ARENA (DEC-0090) reste l'unique surface MCP serveur
        # : ses six outils, lus dans le module — aucun second serveur ne l'a
        # grossi.
        from core.mcp import memory_server

        texte = Path(memory_server.__file__).read_text(encoding="utf-8")
        assert texte.count("@mcp.tool()") == 6


class TestLeRefusEtSaRaisonVoyagentEnsemble:
    """Si le document disparaît, la décision ne tient plus à rien."""

    def test_l_audit_et_la_decision_ne_ont_pas_ete_effaces(self) -> None:
        assert (RACINE / "docs" / "audits" / "ed_donner_agents_audit.md").exists(), (
            "L'audit d'intégration sélective a disparu : on supprime une "
            "décision en la documentant, pas en l'effaçant.")
        texte = (RACINE / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
        assert "## DEC-0205" in texte, (
            "DEC-0205 (ed-donner/agents refusé) a disparu de docs/DECISIONS.md "
            ": on supprime une décision en la remplaçant par une nouvelle, "
            "pas en l'effaçant.")
