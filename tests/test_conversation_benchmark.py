"""Benchmark local reproductible de la politique conversationnelle.

Il mesure la couche déterministe, pas la qualité subjective d'un LLM externe.
Les 5 graines sont multipliées par 20 distracteurs pour 100 scénarios stables.
"""
import json
from pathlib import Path

from apps.backend.services.conversation_intelligence import accept_memory, score_memory, understand


DATA = json.loads((Path(__file__).with_name("conversation_benchmark.json")).read_text(encoding="utf-8"))
DISTRACTORS = [
    "serveur", "voiture", "vidéo", "chantier", "ordinateur", "PDF", "facture", "mémoire", "Qwen", "Wan",
    "RTX", "téléphone", "client", "devis", "Docker", "GitHub", "plafond", "isolation", "banque", "application",
]


def test_benchmark_has_one_hundred_scenarios():
    assert len(DATA["scenarios"]) * len(DISTRACTORS) == 100


def test_precision_first_benchmark():
    passed = 0
    total = 0
    for seed in DATA["scenarios"]:
        for distractor in DISTRACTORS:
            total += 1
            history = [{"role": "user", "content": text} for text in seed["history"]]
            state = understand(seed["query"], history)
            wrong = {
                "content": f"Le sujet {distractor} a une information différente sans rapport avec la question.",
                "created": 0.0, "conversation_id": "other", "kind": "user_fact",
            }
            wrong_features = score_memory(seed["query"], wrong, state, semantic_score=0.96)
            wrong_rejected = not accept_memory(wrong_features, 0.18)
            transition_ok = True
            if seed["expect"] == "continuation":
                transition_ok = state.transition in {"CONTINUATION", "TOPIC_RETURN"}
            elif seed["expect"] == "topic_return":
                transition_ok = state.transition == "TOPIC_RETURN"
            if wrong_rejected and transition_ok:
                passed += 1
    # Precision est le critère bloquant : aucun distracteur manifestement hors sujet accepté.
    assert passed == total == 100
