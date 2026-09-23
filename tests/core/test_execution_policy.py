from core.agent.execution_policy import (
    Complexite,
    delegation_autorisee,
    politique_pour,
)


def test_tache_simple_reste_legere():
    p = politique_pour("Quelle heure est-il ?")
    assert p.complexite is Complexite.SIMPLE
    assert p.peut_deleguer is True
    assert p.verifier_avant_final is False


def test_tache_production_active_verification_et_delegation():
    p = politique_pour(
        "Analyse tout le depot, corrige puis teste de bout en bout sans regression"
    )
    assert p.complexite is Complexite.LONGUE
    assert p.peut_deleguer is True
    assert p.verifier_avant_final is True
    assert p.garder_trace is True
    assert p.budget_delegations == 4


def test_plusieurs_pieces_peuvent_rendre_la_tache_longue():
    p = politique_pour("Analyse ces documents", pieces=["a", "b", "c", "d"])
    assert p.complexite is Complexite.LONGUE


def test_delegation_refuse_boucle_et_budget():
    p = politique_pour("audit complet de production")
    assert delegation_autorisee(p, ["orchestrator"], "researcher") is True
    assert delegation_autorisee(p, ["orchestrator", "researcher"], "researcher") is False
    assert delegation_autorisee(
        p, ["a", "b", "c", "d"], "coder"
    ) is False


def test_tache_simple_autorise_une_delegation_explicite_bornee():
    p = politique_pour("bonjour")
    assert delegation_autorisee(p, [], "researcher") is True
    assert delegation_autorisee(p, ["orchestrator"], "researcher") is False
