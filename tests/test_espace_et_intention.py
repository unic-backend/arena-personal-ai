"""Un espace dit une famille, pas une action.

**Mesuré le 03/09/2026.** Le propriétaire tape « Monte-moi un clip promo à
partir de ces photos » — une suggestion proposée par l'application elle-même,
dans l'espace « Vidéo ». Réponse : « Aucune vidéo valide fournie pour
l'analyse ». Il avait joint des **photos** et demandé un **montage** ; la
demande est partie à l'analyseur de vidéo.

Mesure du routage, avant correctif :

    sans espace       -> MONTAGE          (juste)
    espace « video »  -> VIDEO_ANALYSIS   (faux)

**Choisir l'espace rendait le routage pire que ne rien choisir.** Cliquer
« Vidéo » dit qu'on parle de vidéo, pas qu'on veut l'analyser plutôt que la
monter.

L'espace reste autoritaire — on ne sort jamais de sa famille, même si un
mot-clé le suggère — mais il ne tranche plus à la place d'un mot-clé qui a
nommé l'action.
"""
import asyncio
import logging

import pytest

from agents.orchestrator.orchestrator_agent import (
    FAMILLE_PAR_ESPACE,
    INTENTION_PAR_ESPACE,
)


@pytest.fixture(autouse=True)
def _silence():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


@pytest.fixture
def orchestrateur():
    from apps.backend import runtime
    return runtime.orchestrator


def _intention(orchestrateur, phrase, espace):
    return asyncio.run(orchestrateur.analyze_intent(phrase, espace))


def test_la_suggestion_de_lapplication_ne_part_plus_a_lanalyseur(orchestrateur):
    """La phrase exacte de l'écran, dans l'espace exact où elle est proposée.

    Une application qui suggère une phrase et échoue dessus est pire qu'une
    application qui ne suggère rien.
    """
    assert _intention(
        orchestrateur, "Monte-moi un clip promo à partir de ces photos", "video",
    ) == "MONTAGE"


def test_les_deux_autres_suggestions_restent_a_lanalyse(orchestrateur):
    """Le correctif ne devait pas déplacer ce qui marchait déjà."""
    for phrase in ("Analyse la vidéo que je vais joindre",
                   "Quelle est la durée et la résolution de ce fichier ?"):
        assert _intention(orchestrateur, phrase, "video") == "VIDEO_ANALYSIS"


def test_un_mot_cle_hors_famille_ne_sort_pas_de_lespace(orchestrateur):
    """**La garde qui protège l'espace.**

    « chantier » attire vers le métier ; depuis l'espace Vidéo, la demande
    reste vidéo. Sinon le correctif remplacerait un mauvais routage par un
    autre : le propriétaire a cliqué « Vidéo », c'est une instruction.
    """
    intention = _intention(orchestrateur, "Parle-moi de mon chantier", "video")

    assert intention in FAMILLE_PAR_ESPACE["video"]
    assert intention != "PLAQUISTE"


def test_les_espaces_sans_famille_gardent_lancien_comportement(orchestrateur):
    """Seul « video » a plusieurs actions déclarées. Les autres doivent router
    exactement comme avant — un correctif ciblé ne change pas ce qu'on n'a pas
    mesuré."""
    for espace, defaut in INTENTION_PAR_ESPACE.items():
        if espace in FAMILLE_PAR_ESPACE:
            continue
        assert _intention(orchestrateur, "fais quelque chose avec ca", espace) == defaut


def test_chaque_famille_contient_le_defaut_de_son_espace():
    """Une famille qui ne contient pas son propre défaut laisserait l'espace
    router vers une action qu'il déclare étrangère."""
    for espace, famille in FAMILLE_PAR_ESPACE.items():
        assert INTENTION_PAR_ESPACE[espace] in famille
