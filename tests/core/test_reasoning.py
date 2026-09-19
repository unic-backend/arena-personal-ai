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


# --- Le fil de conversation, en contexte et jamais en question (19/09/2026) ---
#
# Jusqu'ici `solve_complex_task` ne recevait que la derniere phrase :
# « verifie ton calcul » arrivait sans le calcul, et le moteur repondait a cote
# sans pouvoir faire autrement.

FIL = "Ousmane: combien font 12 % de 340 ?\nUsman: 40,8"


async def test_sans_contexte_les_invites_sont_inchangees(provider_factory):
    """Un moteur dont les invites changent en silence n'est plus comparable a
    lui-meme. Sans contexte, elles doivent etre identiques au caractere pres."""
    provider = provider_factory("Plan en prose.", "Solution.")
    moteur = ReasoningEngine(provider=provider)

    await moteur.solve_complex_task("Resous x + 1 = 2")

    for appel in provider.appels:
        assert "fin du contexte" not in appel["prompt"]
        assert "Contexte" not in appel["prompt"]


async def test_le_contexte_entre_dans_le_plan_et_la_synthese(provider_factory):
    provider = provider_factory("Plan en prose.", "Solution.")
    moteur = ReasoningEngine(provider=provider)

    await moteur.solve_complex_task("verifie ton calcul", contexte=FIL)

    plan, synthese = provider.appels[0]["prompt"], provider.appels[1]["prompt"]
    assert "40,8" in plan and "40,8" in synthese


async def test_le_contexte_est_borne_par_deux_marqueurs(provider_factory):
    """Sans ces bornes, le modele lit le fil comme faisant partie de la
    question et repond au mauvais tour — pire que de ne rien lui donner."""
    provider = provider_factory("Plan en prose.", "Solution.")
    moteur = ReasoningEngine(provider=provider)

    await moteur.solve_complex_task("verifie ton calcul", contexte=FIL)

    plan = provider.appels[0]["prompt"]
    assert "ce n'est pas la question" in plan
    assert "--- fin du contexte ---" in plan
    assert plan.index("--- fin du contexte ---") < plan.index("verifie ton calcul")


async def test_la_critique_recoit_aussi_le_contexte(provider_factory):
    provider = provider_factory("Plan en prose.", "Solution.", VERDICT_OK)
    moteur = ReasoningEngine(provider=provider)

    await moteur.solve_complex_task("verifie ton calcul",
                                    profondeur="approfondie", contexte=FIL)

    assert "40,8" in provider.appels[2]["prompt"], (
        "la critique juge « est-ce que ca repond a la question » sans savoir "
        "de quoi on parlait")


async def test_un_contexte_trop_long_garde_la_fin_et_le_dit(provider_factory):
    """Ce qui vient d'etre dit explique la question du jour mieux que ce qui a
    ete dit en premier. La coupe est dite, jamais muette."""
    provider = provider_factory("Plan en prose.", "Solution.")
    moteur = ReasoningEngine(provider=provider)
    fil = "DEBUT-DU-FIL\n" + ("bavardage " * 2000) + "\nFIN-DU-FIL"

    await moteur.solve_complex_task("verifie", contexte=fil)

    plan = provider.appels[0]["prompt"]
    assert "FIN-DU-FIL" in plan
    assert "DEBUT-DU-FIL" not in plan
    assert "debut du contexte coupe" in plan


async def test_un_contexte_vide_ou_blanc_n_ajoute_rien(provider_factory):
    provider = provider_factory("Plan en prose.", "Solution.")
    moteur = ReasoningEngine(provider=provider)

    await moteur.solve_complex_task("Resous x + 1 = 2", contexte="   \n  ")

    assert "Contexte" not in provider.appels[0]["prompt"]
