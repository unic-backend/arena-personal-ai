import subprocess
from pathlib import Path

from typer.testing import CliRunner

from scripts import arena_cli

runner = CliRunner()


def _fake_run(calls, returncode=0):
    def run(argv, cwd, check):
        calls.append((argv, cwd, check))
        return subprocess.CompletedProcess(argv, returncode)
    return run


def test_doctor_invoque_le_script_canonique(monkeypatch):
    calls = []
    monkeypatch.setattr(arena_cli.subprocess, "run", _fake_run(calls))

    result = runner.invoke(arena_cli.app, ["doctor"])

    assert result.exit_code == 0
    assert calls == [
        ([arena_cli.sys.executable, str(arena_cli.RACINE / "scripts" / "doctor.py")],
         arena_cli.RACINE, False)
    ]


def test_audit_orphans_est_reellement_joignable(monkeypatch):
    calls = []
    monkeypatch.setattr(arena_cli.subprocess, "run", _fake_run(calls))

    result = runner.invoke(arena_cli.app, ["audit", "orphans"])

    assert result.exit_code == 0
    assert calls[0][0][-1].endswith("orphelins.py")


def test_performance_transmet_iterations(monkeypatch):
    calls = []
    monkeypatch.setattr(arena_cli.subprocess, "run", _fake_run(calls))

    result = runner.invoke(arena_cli.app, ["performance", "--iterations", "7"])

    assert result.exit_code == 0
    assert calls[0][0][-2:] == ["--iterations", "7"]


def test_code_echec_du_script_est_propage(monkeypatch):
    monkeypatch.setattr(arena_cli.subprocess, "run", _fake_run([], returncode=9))

    result = runner.invoke(arena_cli.app, ["doctor"])

    assert result.exit_code == 9


def test_script_absent_echoue_explicitement(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(arena_cli, "RACINE", tmp_path)

    result = runner.invoke(arena_cli.app, ["doctor"])

    assert result.exit_code == 2
    assert "introuvable" in result.stderr
