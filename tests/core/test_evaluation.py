from core.evaluation import (
    SignalEvaluation,
    TentativeEvaluation,
    agreger,
    pass_at_k,
)


def test_agreger_calcule_score_erreurs_et_signaux():
    rapport = agreger([
        TentativeEvaluation("a", True, (SignalEvaluation("precision", 1.0),)),
        TentativeEvaluation("b", False, (SignalEvaluation("precision", 0.0),), "timeout"),
    ])
    assert rapport.total == 2
    assert rapport.correctes == 1
    assert rapport.erreurs == 1
    assert rapport.score == 0.5
    assert rapport.moyennes == {"precision": 0.5}


def test_pass_at_k_mesure_plusieurs_tentatives():
    assert pass_at_k([(2, 1), (2, 0)], 1) == 0.25
    assert pass_at_k([(2, 1), (2, 0)], 2) == 0.5


def test_pass_at_k_refuse_les_comptes_impossibles():
    try:
        pass_at_k([(1, 2)], 1)
    except ValueError as exc:
        assert "invalide" in str(exc)
    else:
        raise AssertionError("un compte impossible doit echouer")
