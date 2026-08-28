"""Une demande simple paie-t-elle vraiment moins cher ?

`core/execution/voies.py` a ses propres tests (`tests/core/test_voies_execution.py`).
Ce fichier tient le **branchement** : l'orchestrateur consulte la voie juste
après avoir classé la demande, et ce que la passerelle laisse la mémoire ajouter
au prompt suit cette voie au lieu d'une constante unique.
"""
import pytest

from agents.orchestrator.orchestrator_agent import INTENTIONS, OrchestratorAgent
from apps.backend.routers import pwa_gateway
from apps.backend.routers.pwa_gateway import budget_memoire, prompt_systeme
from core.execution.voies import BUDGETS, VOIE_INCONNUE, Voie, budget_de, rang, voie_pour

# --- L'orchestrateur consulte la voie ---------------------------------------------

async def test_la_voie_voyage_avec_la_reponse(provider_factory):
    """Sans elle, personne en aval ne sait ce que ce tour avait le droit de coûter."""
    agent = OrchestratorAgent(provider=provider_factory("Bonjour."), memory=None)

    reponse = await agent.run("Bonjour", context={"intent": "CHAT"})

    assert reponse["voie"] == Voie.LEGERE.value
    assert reponse["budget"]["appels_modele_max"] == BUDGETS[Voie.LEGERE].appels_modele_max


async def test_une_question_simple_n_emprunte_pas_la_voie_la_plus_chere(provider_factory):
    """« bonjour » ne doit pas payer le prix d'une démonstration."""
    agent = OrchestratorAgent(provider=provider_factory("Bonjour."), memory=None)

    reponse = await agent.run("Bonjour", context={"intent": "CHAT"})

    assert rang(Voie(reponse["voie"])) < rang(Voie.PROFONDE)


async def test_une_intention_inconnue_ne_monte_jamais_en_gamme(provider_factory):
    """Se tromper vers le haut coûte une carte graphique et une minute d'attente."""
    agent = OrchestratorAgent(provider=provider_factory("Reponse."), memory=None)

    reponse = await agent.run("peu importe", context={"intent": "INTENTION_INVENTEE"})

    assert reponse["voie"] == VOIE_INCONNUE.value
    assert rang(Voie(reponse["voie"])) < rang(Voie.RECHERCHE)


async def test_une_demonstration_a_bien_droit_a_la_voie_profonde(provider_factory):
    agent = OrchestratorAgent(provider=provider_factory("Demonstration."), memory=None)

    reponse = await agent.run("Démontre cette intégrale", context={"intent": "DEEP_REASONING"})

    assert reponse["voie"] == Voie.PROFONDE.value


async def test_la_cible_de_duree_n_est_pas_presentee_comme_une_mesure(provider_factory):
    """Rien n'a été chronométré ici : le champ s'appelle objectif, pas durée."""
    agent = OrchestratorAgent(provider=provider_factory("Bonjour."), memory=None)

    reponse = await agent.run("Bonjour", context={"intent": "CHAT"})

    assert "objectif_secondes" in reponse["budget"]
    assert "duree_secondes" not in reponse["budget"]
    assert "duree_mesuree" not in reponse["budget"]


@pytest.mark.parametrize("intention", sorted(INTENTIONS))
async def test_chaque_intention_connue_a_sa_voie(intention, provider_factory):
    """Une intention sans voie renverrait sur le défaut sans que personne le voie."""
    agent = OrchestratorAgent(provider=provider_factory("Reponse."), memory=None)

    reponse = await agent.run("peu importe", context={"intent": intention})

    assert reponse["voie"] == voie_pour(intention).value


# --- Le budget mémoire suit la voie ------------------------------------------------

def test_le_budget_memoire_vient_de_la_voie():
    assert budget_memoire("CHAT") == budget_de(Voie.LEGERE).memoire_caracteres
    assert budget_memoire("DEEP_REASONING") == budget_de(Voie.PROFONDE).memoire_caracteres


def test_une_intention_inconnue_prend_le_budget_de_la_voie_la_moins_chere():
    assert budget_memoire("INTENTION_INVENTEE") == budget_de(VOIE_INCONNUE).memoire_caracteres
    assert budget_memoire(None) == budget_de(VOIE_INCONNUE).memoire_caracteres


def test_le_budget_memoire_n_est_plus_une_constante_unique():
    """C'est tout l'objet du branchement : deux intentions, deux budgets."""
    assert budget_memoire("CHAT") != budget_memoire("DEEP_REASONING")


async def test_le_budget_de_la_voie_borne_reellement_le_prompt(monkeypatch, tmp_path):
    """La limite est dure : un souvenir de plus n'est pas tronqué, il n'est pas pris."""
    from core.memory.personnelle import MemoirePersonnelle, Nature, TypeSouvenir
    from core.memory.semantique import IndexSemantique

    class Muet:
        async def __call__(self, textes):
            return []

    memoire = MemoirePersonnelle(db_path=str(tmp_path / "memoire.db"))
    monkeypatch.setattr(pwa_gateway, "memoire_personnelle", memoire)
    monkeypatch.setattr(pwa_gateway, "index_semantique", IndexSemantique(fournisseur=Muet()))
    for numero in range(40):
        memoire.retenir(f"Le tarif de pose du chantier {numero} est 5000 FCFA le m2 developpe.",
                        TypeSouvenir.SEMANTIQUE, Nature.FAIT, source=f"devis UC-{numero}")

    etroit = await prompt_systeme(None, "quel est le tarif de pose ?", intention="CHAT")
    large = await prompt_systeme(None, "quel est le tarif de pose ?",
                                 intention="DEEP_REASONING")

    assert etroit.count("5000 FCFA") < large.count("5000 FCFA"), (
        "la voie profonde s'autorise plus de mémoire que la voie légère")
