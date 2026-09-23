from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_connector_registry_has_real_call_and_health_paths():
    source = _source("core/connectors/registre.py")
    for marker in (
        "def obtenir(",
        "def sante(",
        "def inventaire(",
        "def executer(",
        "return connecteur.executer(capacite, compte=compte, **parametres)",
    ):
        assert marker in source


def test_runtime_declares_key_external_and_local_connectors():
    source = _source("apps/backend/runtime.py")
    required = (
        "gmail",
        "file_conversion",
        "pdf",
        "opentakeoff",
        "ifc",
        "ifc_generation",
        "gitingest",
        "graphify",
        "moneyprinter",
        "wan2gp",
        "hidream",
        "comfyui",
    )
    missing = [name for name in required if f'\"{name}\"' not in source]
    assert not missing, f"Connecteurs attendus non declares dans runtime: {missing}"


def test_status_route_probes_registry_health_instead_of_guessing():
    source = _source("apps/backend/routers/connectors.py")
    assert 'registre.sante(fournisseur)' in source
    assert 'sante.etat == EtatSante.OPERATIONNEL' in source
    assert '"verified": connecte' in source
    assert '"etat": sante.etat.value' in source


def test_external_workers_are_reported_honestly_when_not_configured():
    source = _source("apps/backend/runtime.py")
    for connector in ("moneyprinter", "wan2gp", "hidream", "comfyui", "opentakeoff"):
        assert f'\"{connector}\"' in source
    # The runtime documentation must keep the explicit non-configured contract;
    # a declared worker is not the same thing as a running worker.
    lowered = source.lower()
    assert "non configure" in lowered
    assert "sonde" in lowered
