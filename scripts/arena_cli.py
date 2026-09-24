"""CLI operateur unifiee d'ARENA.

Typer ne remplace aucun service : cette facade invoque les diagnostics et
outils operateur canoniques du depot et propage leur code de sortie.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Sequence

import typer

RACINE = Path(__file__).resolve().parent.parent
app = typer.Typer(name="arena", no_args_is_help=True, help="Commandes operateur ARENA.")
audit_app = typer.Typer(no_args_is_help=True, help="Audits du depot.")
app.add_typer(audit_app, name="audit")


def executer_script(script: str, arguments: Sequence[str] = ()) -> None:
    """Execute un script canonique avec le meme Python, sans shell."""
    chemin = RACINE / "scripts" / script
    if not chemin.is_file():
        typer.echo(f"Script ARENA introuvable: {chemin}", err=True)
        raise typer.Exit(code=2)
    try:
        resultat = subprocess.run(
            [sys.executable, str(chemin), *arguments],
            cwd=RACINE,
            check=False,
        )
    except OSError as exc:
        typer.echo(f"Impossible d'executer {script}: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if resultat.returncode:
        raise typer.Exit(code=resultat.returncode)


@app.command()
def doctor() -> None:
    """Mesure l'etat de la machine et des services ARENA."""
    executer_script("doctor.py")


@audit_app.command("orphans")
def audit_orphans() -> None:
    """Mesure les modules atteints et orphelins."""
    executer_script("orphelins.py")


@app.command()
def performance(
    samples: int = typer.Option(30, min=1, max=10_000, help="Echantillons du baseline."),
) -> None:
    """Lance le baseline reproductible des operations locales."""
    executer_script("performance_baseline.py", ("--samples", str(samples)))


if __name__ == "__main__":
    app()
