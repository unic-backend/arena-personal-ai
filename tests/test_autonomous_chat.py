"""Comportements reels SQLite/Chroma/HTTP, modeles scripts explicitement hors ligne."""
import asyncio
import json
import sqlite3
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.backend import security
from apps.backend.routers.autonomous_chat import get_runtime, router
from apps.backend.services.ai_client import AIClient, AIUnavailable
from apps.backend.services.memory_engine import MemoryEngine
from apps.backend.services.orchestrator import ChatInput, CurrentUser, Orchestrator
from apps.backend.services.settings import AutonomousSettings
from apps.backend.services.tools.builtin import CalculateArgs, SearchArgs, WebSearch, builtin_registry, calculate
from apps.backend.services.tools.registry import Tool, ToolRegistry, ToolResult
from core.memory.personnelle import MemoirePersonnelle, Nature, TypeSouvenir
from core.models.usage import CompteurUsage


class ScriptedAI:
    def __init__(self, replies=(), facts=(), embeddings=False):
        self.replies = list(replies)
        self.facts = list(facts)
        self.embeddings = embeddings
        self.calls = []

    def cloud_allowed(self, text):
        return self.embeddings

    async def embed(self, texts):
        if not self.embeddings:
            raise AIUnavailable("test: embeddings absent")
        return [[1., 0., 0., 0.] for _ in texts]

    async def complete(self, messages, tools=None, json_mode=False, force_local=False):
        if json_mode:
            return {"content": json.dumps({"facts": [{"evidence": fact} for fact in self.facts]})}
        self.calls.append((json.loads(json.dumps(messages)), tools))
        if not self.replies:
            raise AIUnavailable("test: modele absent")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def settings(tmp_path):
    return AutonomousSettings(db_path=tmp_path / "memory.db", chroma_path=tmp_path / "chroma",
                              mode="LOCAL_ONLY")


@pytest.mark.parametrize("expression, expected", [
    ("2+3*4", 14), ("(2500*84)*0.8", 168000), ("2**10", 1024), ("-8/2", -4),
])
async def test_calculate(expression, expected):
    result = await calculate(CalculateArgs(expression=expression))
    assert result.ok and result.data["value"] == expected


@pytest.mark.parametrize("expression", [
    "__import__('os').system('echo unsafe')", "(1).__class__", "[1][0]", "True+1",
    "2**100000000", "1/0", "1e300*1e300", "(-1)**0.5", "sum([1,2])",
])
async def test_calculator_rejects_arbitrary_or_unbounded_execution(expression):
    assert not (await calculate(CalculateArgs(expression=expression))).ok


async def test_registry_unknown_invalid_and_timeout():
    async def slow(args):
        await asyncio.sleep(1)
        return ToolResult(ok=True)
    registry = ToolRegistry()
    registry.register(Tool("slow", "test", CalculateArgs, slow, timeout=0.01))
    assert (await registry.execute("missing", "{}")).error == "unknown_tool"
    assert (await registry.execute("slow", "not json")).error == "invalid_arguments"
    assert (await registry.execute("slow", '{"expression":"2","extra":true}')).error == "invalid_arguments"
    assert (await registry.execute("slow", '{"expression":"2"}')).error == "tool_timeout"
    schema = registry.schemas()[0]["function"]
    assert schema["strict"] and schema["parameters"]["additionalProperties"] is False


async def test_search_falls_back_when_tavily_times_out():
    hosts = []
    def respond(request):
        hosts.append(request.url.host)
        if request.url.host == "api.tavily.com":
            raise httpx.ReadTimeout("offline test")
        return httpx.Response(200, json={"Heading": "Exemple", "AbstractText": "Fait lu",
                                        "AbstractURL": "https://example.org/source"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await WebSearch(client, "fake-test-key")(SearchArgs(query="histoire du Senegal"))
    assert result.ok and result.data["limited_coverage"]
    assert result.data["sources"][0]["url"] == "https://example.org/source"
    assert hosts == ["api.tavily.com", "api.duckduckgo.com"]


async def test_empty_search_is_never_success():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))) as client:
        result = await WebSearch(client)(SearchArgs(query="question"))
    assert not result.ok and result.error == "no_sources"


async def test_sqlite_preserves_entire_message_and_isolates_users(settings):
    ai = ScriptedAI()
    memory = MemoryEngine(settings, ai)
    conversation = str(uuid4())
    text = "long " * 1000 + "Le dernier montant est 987654 FCFA."
    assert await memory.remember("alice", conversation, text, "Reponse")
    restored = MemoryEngine(settings, ai)
    context = await restored.context("alice", conversation, "987654")
    assert context.history[0]["content"] == text
    assert any("987654" in item["content"] for item in context.memories)
    other = await restored.context("bob", conversation, "987654")
    assert other.history == [] and other.memories == []


async def test_extraction_restarts_and_requires_verbatim_user_evidence(settings):
    ai = ScriptedAI(facts=["Je prefere le francais.", "Le modele a invente ceci."])
    memory = MemoryEngine(settings, ai)
    await memory.remember("owner", "one", "Je prefere le francais.", "Le modele a invente ceci.")
    restarted = MemoryEngine(settings, ai)
    await restarted.drain()
    with sqlite3.connect(settings.db_path) as db:
        facts = db.execute("SELECT content FROM autonomous_documents WHERE kind='user_fact'").fetchall()
        assert facts == [("Je prefere le francais.",)]
        assert db.execute("SELECT count(*) FROM autonomous_memory_jobs").fetchone()[0] == 0
    await restarted.remember("owner", "two", "Je prefere le francais.", "Compris")
    await restarted.drain()
    with sqlite3.connect(settings.db_path) as db:
        assert db.execute("SELECT count(*) FROM autonomous_documents WHERE kind='user_fact'").fetchone()[0] == 1


async def test_memory_failure_returns_warning_without_losing_answer(settings):
    blocked = settings.model_copy(update={"db_path": settings.db_path.parent})
    memory = MemoryEngine(blocked, ScriptedAI())
    assert (await memory.context("owner", "one", "bonjour")).warnings == ["memory_unavailable"]
    assert not await memory.remember("owner", "one", "bonjour", "salut")


async def test_chroma_persistence_and_owner_filter(settings):
    ai = ScriptedAI(embeddings=True)
    memory = MemoryEngine(settings, ai)
    await memory.remember("alice", "one", "Les panneaux arrivent jeudi.", "Recu")
    await memory.remember("bob", "one", "Secret de bob", "Recu bob")
    await memory.drain()
    restored = MemoryEngine(settings, ai)
    context = await restored.context("alice", "new", "livraison")
    assert not context.warnings
    assert any("panneaux" in row["content"] for row in context.memories)
    assert all("bob" not in row["content"] for row in context.memories)
    assert list(settings.chroma_path.iterdir())


async def test_chroma_failure_falls_back_to_sqlite(settings, monkeypatch):
    memory = MemoryEngine(settings, ScriptedAI(embeddings=True))
    await memory.remember("owner", "one", "Mon tarif est 12000", "Compris")
    def broken():
        raise RuntimeError("index unavailable")
    monkeypatch.setattr(memory, "_chroma", broken)
    await memory.drain()
    context = await memory.context("owner", "one", "tarif")
    assert context.history and context.memories
    assert "semantic_memory_unavailable_using_sqlite" in context.warnings


def tool_call(name="calculate", arguments='{"expression":"6*7"}', identity="call1"):
    return {"role": "assistant", "tool_calls": [{"id": identity, "type": "function", "function": {
        "name": name, "arguments": arguments}}]}


async def test_orchestrator_passes_real_tool_result_then_remembers(settings):
    ai = ScriptedAI([tool_call(), {"content": "Le resultat est 42."}])
    memory = MemoryEngine(settings, ai)
    async with httpx.AsyncClient() as http:
        orchestrator = Orchestrator(settings, ai, memory, builtin_registry(http))
        request = ChatInput(message="Calcule 6*7")
        result = await orchestrator.run(CurrentUser(id="owner"), request)
    assert result.memory_saved and result.iterations == 2
    assert result.tools[0].ok and "42" in result.response
    tool_message = ai.calls[1][0][-1]
    assert tool_message["role"] == "tool" and tool_message["tool_call_id"] == "call1"
    assert json.loads(tool_message["content"])["data"]["value"] == 42
    context = await memory.context("owner", request.conversation_id, "resultat")
    assert context.history[-1]["content"] == "Le resultat est 42."


async def test_five_turn_limit_and_invalid_tool_recoverability(settings):
    ai = ScriptedAI([tool_call("unknown", identity=str(i)) for i in range(5)])
    async with httpx.AsyncClient() as http:
        orchestrator = Orchestrator(settings, ai, MemoryEngine(settings, ai), builtin_registry(http))
        result = await orchestrator.run(CurrentUser(id="owner"), ChatInput(message="fais le travail"))
    assert len(ai.calls) == 5 and ai.calls[-1][1] is None
    assert len(result.tools) == 4 and result.status == "degraded"
    assert "tool_iteration_limit" in result.warnings


async def test_unavailable_model_is_reported_and_question_retained(settings):
    ai = ScriptedAI()
    async with httpx.AsyncClient() as http:
        orchestrator = Orchestrator(settings, ai, MemoryEngine(settings, ai), builtin_registry(http))
        result = await orchestrator.run(CurrentUser(id="owner"), ChatInput(message="bonjour"))
    assert result.status == "unavailable" and result.memory_saved
    assert "indisponible" in result.response


async def test_same_conversation_is_serialized(settings):
    ai = ScriptedAI([{"content": "Premiere reponse"}, {"content": "Deuxieme reponse"}])
    async with httpx.AsyncClient() as http:
        orchestrator = Orchestrator(settings, ai, MemoryEngine(settings, ai), builtin_registry(http))
        conversation = str(uuid4())
        await asyncio.gather(*[orchestrator.run(CurrentUser(id="owner"), ChatInput(
            message=f"message {i}", conversation_id=conversation)) for i in range(2)])
    assert any(m.get("content") == "Premiere reponse" for m in ai.calls[1][0])
    assert not orchestrator._sessions


def test_authenticated_endpoint_and_strict_body(settings, monkeypatch):
    monkeypatch.setattr(security, "USMAN_API_KEY", "test-owner-only")
    ai = ScriptedAI([{"content": "Bonjour"}])
    http = httpx.AsyncClient()
    memory = MemoryEngine(settings, ai)
    runtime = SimpleNamespace(memory=memory, orchestrator=Orchestrator(settings, ai, memory, builtin_registry(http)))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_runtime] = lambda: runtime
    with TestClient(app) as client:
        assert client.post("/api/v1/chat", json={"message": "salut"}).status_code == 401
        headers = {"Authorization": "Bearer test-owner-only"}
        assert client.post("/api/v1/chat", json={"message": "salut", "user_id": "victim"},
                           headers=headers).status_code == 422
        assert client.post("/api/v1/chat", json={"message": " ", "conversation_id": "wrong"},
                           headers=headers).status_code == 422
        response = client.post("/api/v1/chat", json={"message": "salut"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["response"] == "Bonjour"
    asyncio.run(http.aclose())


async def test_sdk_local_only_uses_local_embeddings_without_cloud(settings, monkeypatch):
    ai = AIClient(settings.model_copy(update={"openai_key": "cloud-key", "mode": "LOCAL_ONLY"}))
    used = []

    async def local_embeddings(texts, base_url, modele, timeout):
        used.append(("embed", base_url, modele, list(texts)))
        return [[1.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr("apps.backend.services.ai_client.embeddings_ollama", local_embeddings)
    from openai import AsyncOpenAI

    def respond(request):
        used.append(("chat", request.url.host))
        return httpx.Response(200, json={
            "id": "test", "object": "chat.completion", "created": 0, "model": "local",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "Local"}}],
        })

    ai._clients["local"] = AsyncOpenAI(
        api_key="ollama", base_url="http://localhost:11434/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    result = await ai.complete([{"role": "user", "content": "Bonjour"}], force_local=True)
    vectors = await ai.embed(["Bonjour"])
    await ai.close()

    assert result["content"] == "Local"
    assert vectors == [[1.0, 0.0, 0.0]]
    assert ("embed", settings.local_url, settings.local_embedding_model, ["Bonjour"]) in used
    assert all("api.openai.com" not in str(item) for item in used)


async def test_existing_owner_memory_is_retrieved_but_never_shared(settings):
    legacy = MemoirePersonnelle(str(settings.db_path))
    legacy.retenir(contenu="Mon tarif BA13 est 12000 FCFA.", type=TypeSouvenir.SEMANTIQUE,
                   nature=Nature.FAIT, source="devis existant")
    memory = MemoryEngine(settings, ScriptedAI(), legacy_memory=legacy)
    owner = await memory.context("owner", "new", "Quel est mon tarif BA13 ?")
    other = await memory.context("someone_else", "new", "Quel est mon tarif BA13 ?")
    assert any("12000" in row["content"] for row in owner.memories)
    assert not other.memories


async def test_failed_extraction_has_bounded_retries_and_keeps_source(settings):
    class BrokenExtraction(ScriptedAI):
        async def complete(self, *args, **kwargs):
            raise AIUnavailable("test: unavailable")
    memory = MemoryEngine(settings, BrokenExtraction())
    await memory.remember("owner", "one", "Je prefere le francais.", "Compris.")
    for _ in range(3):
        await memory.drain()
        with sqlite3.connect(settings.db_path) as db:
            db.execute("UPDATE autonomous_memory_jobs SET due=0")
    with sqlite3.connect(settings.db_path) as db:
        assert db.execute("SELECT attempts,status FROM autonomous_memory_jobs").fetchone() == (3, "failed")
        assert db.execute("SELECT count(*) FROM short_term_memory").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM autonomous_documents WHERE kind='user_fact'").fetchone()[0] == 0


async def test_cloud_quota_is_shared_and_falls_back_to_local(settings):
    from openai import AsyncOpenAI
    used = []
    def respond(request):
        used.append(request.url.host)
        return httpx.Response(200, json={"id": "test", "object": "chat.completion", "created": 0,
            "model": "test", "choices": [{"index": 0, "finish_reason": "stop",
                                           "message": {"role": "assistant", "content": "Reponse"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})
    usage = CompteurUsage(requetes_par_jour=1, db_path=str(settings.db_path))
    ai = AIClient(settings.model_copy(update={"mode": "CLOUD_PREFERRED", "openai_key": "test-only"}), usage)
    for kind, url in (("cloud", "https://api.openai.com/v1"), ("local", "http://localhost:11434/v1")):
        ai._clients[kind] = AsyncOpenAI(api_key="test-only", base_url=url,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    try:
        await ai.complete([{"role": "user", "content": "Bonjour"}])
        await ai.complete([{"role": "user", "content": "Salut"}])
    finally:
        await ai.close()
    assert used == ["api.openai.com", "localhost"]
    assert usage.requetes_aujourdhui == 1 and usage.appels_en_vol == 0


async def test_sensitive_legacy_memory_forces_local_inference(settings):
    from core.memory.chiffrement import Coffre
    legacy = MemoirePersonnelle(str(settings.db_path), coffre=Coffre("test-only-passphrase"))
    legacy.retenir(contenu="Mon tarif BA13 est 12000 FCFA.", type=TypeSouvenir.SEMANTIQUE,
                   nature=Nature.FAIT, source="devis", sensible=True)
    memory = MemoryEngine(settings, ScriptedAI(), legacy_memory=legacy)
    context = await memory.context("owner", "new", "Quel est mon tarif BA13 ?")
    assert context.local_only
    assert any("12000" in row["content"] for row in context.memories)
    assert not (await memory.context("someone_else", "new", "tarif BA13")).local_only


async def test_sensitive_exchange_cannot_search_or_persist_decrypted_content(settings):
    from apps.backend.services.memory_engine import MemoryContext
    class SensitiveMemory:
        async def context(self, *args):
            return MemoryContext(local_only=True)
        async def remember(self, *args):
            pytest.fail("Sensitive exchange copied to plaintext storage")
    class SensitiveAI(ScriptedAI):
        async def complete(self, *args, force_local=False, **kwargs):
            assert force_local
            return await super().complete(*args, **kwargs)
    ai = SensitiveAI([
        {"tool_calls": [{"id": "search", "function": {"name": "web_search",
                         "arguments": '{"query":"private material"}'}}]},
        {"content": "Reponse locale"}])
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: pytest.fail("Sensitive content sent over HTTP"))) as http:
        result = await Orchestrator(settings, ai, SensitiveMemory(), builtin_registry(http, "")).run(
            CurrentUser(id="owner"), ChatInput(message="bonjour"))
    assert not result.memory_saved
    assert result.tools[0].error == "sensitive_context_tool_blocked"
    assert "sensitive_exchange_not_persisted" in result.warnings


async def test_local_embedding_failure_keeps_lexical_memory(settings):
    ai = ScriptedAI(embeddings=False)
    memory = MemoryEngine(settings, ai)
    await memory.remember("owner", "one", "Le chantier Medina commence jeudi.", "Compris")
    await memory.drain()
    context = await memory.context("owner", "new", "chantier Medina")
    assert any("Medina" in item["content"] for item in context.memories)
    assert "semantic_memory_unavailable_using_sqlite" in context.warnings


async def test_embedding_model_change_reindexes_without_deleting_sqlite(settings):
    first_settings = settings.model_copy(update={"local_embedding_model": "modele-a"})
    first = MemoryEngine(first_settings, ScriptedAI(embeddings=True))
    await first.remember("owner", "one", "Isolation acoustique en laine de roche.", "Compris")
    await first.drain()

    with sqlite3.connect(first_settings.db_path) as db:
        before = db.execute(
            "SELECT count(*), min(index_space) FROM autonomous_documents"
        ).fetchone()
    assert before[0] > 0 and "modele-a" in before[1]

    second_settings = settings.model_copy(update={"local_embedding_model": "modele-b"})
    second = MemoryEngine(second_settings, ScriptedAI(embeddings=True))
    # Le nouvel espace doit reprendre les mêmes sources, sans effacer SQLite.
    await second.drain()

    with sqlite3.connect(second_settings.db_path) as db:
        rows = db.execute(
            "SELECT content,indexed,index_space FROM autonomous_documents"
        ).fetchall()
    assert rows
    assert all(row[1] == 1 and "modele-b" in row[2] for row in rows)
    assert any("laine de roche" in row[0] for row in rows)


async def test_interrupted_local_indexing_is_recoverable(settings):
    class FlakyEmbeddingAI(ScriptedAI):
        def __init__(self):
            super().__init__(embeddings=True)
            self.fail_once = True

        async def embed(self, texts):
            if self.fail_once:
                self.fail_once = False
                raise AIUnavailable("local embeddings temporarily unavailable")
            return await super().embed(texts)

    ai = FlakyEmbeddingAI()
    memory = MemoryEngine(settings, ai)
    await memory.remember("owner", "one", "Montant durable 76543 FCFA.", "Compris")
    await memory.drain()

    with sqlite3.connect(settings.db_path) as db:
        source_count = db.execute("SELECT count(*) FROM autonomous_documents").fetchone()[0]
        indexed = db.execute("SELECT sum(indexed) FROM autonomous_documents").fetchone()[0]
        db.execute("UPDATE autonomous_documents SET index_after=0")

    assert source_count > 0
    assert not indexed

    await memory.drain()
    with sqlite3.connect(settings.db_path) as db:
        rows = db.execute(
            "SELECT indexed,index_space,content FROM autonomous_documents"
        ).fetchall()
    assert all(row[0] == 1 and row[1] for row in rows)
    assert any("76543" in row[2] for row in rows)


async def test_local_semantic_restart_preserves_owner_isolation(settings):
    ai = ScriptedAI(embeddings=True)
    first = MemoryEngine(settings, ai)
    await first.remember("alice", "one", "Panneaux phoniques livraison vendredi.", "Reçu")
    await first.remember("bob", "one", "Secret bob 999.", "Reçu")
    await first.drain()

    restarted = MemoryEngine(settings, ai)
    alice = await restarted.context("alice", "new", "livraison panneaux")
    bob = await restarted.context("bob", "new", "livraison panneaux")

    assert any("Panneaux" in item["content"] for item in alice.memories)
    assert all("Secret bob" not in item["content"] for item in alice.memories)
    assert all("Panneaux" not in item["content"] for item in bob.memories)
