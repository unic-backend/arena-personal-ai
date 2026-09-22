"""Mesure la qualite du retrieval du Knowledge Vault sur des cas labels.

Format du JSON:
[
  {"query": "double montant joints", "relevant": ["sources/ba13.md"]},
  {"query": "isolation bruit", "relevant": ["concepts/acoustique.md", "sources/laine.md"]}
]

Aucun score n'est invente : sans fichier de verite terrain, le script refuse.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from statistics import mean

from core.knowledge.retrieval import ndcg_at_k, recall_at_k
from core.knowledge.vault import KnowledgeVault


def _charger_cas(path: Path) -> list[dict[str, object]]:
    brut = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(brut, list) or not brut:
        raise ValueError("Le fichier d'evaluation doit contenir une liste non vide.")
    cas: list[dict[str, object]] = []
    for index, item in enumerate(brut, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Cas {index}: objet JSON attendu.")
        query = str(item.get("query") or "").strip()
        relevant = item.get("relevant")
        if not query or not isinstance(relevant, list) or not relevant:
            raise ValueError(f"Cas {index}: query et relevant[] non vides sont obligatoires.")
        chemins = [str(valeur).strip() for valeur in relevant if str(valeur).strip()]
        if not chemins:
            raise ValueError(f"Cas {index}: aucun chemin pertinent exploitable.")
        cas.append({"query": query, "relevant": chemins})
    return cas


async def evaluer(path: Path, *, root: Path | None, k: int, lexical_only: bool) -> dict[str, object]:
    vault = KnowledgeVault(root) if root else KnowledgeVault()
    cas = _charger_cas(path)

    lignes: list[dict[str, object]] = []
    for item in cas:
        query = str(item["query"])
        relevant = list(item["relevant"])
        if lexical_only:
            hits = vault.search(query, limit=k)
        else:
            hits = await vault.hybrid_search(query, limit=k)
        predicted = [hit.path for hit in hits]
        pertinence = {identifiant: 1 for identifiant in relevant}
        lignes.append({
            "query": query,
            "mode": hits[0].mode if hits else ("BM25" if lexical_only else "NONE"),
            "recall_at_k": recall_at_k(predicted, relevant, k=k),
            "ndcg_at_k": ndcg_at_k(predicted, pertinence, k=k),
            "predicted": predicted,
            "relevant": relevant,
        })

    return {
        "cases": len(lignes),
        "k": k,
        "requested_mode": "BM25" if lexical_only else "HYBRID_IF_AVAILABLE",
        "mean_recall_at_k": mean(float(row["recall_at_k"]) for row in lignes),
        "mean_ndcg_at_k": mean(float(row["ndcg_at_k"]) for row in lignes),
        "results": lignes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluer le retrieval du Knowledge Vault.")
    parser.add_argument("cases", type=Path, help="JSON de requetes avec chemins pertinents labels.")
    parser.add_argument("--root", type=Path, default=None, help="Racine du vault.")
    parser.add_argument("-k", type=int, default=5, choices=range(1, 21), metavar="[1-20]")
    parser.add_argument("--lexical-only", action="store_true", help="Mesurer BM25 sans embeddings.")
    args = parser.parse_args()

    rapport = asyncio.run(
        evaluer(args.cases, root=args.root, k=args.k, lexical_only=args.lexical_only)
    )
    print(json.dumps(rapport, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
