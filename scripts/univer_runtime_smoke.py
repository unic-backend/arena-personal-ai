"""Smoke reel du moteur Office dans l'image finale.

Aucun mock : ce script utilise le binaire `univer` installe dans Docker,
cree un Worktree, ecrit, inspecte, prepare, fusionne, exporte un XLSX,
rend un PDF, ouvre le Viewer local puis arrete son daemon.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from openpyxl import load_workbook


def _run(*args: str, timeout: int = 240) -> dict:
    resultat = subprocess.run(
        ["univer", *args, "--json"],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env={
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", "/tmp"),
            "UNIVER_HOME": os.environ.get("UNIVER_HOME", "/tmp/arena-univer-smoke-home"),
            "UNIVER_RENDER_BROWSER": os.environ.get("UNIVER_RENDER_BROWSER", "/usr/bin/chromium"),
            "NO_COLOR": "1",
            "CI": "1",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        },
    )
    if resultat.returncode != 0:
        raise AssertionError(
            f"univer {' '.join(args[:3])} -> {resultat.returncode}\n"
            f"stdout={resultat.stdout[-2500:]}\nstderr={resultat.stderr[-2500:]}"
        )
    try:
        charge = json.loads(resultat.stdout)
    except json.JSONDecodeError as erreur:
        raise AssertionError(f"Sortie Univer non JSON: {resultat.stdout[-2500:]}") from erreur
    if not isinstance(charge, dict):
        raise AssertionError(f"JSON Univer inattendu: {type(charge).__name__}")
    return charge


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="arena-univer-smoke-") as temp:
        racine = Path(temp)
        os.environ["UNIVER_HOME"] = str(racine / "home")
        fichier = racine / "arena.univer"
        xlsx = racine / "arena.xlsx"
        pdf = racine / "arena.pdf"

        _run("new", str(fichier))
        assert fichier.is_file() and fichier.stat().st_size > 0

        worktree = _run("worktree", "add", str(fichier), "--name", "arena-ci")
        wid = str(worktree.get("worktreeId") or "")
        assert wid

        unite = _run(
            "unit", "add", str(fichier),
            "--worktree", wid, "--type", "sheet", "--name", "Budget",
        )
        uid = str(unite.get("unitId") or "")
        assert uid

        ecriture = _run(
            "execute", str(fichier),
            "--worktree", wid, "--unit", uid, "-e",
            (
                'const s = workbook.getActiveSheet(); '
                's.getRange("A1").setValue("Arena Office"); '
                's.getRange("B1").setValue(42); '
                'return s.getRange("A1:B1").getDisplayValues();'
            ),
        )
        assert ecriture.get("committed") is True
        assert ecriture.get("worktreeId") == wid
        assert ecriture.get("unitId") == uid

        inspecte = _run(
            "inspect", "range", "A1:B1", str(fichier),
            "--worksheet", "name:Sheet1", "--unit", uid, "--worktree", wid,
        )
        assert inspecte["ranges"][0]["displayValues"] == [["Arena Office", "42"]]

        pret = _run("worktree", "ready", str(fichier), "--worktree", wid)
        assert pret.get("status") == "ready" and pret.get("worktreeId") == wid

        fusion = _run("worktree", "merge", str(fichier), "--worktree", wid)
        assert fusion.get("status") == "merged" and fusion.get("worktreeId") == wid

        trunk = _run(
            "inspect", "range", "A1:B1", str(fichier),
            "--worksheet", "name:Sheet1", "--unit", uid, "--trunk",
        )
        assert trunk["ranges"][0]["displayValues"] == [["Arena Office", "42"]]

        _run("export", str(fichier), str(xlsx), "--unit", uid, timeout=300)
        assert xlsx.is_file() and xlsx.stat().st_size > 0
        classeur = load_workbook(xlsx, read_only=True, data_only=False)
        try:
            feuille = classeur.active
            assert feuille["A1"].value == "Arena Office"
            assert feuille["B1"].value == 42
        finally:
            classeur.close()

        _run("print-pdf", str(fichier), str(pdf), "--unit", uid, timeout=300)
        assert pdf.is_file() and pdf.stat().st_size > 100
        assert pdf.read_bytes()[:5] == b"%PDF-"

        ouvert = _run("open", str(fichier), "--unit", uid, timeout=180)
        url = str(ouvert.get("openUrl") or "")
        assert url.startswith("http://127.0.0.1:")
        with urllib.request.urlopen(url, timeout=20) as reponse:
            html = reponse.read().decode("utf-8", errors="replace")
            assert reponse.status == 200
            assert '<div id="app"></div>' in html

        arret = _run("daemon", "stop", timeout=30)
        assert isinstance(arret, dict)

        print(
            "UNIVER_RUNTIME_SMOKE_OK",
            f"univer={fichier.stat().st_size}",
            f"xlsx={xlsx.stat().st_size}",
            f"pdf={pdf.stat().st_size}",
        )


if __name__ == "__main__":
    main()
