"""Moteur de raisonnement : plan, calcul en bac à sable, puis synthèse.

Le chemin complet exige Ollama ; le comportement sans bac à sable se mesure hors ligne.
"""
import pytest

from core.reasoning.reasoning_engine import ReasoningEngine

PLAN_AVEC_CODE = (
    "Plan : resoudre l'equation avec sympy.\n"
    "```python\nimport sympy; x = sympy.Symbol('x'); print(sympy.solve(x**2 - 5*x + 6, x))\n```"
)


async def test_sans_bac_a_sable_le_calcul_remonte_le_refus(provider_factory, monkeypatch):
    """Le moteur ne doit pas présenter un calcul qui n'a jamais eu lieu."""
    monkeypatch.delenv("ALLOW_UNSAFE_EXEC", raising=False)
    provider = provider_factory(PLAN_AVEC_CODE, "Solution finale.")
    moteur = ReasoningEngine(provider=provider)
    monkeypatch.setattr(moteur.interpreter, "docker_available", False)

    res = await moteur.solve_complex_task("Resous x^2 - 5x + 6 = 0")

    assert "Erreur calcul" in res["calculation_result"]
    assert "refusée" in res["calculation_result"]


async def test_un_plan_sans_code_ne_declenche_aucune_execution(provider_factory, monkeypatch):
    provider = provider_factory("Plan en prose, sans code.", "Solution finale.")
    moteur = ReasoningEngine(provider=provider)

    def interdit(*args, **kwargs):
        raise AssertionError("Aucun code n'était proposé : rien ne devait s'exécuter.")

    monkeypatch.setattr(moteur.interpreter, "execute_python_code", interdit)

    res = await moteur.solve_complex_task("Explique une idee")

    assert res["final_response"] == "Solution finale."


@pytest.mark.integration
async def test_le_moteur_resout_une_equation_de_bout_en_bout(ollama_en_ligne):
    moteur = ReasoningEngine(provider=ollama_en_ligne)

    res = await moteur.solve_complex_task(
        "Résous l'équation x^2 - 5*x + 6 = 0 avec sympy et donne les racines exactes."
    )

    assert res["final_response"].strip() != ""
