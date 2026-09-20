from apps.backend.services.conversation_intelligence import (
    accept_memory,
    needs_long_term,
    score_memory,
    understand,
)


def h(*messages):
    return [{"role": "user", "content": message} for message in messages]


def test_coreference_prefers_recent_person_not_unrelated_topic():
    history = h(
        "Mon frère Mamadou vient demain.",
        "Il travaille chez Orange.",
        "Mon ordinateur chauffe beaucoup.",
    )
    state = understand("Pourquoi il vient demain ?", history)
    assert state.transition == "CONTINUATION"
    assert "Mamadou" in state.active_entities or "Orange" in state.active_entities


def test_explicit_topic_return_is_detected():
    history = h("Mon projet vidéo utilise Wan.", "Ma voiture est une BMW noire.")
    state = understand("Non je parle du projet vidéo, pas l'autre.", history)
    assert state.transition == "TOPIC_RETURN"


def test_new_unrelated_topic_is_shift():
    state = understand("Mon ordinateur surchauffe", h("Le projet vidéo utilise Wan"))
    assert state.transition == "TOPIC_SHIFT"


def test_recent_reference_can_skip_global_memory():
    history = h("Mamadou vient demain.", "Il travaille chez Orange.")
    state = understand("Pourquoi il vient ?", history)
    assert needs_long_term("Pourquoi il vient ?", history, state) is False


def test_semantic_similarity_alone_cannot_inject_wrong_topic():
    state = understand("Quel modèle utilise mon assistant Usman ?", h("Mon assistant Usman utilise Qwen."))
    candidate = {
        "content": "Mon projet vidéo utilise Wan.", "created": 0.0,
        "conversation_id": "other", "kind": "user_fact",
    }
    features = score_memory(
        "Quel modèle utilise mon assistant Usman ?", candidate, state,
        semantic_score=0.99, same_conversation=False,
    )
    assert accept_memory(features, 0.18) is False


def test_matching_entity_memory_can_pass_gate():
    state = understand("Quel modèle utilise Usman ?", h("Usman est mon assistant personnel."))
    candidate = {
        "content": "Usman utilise Qwen.", "created": 0.0,
        "conversation_id": "old", "kind": "user_fact",
    }
    features = score_memory("Quel modèle utilise Usman ?", candidate, state, semantic_score=0.85)
    assert accept_memory(features, 0.18) is True


def test_zero_memory_is_valid_for_unrelated_candidate():
    state = understand("Combien j'ai payé ma BMW ?", h("J'ai acheté une BMW noire."))
    candidate = {"content": "Le serveur coûte 500 euros.", "created": 0.0, "conversation_id": "x"}
    features = score_memory("Combien j'ai payé ma BMW ?", candidate, state, semantic_score=0.8)
    assert accept_memory(features, 0.18) is False


def test_informal_french_reference_keeps_context():
    state = understand("celui de la vidéo pas l'autre", h("On travaille sur Usman.", "Le projet vidéo utilise Wan."))
    assert state.transition in {"CONTINUATION", "TOPIC_RETURN"}


def test_first_second_reference_is_not_treated_as_fresh_topic():
    state = understand("je parle du premier pas celui qu'on vient de voir", h("Premier modèle Qwen.", "Deuxième modèle Wan."))
    assert state.transition in {"CONTINUATION", "TOPIC_RETURN"}
