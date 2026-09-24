"""`Real connector validation` (`.github/workflows/real-connectors.yml`) —
mesuré le 24/09/2026 en panne silencieuse depuis sa création.

`tests/integration/test_real_connectors.py` porte `pytestmark = pytest.mark.
integration`. `pyproject.toml` exclut ce marqueur par défaut
(`addopts = "-m 'not integration'"`) — c'est la règle qui garde `pytest` vert
hors ligne. Le workflow programmé lançait `pytest tests/integration/ -q -ra`
sans jamais la lever : les quatre tests étaient déselectionnés avant de
pouvoir s'exécuter, `pytest` rendait le code 5 (« aucun test collecté »), et
GitHub Actions marquait la tâche planifiée en échec chaque nuit — sans jamais
avoir réellement interrogé Gmail, l'agenda, GitHub ou Agent Reach.

Reproduit avant correction :

    RUN_REAL_INTEGRATION=1 pytest tests/integration/ -q -ra
    → 4 deselected, code de sortie 5

Après correction (`-m integration` ajouté à la commande) :

    RUN_REAL_INTEGRATION=1 pytest tests/integration/ -q -ra -m integration
    → 4 skipped (identifiants absents ici), code de sortie 0
"""
from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/real-connectors.yml")


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _commande_des_sondes() -> str:
    data = _workflow()
    jobs = data.get("jobs", {})
    job = jobs["real-connectors"]
    etapes = job["steps"]
    sonde = next(e for e in etapes if e.get("name") == "Real connector probes (read-only)")
    return sonde["run"]


def test_la_commande_leve_le_marqueur_integration_exclu_par_defaut() -> None:
    """Sans `-m integration`, `addopts = "-m 'not integration'"`
    (pyproject.toml) déselectionne les quatre tests avant qu'ils ne tournent
    — mesuré : `pytest` rend alors le code 5, jamais un vrai résultat."""
    commande = _commande_des_sondes()
    assert "pytest" in commande
    assert "tests/integration" in commande
    assert "-m integration" in commande or "-m 'integration'" in commande or '-m "integration"' in commande


def test_le_marqueur_integration_existe_bien_dans_la_config_du_depot() -> None:
    """Le marqueur que la commande lève doit être celui que pyproject.toml
    exclut par défaut — sinon la commande lève un marqueur qui n'exclut
    rien, et le silence reviendrait sous une autre forme."""
    racine = Path(__file__).resolve().parent.parent
    config = (racine / "pyproject.toml").read_text(encoding="utf-8")
    assert "addopts" in config
    assert "not integration" in config


def test_le_workflow_programme_reste_declenchable_a_la_demande() -> None:
    """Un test rouge chaque nuit qu'on ne regarde jamais est pire qu'aucun
    test — `workflow_dispatch` doit rester pour le relancer après un
    correctif, sans attendre 3h17 du matin."""
    data = _workflow()
    assert "workflow_dispatch" in data.get("on", {}) or "workflow_dispatch" in data.get(True, {})
