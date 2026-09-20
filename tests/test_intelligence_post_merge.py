"""Post-merge adversarial benchmark for conversation and memory precision.

The dataset contains 50 golden conversations. Four deterministic perturbations
per golden yield 200 scored scenarios. These tests intentionally exercise the
merged #258 implementation before any hardening changes.
"""
import json
from pathlib import Path

import pytest

from apps.backend.services.ai_client import AIUnavailable
from apps.backend.services.conversation_intelligence import accept_memory, score_memory, understand
from apps.backend.services.memory_engine import MemoryEngine
from apps.backend.services.settings import AutonomousSettings

DATA = json.loads(
    (Path(__file__).with_name("intelligence_post_merge_goldens.json")).read_text(encoding="utf-8")
)
PERTURBATIONS = [
    "",
    " Mon téléphone est chargé.",
    " Le chantier est terminé.",
    " GitHub a envoyé une notification.",
]


class BenchmarkAI:
    def __init__(self, *, embeddings=True, facts=()):
        self.embeddings = embeddings
        self.facts = list(facts)

    def embedding_space(self):
        return "benchmark|v1"

    async def embed(self, texts):
        if not self.embeddings:
            raise AIUnavailable("benchmark embeddings unavailable")
        vectors = []
        for text in texts:
            value = float((sum(text.encode("utf-8")) % 997) + 1)
            vectors.append([value, value / 2, 1.0, 0.5])
        return vectors

    async def complete(self, messages, tools=None, json_mode=False, force_local=False):
        if json_mode:
            return {"content": json.dumps({"facts": [{"evidence": item} for item in self.facts]})}
        raise AIUnavailable("benchmark does not call chat generation")


@pytest.fixture
def intelligence_settings(tmp_path):
    return AutonomousSettings(
        db_path=tmp_path / "memory.db",
        chroma_path=tmp_path / "chroma",
        mode="LOCAL_ONLY",
        memory_debug=True,
    )


def _history(lines, perturbation=""):
    result = [{"role": "user", "content": line} for line in lines]
    if perturbation:
        result.append({"role": "user", "content": perturbation.strip()})
    return result


def test_golden_dataset_has_fifty_conversations_and_two_hundred_matrix_cases():
    assert len(DATA["goldens"]) == 50
    assert len(DATA["goldens"]) * len(PERTURBATIONS) == DATA["matrix"]["total"] == 200


def test_post_merge_conversation_matrix():
    failures = []
    total = 0
    for golden in DATA["goldens"]:
        for perturbation in PERTURBATIONS:
            total += 1
            history = _history(golden["history"], perturbation)
            state = understand(golden["query"], history)

            if golden["kind"] == "transition":
                ok = state.transition == golden["expected_transition"]
                token = golden.get("expected_topic_token", "").casefold()
                if token:
                    ok = ok and token in state.active_topic.casefold()
            elif golden["kind"] == "reference":
                ok = state.references.get("recent_reference") == golden["expected_reference"]
            elif golden["kind"] == "memory_gate":
                candidate = {
                    "content": golden["wrong_candidate"],
                    "created": 0.0,
                    "conversation_id": "other",
                    "kind": "user_fact",
                }
                features = score_memory(
                    golden["query"],
                    candidate,
                    state,
                    semantic_score=golden["semantic_score"],
                    same_conversation=False,
                )
                ok = accept_memory(features, 0.18) is golden["expected_accept"]
            else:
                raise AssertionError(f"Unknown golden kind: {golden['kind']}")

            if not ok:
                failures.append(
                    {
                        "id": golden["id"],
                        "kind": golden["kind"],
                        "perturbation": perturbation,
                        "transition": state.transition,
                        "topic": state.active_topic,
                        "reference": state.references.get("recent_reference"),
                    }
                )

    passed = total - len(failures)
    assert passed == total, f"conversation benchmark: {passed}/{total}; failures={failures[:20]}"


@pytest.mark.asyncio
async def test_user_question_does_not_become_retrievable_personal_fact(intelligence_settings):
    memory = MemoryEngine(intelligence_settings, BenchmarkAI())
    await memory.remember(
        "owner",
        "question-source",
        "Est-ce que mon serveur a 64 GB de RAM ?",
        "Je n'ai pas cette information.",
    )
    await memory.drain()
    context = await memory.context("owner", "later", "Combien de RAM a mon serveur ?")
    assert all("64 GB" not in item["content"] for item in context.memories)


@pytest.mark.asyncio
async def test_assistant_guess_is_not_retrieved_as_user_memory(intelligence_settings):
    memory = MemoryEngine(intelligence_settings, BenchmarkAI())
    await memory.remember(
        "owner",
        "guess-source",
        "Combien de RAM a mon serveur ?",
        "Ton serveur a 64 GB de RAM.",
    )
    await memory.drain()
    context = await memory.context("owner", "later", "Quelle RAM a mon serveur ?")
    assert all(
        not (item.get("kind") == "assistant_message" and "64 GB" in item["content"])
        for item in context.memories
    )


@pytest.mark.asyncio
async def test_speculation_is_not_promoted_to_confirmed_memory(intelligence_settings):
    statement = "Peut-être que je vais utiliser Wan pour Usman."
    memory = MemoryEngine(intelligence_settings, BenchmarkAI(facts=[statement]))
    await memory.remember("owner", "speculation-source", statement, "D'accord.")
    await memory.drain()
    context = await memory.context("owner", "later", "Quel modèle ai-je choisi pour Usman ?")
    assert all(
        not (item.get("kind") == "user_fact" and "Wan" in item["content"])
        for item in context.memories
    )


@pytest.mark.asyncio
async def test_memory_debug_identifies_candidates_without_exposing_content(intelligence_settings):
    fact = "Usman utilise Qwen."
    memory = MemoryEngine(intelligence_settings, BenchmarkAI(facts=[fact]))
    await memory.remember("owner", "source", fact, "Compris.")
    await memory.drain()
    context = await memory.context("owner", "later", "Quel modèle utilise Usman ?")
    accepted = [item for item in context.retrieval_debug if item.get("status") == "ACCEPTED"]
    assert accepted
    assert all(item.get("memory_id") for item in accepted)
    assert all("content" not in item for item in accepted)
