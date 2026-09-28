"""Smoke runtime réel du moteur Office Univer dans l'image finale.

Ce script ne mocke rien : il appelle le binaire installé, écrit dans un
Worktree, relit, fusionne, exporte un vrai XLSX, le réimporte et rend un PDF.
Il est lancé par la CI Docker sous l'utilisateur non-root `arena`.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from openpyxl import load_workbook


def _run(*args: str, timeout: int = 180) -> dict:
    commande = ["univer", *args, "--json"]
    resultat = subprocess.run(
        commande,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env={**os.environ, "NO_COLOR": "1", "CI": "1"},
    )
    if resultat.returncode != 0:
        raise AssertionError(
            f"{' '.join(commande[:4])} a échoué ({resultat.returncode})\n"
            f"stdout: {resultat.stdout[-2000:]}\n"
            f"stderr: {resultat.stderr[-2000:]}"
        )
    try:
        charge = json.loads(resultat.stdout)
    except json.JSONDecodeError as erreur:
        raise AssertionError(
            f"Sortie Univer non JSON : {resultat.stdout[-2000:]}"
        ) from erreur
    if not isinstance(charge, dict):
        raise AssertionError(f"Résultat Univer inattendu : {type(charge).__name__}")
    return charge


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="arena-univer-smoke-") as temp:
        racine = Path(temp)
        fichier = racine / "office.univer"
        export_xlsx = racine / "office.xlsx"
        rendu_pdf = racine / "office.pdf"
        reimporte = racine / "reimporte.univer"

        _run("new", str(fichier))
        if not fichier.is_file() or fichier.stat().st_size == 0:
            raise AssertionError("univer new n'a pas créé de conteneur réel")

        worktree = _run("worktree", "add", str(fichier), "--name", "ci")
        worktree_id = str(worktree.get("worktreeId") or "")
        if not worktree_id:
            raise AssertionError("worktree add n'a pas rendu worktreeId")

        unite = _run(
            "unit", "add", str(fichier),
            "--worktree", worktree_id,
            "--type", "sheet",
            "--name", "Budget",
        )
        unit_id = str(unite.get("unitId") or "")
        if not unit_id:
            raise AssertionError("unit add n'a pas rendu unitId")

        ecriture = _run(
            "execute", str(fichier),
            "--worktree", worktree_id,
            "--unit", unit_id,
            "-e",
            (
                'const s = workbook.getActiveSheet(); '
                's.getRange("A1").setValue("Arena Office"); '
                's.getRange("B1").setValue(42); '
                'return s.getRange("A1:B1").getDisplayValues();'
            ),
        )
        if ecriture.get("committed") is not True:
            raise AssertionError(f"l'écriture n'a pas été commitée : {ecriture}")

        relecture = _run(
            "execute", str(fichier),
            "--worktree", worktree_id,
            "--unit", unit_id,
            "-e",
            'return workbook.getActiveSheet().getRange("A1:B1").getDisplayValues();',
        )
        if relecture.get("value") != [["Arena Office", "42"]]:
            raise AssertionError(f"relecture Worktree fausse : {relecture}")

        inspection = _run(
            "inspect", "range", "A1:B1", str(fichier),
            "--worksheet", "index:1",
            "--unit", unit_id,
            "--worktree", worktree_id,
        )
        ranges = inspection.get("ranges") or []
        if not ranges or ranges[0].get("displayValues") != [["Arena Office", "42"]]:
            raise AssertionError(f"inspect ne voit pas la modification : {inspection}")

        pret = _run("worktree", "ready", str(fichier), "--worktree", worktree_id)
        if pret.get("status") != "ready":
            raise AssertionError(f"worktree ready inattendu : {pret}")

        fusion = _run("worktree", "merge", str(fichier), "--worktree", worktree_id)
        if fusion.get("status") != "merged":
            raise AssertionError(f"worktree merge inattendu : {fusion}")

        trunk = _run(
            "inspect", "range", "A1:B1", str(fichier),
            "--worksheet", "index:1",
            "--unit", unit_id,
            "--trunk",
        )
        ranges_trunk = trunk.get("ranges") or []
        if not ranges_trunk or ranges_trunk[0].get("displayValues") != [["Arena Office", "42"]]:
            raise AssertionError(f"la fusion n'est pas visible dans le trunk : {trunk}")

        _run("export", str(fichier), str(export_xlsx), "--unit", unit_id, timeout=300)
        if not export_xlsx.is_file() or export_xlsx.stat().st_size == 0:
            raise AssertionError("l'export XLSX est absent ou vide")

        classeur = load_workbook(export_xlsx, read_only=True, data_only=False)
        feuille = classeur.active
        if feuille["A1"].value != "Arena Office" or feuille["B1"].value != 42:
            raise AssertionError(
                f"XLSX exporté incorrect : A1={feuille['A1'].value!r}, B1={feuille['B1'].value!r}"
            )
        classeur.close()

        importe = _run("import", str(reimporte), "--file", str(export_xlsx), timeout=300)
        imported_unit = str(importe.get("unitId") or "")
        if not imported_unit or not reimporte.is_file() or reimporte.stat().st_size == 0:
            raise AssertionError(f"réimport XLSX invalide : {importe}")

        verif_import = _run(
            "inspect", "range", "A1:B1", str(reimporte),
            "--worksheet", "index:1",
            "--unit", imported_unit,
            "--trunk",
        )
        imported_ranges = verif_import.get("ranges") or []
        if not imported_ranges or imported_ranges[0].get("displayValues") != [["Arena Office", "42"]]:
            raise AssertionError(f"le XLSX réimporté ne conserve pas les données : {verif_import}")

        _run("print-pdf", str(fichier), str(rendu_pdf), "--unit", unit_id, timeout=300)
        if (
            not rendu_pdf.is_file()
            or rendu_pdf.stat().st_size < 100
            or rendu_pdf.read_bytes()[:5] != b"%PDF-"
        ):
            raise AssertionError("le rendu PDF Univer n'est pas un PDF réel")

        print(
            "UNIVER_SMOKE_OK "
            f"container={fichier.stat().st_size} "
            f"xlsx={export_xlsx.stat().st_size} "
            f"pdf={rendu_pdf.stat().st_size}"
        )


if __name__ == "__main__":
    main()
