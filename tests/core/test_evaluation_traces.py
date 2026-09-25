from core.observabilite.evaluation import (
    EpisodeEvaluation,
    EtapeEvaluation,
    SignalEvaluation,
    TrajectoireEvaluation,
    agreger,
)


def test_agreger_trajectoires_et_signaux_mesures():
    episode = EpisodeEvaluation(
        nom="memoire",
        trajectoires=(
            TrajectoireEvaluation(
                scenario="retrouve-source",
                etapes=(
                    EtapeEvaluation("recherche", True, (SignalEvaluation("precision", 1.0),)),
                    EtapeEvaluation("reponse", True),
                ),
                signaux=(SignalEvaluation("latence_ms", 12.0),),
            ),
            TrajectoireEvaluation(
                scenario="inconnu",
                etapes=(EtapeEvaluation("recherche", False, erreur="absent"),),
                signaux=(SignalEvaluation("latence_ms", 18.0),),
            ),
        ),
    )

    rapport = agreger([episode])

    assert rapport == {
        "total": 2,
        "reussies": 1,
        "taux_reussite": 0.5,
        "moyennes": {"latence_ms": 15.0, "precision": 1.0},
    }


def test_agreger_vide_ne_fabrique_pas_un_score():
    rapport = agreger([])
    assert rapport["total"] == 0
    assert rapport["taux_reussite"] is None
    assert rapport["moyennes"] == {}


def test_trajectoire_sans_etape_nest_pas_reussie():
    trajectoire = TrajectoireEvaluation(scenario="vide", etapes=())
    assert trajectoire.reussie is False
