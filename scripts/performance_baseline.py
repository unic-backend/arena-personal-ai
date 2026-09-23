"""Mesure reproductible des couts de base d'ARENA, sans fournisseur externe.

Ce script ne pretend pas mesurer Ollama, le reseau ou le GPU. Il mesure uniquement
ce que cette machine execute reellement ici : import du backend et temps CPU d'un
petit lot JSON. Les resultats sont du JSON afin de pouvoir comparer deux revisions
sans transformer une impression en affirmation de performance.

Usage:
    python scripts/performance_baseline.py
    python scripts/performance_baseline.py --samples 25 --output baseline.json
"""
from __future__ import annotations

import argparse
import importlib
import json
import statistics
import time
from pathlib import Path
from typing import Callable


def mesurer(action: Callable[[], object], samples: int) -> dict[str, float]:
    """Retourne des millisecondes mesurees; aucune estimation n'est fabriquee."""
    valeurs: list[float] = []
    for _ in range(samples):
        debut = time.perf_counter_ns()
        action()
        valeurs.append((time.perf_counter_ns() - debut) / 1_000_000)
    valeurs.sort()
    index_p95 = min(len(valeurs) - 1, max(0, int(len(valeurs) * 0.95) - 1))
    return {
        "min_ms": round(valeurs[0], 3),
        "median_ms": round(statistics.median(valeurs), 3),
        "p95_ms": round(valeurs[index_p95], 3),
        "max_ms": round(valeurs[-1], 3),
    }


def _import_backend() -> object:
    return importlib.import_module("apps.backend.main")


def _json_roundtrip() -> object:
    charge = {"messages": [{"role": "user", "content": "arena"}] * 50}
    return json.loads(json.dumps(charge, ensure_ascii=False))


def construire_baseline(samples: int) -> dict[str, object]:
    if samples < 1:
        raise ValueError("samples doit etre >= 1")
    # L'import Python est mis en cache apres le premier passage. On l'assume et on
    # le nomme explicitement : cette mesure detecte surtout une regression du chemin
    # d'import, elle n'est pas presentee comme un temps de demarrage a froid.
    return {
        "schema": 1,
        "samples": samples,
        "scope": "local-process-only",
        "backend_import_cached": mesurer(_import_backend, samples),
        "json_roundtrip": mesurer(_json_roundtrip, samples),
        "not_measured": ["ollama", "gpu", "network", "provider_latency"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Baseline performance locale ARENA")
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    resultat = construire_baseline(args.samples)
    texte = json.dumps(resultat, indent=2, ensure_ascii=False)
    print(texte)
    if args.output:
        args.output.write_text(texte + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
