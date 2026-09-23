from core.executive.operating_principles import PRINCIPES, SOURCE, bloc_pour_prompt
from core.executive.synthese import PROMPT_SYNTHESE


def test_operating_principles_are_compact_and_actionable():
    assert len(PRINCIPES) >= 6
    bloc = bloc_pour_prompt()
    for attendu in (
        "roles",
        "validation humaine",
        "budget",
        "trace",
        "indisponible",
        "autorite finale",
    ):
        assert attendu in bloc.lower()


def test_principles_are_native_to_executive_synthesis():
    assert "{principes}" in PROMPT_SYNTHESE
    assert "Methode d'exploitation native d'ARENA" in PROMPT_SYNTHESE


def test_source_is_attributed_without_vendoring_book_text():
    assert "Headcount Zero" in SOURCE
    assert "zero-employee-company-book" in SOURCE
