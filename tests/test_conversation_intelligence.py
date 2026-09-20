from apps.backend.services.conversation_intelligence import (
    needs_long_term,
    rank_memory,
    understand,
)


def hist(*messages):
    return [{"role": "user", "content": message} for message in messages]


def test_coreference_prefers_recent_single_entity():
    history = hist("Mon frère Mamadou vient demain.")
    state = understand("Pourquoi il vient ?", history)
    assert state.relation == "CONTINUATION"
    assert state.resolved_references.get("il") == "Mamadou"
    assert not needs_long_term("Pourquoi il vient ?", history, state)


def test_topic_shift_does_not_replace_return_target():
    history = hist("Mon projet vidéo utilise Wan.", "Mon ordinateur chauffe beaucoup.")
    state = understand("Je parle du projet vidéo pas l'autre", history)
    assert state.relation == "TOPIC_RETURN"
    assert "projet" in state.active_topic.casefold() or "vidéo" in state.active_topic.casefold()


def test_entity_mismatch_rejects_semantically_similar_memory():
    state = understand("Quel modèle utilise Usman ?", hist("Usman utilise Qwen."))
    ranked = rank_memory("Quel modèle utilise Usman ?", state, [
        {"content": "Le projet Wan utilise un modèle vidéo.", "created": 1},
        {"content": "Usman utilise Qwen comme modèle.", "created": 1},
    ])
    accepted = [row.item["content"] for row in ranked if row.accepted]
    assert "Usman utilise Qwen comme modèle." in accepted
    assert "Le projet Wan utilise un modèle vidéo." not in accepted


def test_zero_memory_is_valid_for_unknown_price():
    state = understand("Combien j'ai payé ma BMW ?", hist("J'ai acheté une BMW noire."))
    ranked = rank_memory("Combien j'ai payé ma BMW ?", state, [
        {"content": "J'ai acheté une BMW noire.", "created": 1},
        {"content": "Mon ordinateur a coûté 900 euros.", "created": 1},
    ], threshold=0.45)
    assert not [row for row in ranked if row.accepted]


def test_recent_topic_continuation_beats_unrelated_computer_topic():
    history = hist(
        "Mon frère Mamadou vient demain.",
        "Mamadou travaille chez Orange.",
        "Mon ordinateur chauffe.",
    )
    state = understand("Pourquoi Mamadou vient demain ?", history)
    assert "Mamadou" in state.active_entities
    assert "ordinateur" not in state.active_topic.casefold()


def test_two_plausible_entities_are_not_guessed():
    state = understand("Pourquoi il vient ?", hist("Mamadou et Ibrahima viennent demain."))
    assert state.resolved_references == {}
