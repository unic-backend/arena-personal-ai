"""« Résous cette équation » : le calcul a-t-il vraiment lieu ?

`core/reasoning/reasoning_engine.py` a ses propres tests
(`tests/core/test_reasoning.py`). Ce fichier tient le **branchement** :
l'intention `DEEP_REASONING` atteint le moteur, le calcul est réellement
exécuté, et quand le bac à sable refuse, la réponse le dit au lieu de présenter
un chiffre élégant que rien n'a vérifié.

Aucun test n'appelle Ollama ni Docker.
"""
import pytest

from apps.backend.routers import chat as routeur_chat
from apps.backend.routers.chat import ChatRequest, dispatch_request, note_de_calcul
from core.reasoning.reasoning_engine import ReasoningEngine

PLAN_AVEC_CODE = (
    "Plan : resoudre l'equation avec sympy.\n"
    "```python\nimport sympy; print(sympy.solve('x**2 - 5*x + 6'))\n```"
)
PLAN_SANS_CODE = "Plan en prose : il n'y a rien a calculer ici."


@pytest.fixture
def moteur(monkeypatch, provider_factory):
    """Le vrai moteur, avec un modèle scripté et un bac à sable doublé."""
    def _installer(plan, solution="Solution finale.", calcul=None):
        engin = ReasoningEngine(provider=provider_factory(plan, solution))
        appels = []

        def _executer(code):
            appels.append(code)
            return calcul if calcul is not None else {
                "success": True, "stdout": "[2, 3]", "stderr": ""}

        monkeypatch.setattr(engin.interpreter, "execute_python_code", _executer)
        monkeypatch.setattr(routeur_chat, "reasoning_engine", engin)
        engin.appels = appels
        return engin
    return _installer


async def raisonner(demande="Résous x^2 - 5x + 6 = 0"):
    return await dispatch_request(ChatRequest(prompt=demande, session_id="test"),
                                  intent="DEEP_REASONING")


# --- Le test qui justifie ce branchement ------------------------------------------

async def test_la_demande_atteint_le_moteur_de_raisonnement(moteur):
    """Avant : une passe du modèle rapide, et un chiffre sorti de sa tête."""
    engin = moteur(PLAN_AVEC_CODE)

    resultat = await raisonner()

    assert resultat["agent"] == "ReasoningEngine"
    assert engin.appels, "le code du plan doit être réellement exécuté"


async def test_le_calcul_execute_voyage_avec_la_reponse(moteur):
    """Sans lui, personne ne peut vérifier que le chiffre vient d'une exécution."""
    moteur(PLAN_AVEC_CODE)

    resultat = await raisonner()

    assert resultat["calcul"] == "[2, 3]"
    assert resultat["plan"].startswith("Plan :")


async def test_l_orchestrateur_ne_repond_plus_a_sa_place(moteur, monkeypatch):
    moteur(PLAN_AVEC_CODE)

    async def interdit(*args, **kwargs):
        raise AssertionError("DEEP_REASONING ne doit plus passer par l'orchestrateur.")

    monkeypatch.setattr(routeur_chat.orchestrator, "run", interdit)

    assert (await raisonner())["agent"] == "ReasoningEngine"


# --- Un calcul qui n'a pas eu lieu se dit -----------------------------------------

async def test_le_bac_a_sable_refuse_et_la_reponse_le_dit(moteur):
    """Une capacité absente se rapporte : elle ne se simule pas."""
    moteur(PLAN_AVEC_CODE, calcul={
        "success": False, "stdout": "",
        "stderr": "Exécution refusée : le démon Docker est inactif."})

    resultat = await raisonner()

    assert "refusée" in resultat["calcul"]
    assert "n a donc ete verifie par aucun calcul" in resultat["response"]
    assert "Docker" in resultat["response"], "la raison doit voyager avec l'avertissement"


async def test_un_calcul_reussi_n_ajoute_aucun_avertissement(moteur):
    moteur(PLAN_AVEC_CODE)

    resultat = await raisonner()

    assert resultat["response"] == "Solution finale."


async def test_un_plan_sans_code_ne_declenche_rien_et_n_avertit_de_rien(moteur):
    """On n'ajoute pas un avertissement à une réponse qui ne prétend rien calculer."""
    engin = moteur(PLAN_SANS_CODE)

    resultat = await raisonner("Explique-moi une idée")

    assert engin.appels == []
    assert resultat["calcul"] == ""
    assert resultat["response"] == "Solution finale."


@pytest.mark.parametrize("calcul", ["", "[2, 3]", "42"])
def test_un_calcul_qui_a_eu_lieu_ne_porte_pas_de_note(calcul):
    assert note_de_calcul(calcul) == ""


def test_un_calcul_refuse_porte_toujours_sa_raison():
    note = note_de_calcul("Erreur calcul : le démon Docker est inactif.")

    assert "Docker" in note and "aucun calcul" in note
