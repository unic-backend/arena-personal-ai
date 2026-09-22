"""CLI du Knowledge Vault local d'ARENA."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.knowledge import KnowledgeVault


def _afficher(valeur: Any) -> None:
    if hasattr(valeur, "to_dict"):
        valeur = valeur.to_dict()
    if isinstance(valeur, list):
        valeur = [item.to_dict() if hasattr(item, "to_dict") else item for item in valeur]
    print(json.dumps(valeur, ensure_ascii=False, indent=2))


def construire_parseur() -> argparse.ArgumentParser:
    parseur = argparse.ArgumentParser(
        description="Base de connaissance Markdown locale, sourcee et compatible Obsidian."
    )
    parseur.add_argument("--root", type=Path, help="Dossier du vault (defaut: data/knowledge_vault)")
    sous = parseur.add_subparsers(dest="commande", required=True)

    sous.add_parser("init", help="Creer l'ossature raw/wiki/output sans rien ecraser.")

    ingest = sous.add_parser("ingest", help="Ajouter une source locale et sa note source.")
    ingest.add_argument("source", type=Path)
    ingest.add_argument("--url", default=None)
    ingest.add_argument("--title", default=None)

    search = sous.add_parser("search", help="Chercher dans le wiki avec provenance.")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5)

    sous.add_parser("lint", help="Verifier liens, orphelins, provenance et sources brutes.")
    sous.add_parser("graph", help="Regenerer output/graph.json.")

    return parseur


def main() -> int:
    args = construire_parseur().parse_args()
    vault = KnowledgeVault(args.root) if args.root else KnowledgeVault()

    if args.command == "init":
        _afficher({"status": "INITIALIZED", **vault.initialize()})
        return 0
    if args.command == "ingest":
        _afficher(vault.ingest(args.source, source_url=args.url, title=args.title))
        return 0
    if args.command == "search":
        _afficher(vault.search(args.query, limit=args.limit))
        return 0
    if args.command == "lint":
        _afficher(vault.lint())
        return 0
    if args.command == "graph":
        cible = vault.write_graph()
        _afficher({"status": "WRITTEN", "path": str(cible)})
        return 0
    raise AssertionError(f"Commande inconnue: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
