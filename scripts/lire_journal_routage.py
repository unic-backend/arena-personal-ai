"""Relit le journal de routage : ce que `dispatch_request` a reellement decide.

    python scripts/lire_journal_routage.py
    python scripts/lire_journal_routage.py --limite 20
    python scripts/lire_journal_routage.py --requete <identifiant>

Chantier « journal de routage » (DEC-0192, DEC-0193). Une ligne par passage
par `dispatch_request` : la date, la phrase exacte du proprietaire,
l'intention retenue, les agents reellement appeles et — pour une chaine
courte (DEC-0143) — les etapes que `core/agent/equipe.py::executer` a
reellement executees. Lecture seule : ce script ne decide rien et n'ecrit
rien.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from apps.backend.config import DB_PATH  # noqa: E402
from core.observabilite.routage import JournalDeRoutage  # noqa: E402


def _ligne(appel) -> str:
    agents = " -> ".join(appel.agents) if appel.agents else "(aucun)"
    chaine = f", {len(appel.etapes)} etape(s) executee(s)" if appel.etapes else ""
    return (f"[{appel.horodatage}] {appel.intention:<16} {agents}{chaine}\n"
            f"    « {appel.phrase} »")


def main() -> None:
    analyseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analyseur.add_argument("--limite", type=int, default=20,
                           help="combien de passages au plus (les plus recents d'abord)")
    analyseur.add_argument("--requete", default=None,
                           help="ne garder que les passages d'une demande HTTP donnee")
    arguments = analyseur.parse_args()

    journal = JournalDeRoutage(db_path=str(DB_PATH))
    passages = journal.dernieres(limite=arguments.limite, requete_id=arguments.requete)

    if not passages:
        print("Aucun passage enregistre.")
        return

    for appel in passages:
        print(_ligne(appel))
    print(f"\n{len(passages)} passage(s) affiche(s).")


if __name__ == "__main__":
    main()
