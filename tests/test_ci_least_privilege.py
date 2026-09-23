from pathlib import Path

import yaml


WORKFLOW = Path(".github/workflows/ci.yml")


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_ci_declares_explicit_least_privilege_permissions() -> None:
    """CI must not inherit repository-default write permissions."""
    data = _workflow()
    assert data.get("permissions") == {"contents": "read"}


def test_no_job_escalates_github_token_permissions() -> None:
    """A future job must not silently widen the workflow trust boundary."""
    data = _workflow()
    for name, job in data.get("jobs", {}).items():
        assert "permissions" not in job, f"job {name!r} overrides least-privilege permissions"
