from __future__ import annotations

import pytest

from scripts.performance_baseline import construire_baseline, mesurer


def test_mesurer_rapporte_des_mesures_sans_inventer_de_cible() -> None:
    resultat = mesurer(lambda: None, 3)
    assert set(resultat) == {"min_ms", "median_ms", "p95_ms", "max_ms"}
    assert resultat["min_ms"] >= 0
    assert resultat["max_ms"] >= resultat["min_ms"]


def test_baseline_annonce_explicitement_ce_quelle_ne_mesure_pas() -> None:
    resultat = construire_baseline(1)
    assert resultat["scope"] == "local-process-only"
    assert resultat["samples"] == 1
    assert "provider_latency" in resultat["not_measured"]
    assert "gpu" in resultat["not_measured"]


def test_baseline_refuse_zero_echantillon() -> None:
    with pytest.raises(ValueError, match="samples"):
        construire_baseline(0)
