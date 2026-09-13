"""Moteur de raisonnement : plan, calcul en bac a sable, synthese.

Le chemin complet exige Ollama ; le comportement sans bac a sable se mesure
hors ligne. Les modes `approfondie` sont couverts par des providers factices :
aucun appel reseau.
"""
import pytest

from core.reasoning.reasoning_engine import ReasoningEngine

PLAN_AVEC_CODE = (
    "Plan : resoudre l'equation avec sympy.\n"
    "```python\nimport sympy; x = sympy.Symbol('x'); print(sympy.solve(x**2 - 5*x + 6, x))\n```"
)

VERDICT_OK = "VERDICT: OK\nRAISON: reponse complete et exacte\nCONFIANCE: 0.9"
VERDICT_KO = "VERDICT: KO\nRAISON: il manque les cas limites\nCONFIANCE: 0.4"


# --- Mode standard : comportement historique ---------------------------------


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
    # Le mode par defaut ne fait pas de critique : rien n'est invente.
    assert res["profondeur"] == "standard"
    assert res["critique"] is None


# --- Mode approfondie : critique et revision ---------------------------------


async def test_approfondie_critique_ok_conserve_la_synthese(provider_factory, monkeypatch):
    """Quand la critique dit OK, la synthese est rendue telle quelle, sans
    appel de revision au modele."""
    provider = provider_factory(
        "Plan simple, sans code.",
        "Solution finale.",
        VERDICT_OK,
    )
    moteur = ReasoningEngine(provider=provider)
    monkeypatch.setattr(
        moteur.interpreter, "execute_python_code",
        lambda *a, **k: {"success": True, "stdout": "", "sans_code": True},
    )

    res = await moteur.solve_complex_task("Explique une idee", profondeur="approfondie")

    assert res["final_response"] == "Solution finale."
    assert res["critique"] is not None
    assert res["critique"]["ok"] is True
    assert res["critique"]["confiance"] == pytest.approx(0.9)
    etapes = {e["etape"]: e for e in res["coordination"]["etapes"]}
    assert etapes["revision"]["etat"] == "DONE"


async def test_approfondie_critique_ko_declenche_la_revision(provider_factory, monkeypatch):
    """Quand la critique dit KO, la revision remplace la synthese."""
    provider = provider_factory(
        "Plan simple, sans code.",
        "Solution incomplete.",
        VERDICT_KO,
        "Solution corrigee et complete.",
    )
    moteur = ReasoningEngine(provider=provider)
    monkeypatch.setattr(
        moteur.interpreter, "execute_python_code",
        lambda *a, **k: {"success": True, "stdout": "", "sans_code": True},
    )

    res = await moteur.solve_complex_task("Explique une idee", profondeur="approfondie")

    assert res["final_response"] == "Solution corrigee et complete."
    assert res["critique"] is not None
    assert res["critique"]["ok"] is False
    assert "cas limites" in res["critique"]["raison"]


async def test_approfondie_critique_illisible_est_abandonnee(provider_factory, monkeypatch):
    """Une critique qui ne respecte pas le format ne casse rien : elle est
    abandonnee, la synthese originale est conservee, la tache aboutit."""
    provider = provider_factory(
        "Plan simple, sans code.",
        "Solution finale.",
        "je ne sais pas trop",
    )
    moteur = ReasoningEngine(provider=provider)
    monkeypatch.setattr(
        moteur.interpreter, "execute_python_code",
        lambda *a, **k: {"success": True, "stdout": "", "sans_code": True},
    )

    res = await moteur.solve_complex_task("Explique une idee", profondeur="approfondie")

    assert res["final_response"] == "Solution finale."
    assert res["critique"] is None
    etapes = {e["etape"]: e for e in res["coordination"]["etapes"]}
    assert etapes["critique"]["etat"] == "SKIPPED"
    assert res["status"] == "success"


def test_profondeur_inconnue_refusee(provider_factory):
    provider = provider_factory()
    moteur = ReasoningEngine(provider=provider)

    with pytest.raises(ValueError, match="profondeur inconnue"):
        import asyncio
        asyncio.run(moteur.solve_complex_task("test", profondeur="turbo"))


# --- Bout en bout (Ollama requis) -------------------------------------------


@pytest.mark.integration
async def test_le_moteur_resout_une_equation_de_bout_en_bout(ollama_en_ligne):
    moteur = ReasoningEngine(provider=ollama_en_ligne)

    res = await moteur.solve_complex_task(
        "Résous l'équation x^2 - 5*x + 6 = 0 avec sympy et donne les racines exactes."
    )

    assert res["final_response"].strip() != ""


@pytest.mark.integration
async def test_le_mode_approfondie_critique_et_revise_si_besoin(ollama_en_ligne):
    """Le mode approfondie doit rendre un verdict lisible en bout de chaine."""
    moteur = ReasoningEngine(provider=ollama_en_ligne)

    res = await moteur.solve_complex_task(
        "Combien font 2 + 2 ? Justifie en une phrase.",
        profondeur="approfondie",
    )

    assert res["final_response"].strip() != ""
    if res["critique"] is not None:
        assert res["critique"]["ok"] in (True, False)