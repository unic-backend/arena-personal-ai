"""Regressions for short continuation requests and working-context precision."""

from apps.backend.services.conversation_intelligence import understand
from apps.backend.services.memory_engine import MemoryEngine


def _history(*messages: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": message} for message in messages]


def test_bare_continue_is_a_continuation_not_a_topic_shift():
    history = _history(
        "Le PDF du devis Fast Group est prêt.",
        "Le client veut aussi une copie signée.",
    )

    state = understand("Continue", history)

    assert state.transition == "CONTINUATION"
    assert state.question_scope == "CURRENT_CONVERSATION"


def test_working_context_prefers_resolved_reference_over_old_stopword_match():
    history = _history(
        "Je travaille avec Mamadou sur un devis.",
        "Le PDF est prêt.",
    )
    query = "Continue avec ça"
    state = understand(query, history)

    memories = MemoryEngine._working_candidates(history, query, state)

    assert state.references.get("recent_reference") == "PDF"
    assert memories
    assert memories[0]["content"] == "Le PDF est prêt."
    assert all("Mamadou" not in memory["content"] for memory in memories)


def test_working_context_does_not_match_substrings_or_stopwords():
    history = _history(
        "Le montage vidéo est terminé.",
        "Le devis est prêt.",
    )

    memories = MemoryEngine._working_candidates(history, "Continue avec ça")

    assert memories == []
