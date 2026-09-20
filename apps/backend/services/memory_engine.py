"""Memoire hybride : SQLite durable, projection Chroma et extraction reprise.

La mémoire longue est désormais filtrée par le contexte conversationnel avant
d'être exposée au modèle. SQLite reste la source de vérité et l'isolation par
utilisateur reste obligatoire.
"""
import asyncio
import hashlib
import json
import logging
import sqlite3
import threading
import time
from contextlib import closing
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from apps.backend.services.ai_client import AIClient
from apps.backend.services.conversation_intelligence import (
    ConversationState,
    accept_memory,
    classify_user_evidence,
    needs_long_term,
    score_memory,
    tokens,
    understand,
)
from apps.backend.services.settings import AutonomousSettings
from core.memory.memory_manager import MemoryManager
from core.memory.personnelle import MemoirePersonnelle
from core.memory.recuperation import recuperer

logger = logging.getLogger("usman.autonomous.memory")


class ExtractedFact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    evidence: str = Field(min_length=3, max_length=1500)


class FactExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    facts: list[ExtractedFact] = Field(max_length=12)


class MemoryContext(BaseModel):
    history: list[dict[str, str]] = Field(default_factory=list)
    memories: list[dict[str, Any]] = Field(default_factory=list)
    profile: str = ""
    warnings: list[str] = Field(default_factory=list)
    local_only: bool = False
    conversation_state: dict[str, Any] = Field(default_factory=dict)
    retrieval_debug: list[dict[str, Any]] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    long_term_used: bool = False


def session_key(user_id: str, conversation_id: str) -> str:
    digest = hashlib.sha256(json.dumps([user_id, conversation_id]).encode()).hexdigest()
    return f"autonomous:{digest}"


class MemoryEngine:
    def __init__(self, settings: AutonomousSettings, ai: AIClient,
                 legacy_memory: MemoirePersonnelle | None = None):
        self.settings, self.ai = settings, ai
        self.legacy_memory = legacy_memory
        self._ready = False
        self._init_lock = asyncio.Lock()
        self._drain_lock = asyncio.Lock()
        self._collection: Any = None
        self._chroma_lock = threading.Lock()
        self._index_space = self._embedding_space()
        self._semantic_available = True

    def _embedding_space(self) -> str:
        identite = getattr(self.ai, "embedding_space", None)
        if callable(identite):
            return str(identite())
        return f"ollama|{self.settings.local_embedding_model}|{self.settings.local_url.rstrip('/')}"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.settings.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        MemoryManager(str(self.settings.db_path))
        with closing(self._connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS autonomous_documents (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL, kind TEXT NOT NULL,
                    content TEXT NOT NULL, source TEXT NOT NULL,
                    created REAL NOT NULL, indexed INTEGER NOT NULL DEFAULT 0,
                    index_after REAL NOT NULL DEFAULT 0,
                    index_space TEXT NOT NULL DEFAULT '',
                    retrievable INTEGER NOT NULL DEFAULT 1,
                    source_type TEXT NOT NULL DEFAULT 'legacy',
                    confidence REAL NOT NULL DEFAULT 1.0,
                    memory_type TEXT NOT NULL DEFAULT 'episodic',
                    status TEXT NOT NULL DEFAULT 'active'
                );
                CREATE INDEX IF NOT EXISTS autonomous_documents_owner
                    ON autonomous_documents(user_id, kind, created);
                CREATE TABLE IF NOT EXISTS autonomous_memory_jobs (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL, question TEXT NOT NULL,
                    answer TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    due REAL NOT NULL, lease TEXT, lease_until REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending'
                );
            """)
            colonnes = {row["name"] for row in db.execute("PRAGMA table_info(autonomous_documents)")}
            migrations = {
                "index_space": "TEXT NOT NULL DEFAULT ''",
                "retrievable": "INTEGER NOT NULL DEFAULT 1",
                "source_type": "TEXT NOT NULL DEFAULT 'legacy'",
                "confidence": "REAL NOT NULL DEFAULT 1.0",
                "memory_type": "TEXT NOT NULL DEFAULT 'episodic'",
                "status": "TEXT NOT NULL DEFAULT 'active'",
            }
            for colonne, definition in migrations.items():
                if colonne not in colonnes:
                    db.execute(f"ALTER TABLE autonomous_documents ADD COLUMN {colonne} {definition}")
            db.execute(
                "CREATE INDEX IF NOT EXISTS autonomous_documents_retrieval "
                "ON autonomous_documents(user_id,retrievable,status,kind,created)"
            )
            # Migration non destructive : les messages restent stockes, mais
            # seules les preuves admissibles restent candidates a la memoire longue.
            legacy_rows = db.execute(
                "SELECT id,kind,content FROM autonomous_documents WHERE source_type='legacy'"
            ).fetchall()
            for row in legacy_rows:
                kind = row["kind"]
                if kind == "assistant_message":
                    policy = {"eligible": False, "source_type": "assistant_output", "confidence": 0.0}
                    memory_type = "assistant_output"
                elif kind in {"user_message", "user_fact"}:
                    policy = classify_user_evidence(row["content"])
                    memory_type = "semantic" if kind == "user_fact" else "episodic"
                else:
                    continue
                db.execute(
                    "UPDATE autonomous_documents SET retrievable=?,source_type=?,confidence=?,memory_type=? "
                    "WHERE id=?",
                    (
                        1 if policy["eligible"] else 0,
                        policy["source_type"],
                        float(policy["confidence"]),
                        memory_type,
                        row["id"],
                    ),
                )
            db.execute("UPDATE autonomous_documents SET index_after=0 WHERE indexed=1 AND index_space<>?",
                       (self._index_space,))

    async def initialize(self) -> None:
        async with self._init_lock:
            if not self._ready:
                await asyncio.to_thread(self._initialize)
                self._ready = True

    def _chroma(self) -> Any:
        with self._chroma_lock:
            if self._collection is None:
                import chromadb
                from chromadb.config import Settings
                client = chromadb.PersistentClient(
                    path=str(self.settings.chroma_path), settings=Settings(anonymized_telemetry=False))
                model_key = hashlib.sha256(self._index_space.encode()).hexdigest()[:12]
                self._collection = client.get_or_create_collection(
                    name=f"arena_{model_key}", embedding_function=None,
                    metadata={"hnsw:space": "cosine", "embedding_space": self._index_space})
                if self._collection.count() == 0:
                    with closing(self._connect()) as db, db:
                        db.execute("UPDATE autonomous_documents SET indexed=0, index_after=0 WHERE index_space=?",
                                   (self._index_space,))
        return self._collection

    def _history(self, user_id: str, conversation_id: str) -> list[dict[str, str]]:
        memory = MemoryManager(str(self.settings.db_path))
        return memory.get_recent_history(session_key(user_id, conversation_id), self.settings.history_messages)

    @staticmethod
    def _working_candidates(history: list[dict[str, str]], query: str) -> list[dict[str, Any]]:
        """Recent user evidence, without querying global/long-term memory."""
        query_folded = (query or "").casefold()
        query_words = {word for word in query_folded.split() if len(word) >= 3}
        result: list[dict[str, Any]] = []
        for item in reversed(history[-8:]):
            if item.get("role") != "user":
                continue
            content = str(item.get("content") or "")
            folded = content.casefold()
            lexical_hit = any(word in folded for word in query_words)
            direct_hit = bool(query_folded and query_folded in folded)
            if lexical_hit or direct_hit:
                result.append({
                    "kind": "working_user_message",
                    "content": content,
                    "source": "working_context",
                    "created": time.time(),
                    "conversation_id": "current",
                    "relevance": 1.0,
                })
        return result[:5]

    def _lexical_candidates(self, user_id: str, query: str) -> list[dict[str, Any]]:
        words = sorted(tokens(query))[:12]
        if not words:
            return []
        conditions = " OR ".join("instr(lower(content), ?) > 0" for _ in words)
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT id,conversation_id,kind,content,source,created,source_type,confidence,memory_type,status "
                "FROM autonomous_documents WHERE user_id=? AND retrievable=1 AND status='active' AND ("
                + conditions + ") ORDER BY created DESC LIMIT ?",
                [user_id, *words, self.settings.retrieval_top_k],
            ).fetchall()
        return [dict(row) for row in rows]

    def _query_vectors(self, user_id: str, vector: list[float]) -> list[dict[str, Any]]:
        response = self._chroma().query(
            query_embeddings=[vector], n_results=self.settings.retrieval_top_k,
            where={"user_id": user_id}, include=["distances"],
        )
        ids = (response.get("ids") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]
        distance_by_id = {doc_id: float(distance) for doc_id, distance in zip(ids, distances, strict=False)}
        with closing(self._connect()) as db:
            result = []
            for document_id in ids:
                row = db.execute(
                    "SELECT id,conversation_id,kind,content,source,created,source_type,confidence,memory_type,status "
                    "FROM autonomous_documents WHERE id=? AND user_id=? AND retrievable=1 AND status='active'",
                    (document_id, user_id)).fetchone()
                if row:
                    item = dict(row)
                    item["semantic_score"] = max(0.0, 1.0 - distance_by_id.get(document_id, 1.0))
                    result.append(item)
        return result

    def _rerank(self, query: str, conversation_id: str, state: ConversationState,
                candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        weights = {
            "semantic": self.settings.semantic_weight,
            "lexical": self.settings.lexical_weight,
            "entity": self.settings.entity_weight,
            "topic": self.settings.topic_weight,
            "recency": self.settings.recency_weight,
            "conversation": self.settings.conversation_weight,
        }
        accepted, debug = [], []
        for candidate in candidates:
            features = score_memory(
                query, candidate, state, candidate.get("semantic_score"),
                same_conversation=candidate.get("conversation_id") == conversation_id,
                weights=weights,
            )
            ok = accept_memory(features, self.settings.relevance_threshold)
            debug.append({
                "memory_id": candidate.get("id"),
                "kind": candidate.get("kind"),
                "source_type": candidate.get("source_type"),
                "memory_type": candidate.get("memory_type"),
                "confidence": round(float(candidate.get("confidence", 1.0)), 3),
                "source": candidate.get("source"),
                "conversation_id": candidate.get("conversation_id"),
                "created": candidate.get("created"),
                "score": round(features["score"], 3),
                "semantic": round(features["semantic"], 3),
                "lexical": round(features["lexical"], 3),
                "entity": round(features["entity"], 3),
                "topic": round(features["topic"], 3),
                "same_conversation": features["same_conversation"],
                "status": "ACCEPTED" if ok else "REJECTED",
            })
            if ok:
                accepted.append({**candidate, "relevance": features["score"]})
        accepted.sort(key=lambda row: (float(row.get("relevance", 0)), float(row.get("created", 0))), reverse=True)
        return accepted[:self.settings.rerank_top_k], debug

    async def context(self, user_id: str, conversation_id: str, query: str) -> MemoryContext:
        total_started = time.perf_counter()
        timings: dict[str, float] = {}
        try:
            history_started = time.perf_counter()
            await self.initialize()
            history = await asyncio.to_thread(self._history, user_id, conversation_id)
            timings["history_load"] = (time.perf_counter() - history_started) * 1000
        except Exception:
            logger.warning("Memoire SQLite indisponible; contexte non charge.")
            return MemoryContext(
                warnings=["memory_unavailable"],
                timings_ms={"total_memory": (time.perf_counter() - total_started) * 1000},
            )

        understanding_started = time.perf_counter()
        state = understand(
            query,
            history,
            recent_window=self.settings.recent_context_window,
        )
        timings["conversation_understanding"] = (time.perf_counter() - understanding_started) * 1000

        memory = MemoryManager(str(self.settings.db_path))
        result = MemoryContext(
            history=history,
            conversation_state=state.as_debug(),
            profile=str(memory.get_fact("owner") or "") if user_id == "owner" else "",
            timings_ms=timings,
        )
        if not self._semantic_available:
            result.warnings.append("semantic_memory_unavailable_using_sqlite")

        if not needs_long_term(query, history, state):
            working_started = time.perf_counter()
            result.memories = self._working_candidates(history, query)
            timings["working_memory"] = (time.perf_counter() - working_started) * 1000
            if self.settings.memory_debug:
                result.retrieval_debug.append({
                    "status": "SKIPPED",
                    "reason": "recent_context_sufficient",
                    "working_evidence": len(result.memories),
                })
            timings["total_memory"] = (time.perf_counter() - total_started) * 1000
            return result

        result.long_term_used = True
        lexical_started = time.perf_counter()
        candidates = await asyncio.to_thread(self._lexical_candidates, user_id, query)
        timings["lexical_retrieval"] = (time.perf_counter() - lexical_started) * 1000
        by_id = {row["id"]: row for row in candidates}

        try:
            embedding_started = time.perf_counter()
            async with asyncio.timeout(min(5, self.settings.timeout)):
                vectors = await self.ai.embed([query])
            timings["embedding"] = (time.perf_counter() - embedding_started) * 1000

            vector_started = time.perf_counter()
            semantic = await asyncio.to_thread(self._query_vectors, user_id, vectors[0])
            timings["vector_retrieval"] = (time.perf_counter() - vector_started) * 1000
            self._semantic_available = True
            for row in semantic:
                previous = by_id.get(row["id"])
                if previous:
                    previous["semantic_score"] = row.get("semantic_score", 0.0)
                else:
                    by_id[row["id"]] = row
        except Exception:
            self._semantic_available = False
            if "semantic_memory_unavailable_using_sqlite" not in result.warnings:
                result.warnings.append("semantic_memory_unavailable_using_sqlite")

        rerank_started = time.perf_counter()
        memories, debug = self._rerank(query, conversation_id, state, list(by_id.values()))
        timings["rerank"] = (time.perf_counter() - rerank_started) * 1000
        result.memories = memories
        if self.settings.memory_debug:
            result.retrieval_debug = debug

        # La mémoire legacy propriétaire reste un fallback séparé et local-only,
        # mais ne contourne jamais la priorité du contexte de conversation.
        if user_id == "owner" and self.legacy_memory is not None and len(result.memories) < self.settings.rerank_top_k:
            try:
                legacy_started = time.perf_counter()
                legacy_hits = recuperer(self.legacy_memory, query, budget_caracteres=1200)
                result.local_only = any(item.souvenir.sensible for item in legacy_hits)
                for item in legacy_hits:
                    candidate = {
                        "kind": item.souvenir.nature.value,
                        "content": item.souvenir.contenu,
                        "source": item.souvenir.source,
                        "source_type": "legacy_memory",
                        "memory_type": "semantic",
                        "confidence": 0.8,
                        "created": 0.0,
                        "conversation_id": "legacy",
                    }
                    accepted, legacy_debug = self._rerank(query, conversation_id, state, [candidate])
                    if accepted:
                        result.memories.extend(accepted)
                    if self.settings.memory_debug:
                        result.retrieval_debug.extend(legacy_debug)
                timings["legacy_retrieval"] = (time.perf_counter() - legacy_started) * 1000
            except Exception:
                result.warnings.append("legacy_memory_unavailable")
        result.memories = result.memories[:self.settings.rerank_top_k]
        timings["total_memory"] = (time.perf_counter() - total_started) * 1000
        return result

    @staticmethod
    def _document(
        db: sqlite3.Connection,
        user_id: str,
        conversation_id: str,
        kind: str,
        content: str,
        source: str,
        *,
        retrievable: bool = True,
        source_type: str = "legacy",
        confidence: float = 1.0,
        memory_type: str = "episodic",
        status: str = "active",
    ) -> None:
        for offset in range(0, len(content), 1500):
            chunk = content[offset:offset + 1500]
            identity = [user_id, kind, chunk.strip().casefold()]
            if kind != "user_fact":
                identity.extend([source, offset])
            key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
            db.execute(
                "INSERT OR IGNORE INTO autonomous_documents "
                "(id,user_id,conversation_id,kind,content,source,created,retrievable,"
                "source_type,confidence,memory_type,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    key,
                    user_id,
                    conversation_id,
                    kind,
                    chunk,
                    source,
                    time.time(),
                    1 if retrievable else 0,
                    source_type,
                    float(confidence),
                    memory_type,
                    status,
                ),
            )

    def _save(self, user_id: str, conversation_id: str, question: str, answer: str) -> None:
        job = uuid4().hex
        policy = classify_user_evidence(question)
        with closing(self._connect()) as db, db:
            for role, content in (("user", question), ("assistant", answer)):
                db.execute(
                    "INSERT INTO short_term_memory(session_id,role,content) VALUES (?,?,?)",
                    (session_key(user_id, conversation_id), role, content),
                )
                if role == "user":
                    self._document(
                        db,
                        user_id,
                        conversation_id,
                        "user_message",
                        content,
                        job,
                        retrievable=bool(policy["eligible"]),
                        source_type=str(policy["source_type"]),
                        confidence=float(policy["confidence"]),
                        memory_type="episodic",
                    )
                else:
                    self._document(
                        db,
                        user_id,
                        conversation_id,
                        "assistant_message",
                        content,
                        job,
                        retrievable=False,
                        source_type="assistant_output",
                        confidence=0.0,
                        memory_type="assistant_output",
                    )
            db.execute(
                "INSERT INTO autonomous_memory_jobs "
                "(id,user_id,conversation_id,question,answer,due) VALUES (?,?,?,?,?,?)",
                (job, user_id, conversation_id, question, answer, time.time()),
            )

    async def remember(self, user_id: str, conversation_id: str, question: str, answer: str) -> bool:
        try:
            await self.initialize()
            await asyncio.to_thread(self._save, user_id, conversation_id, question, answer)
            return True
        except Exception:
            logger.warning("Echange non sauvegarde dans la memoire.")
            return False

    def _claim(self) -> dict[str, Any] | None:
        now, lease = time.time(), uuid4().hex
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM autonomous_memory_jobs WHERE status='pending' AND due<=? "
                             "AND lease_until<=? ORDER BY due LIMIT 1", (now, now)).fetchone()
            if not row:
                return None
            db.execute("UPDATE autonomous_memory_jobs SET lease=?, lease_until=? WHERE id=?",
                       (lease, now + 300, row["id"]))
            return {**dict(row), "lease": lease}

    def _finish(self, job: dict[str, Any], facts: list[ExtractedFact] | None) -> None:
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            live = db.execute("SELECT lease FROM autonomous_memory_jobs WHERE id=?", (job["id"],)).fetchone()
            if not live or live["lease"] != job["lease"]:
                return
            if facts is not None:
                for fact in facts:
                    policy = classify_user_evidence(fact.evidence)
                    if fact.evidence in job["question"] and policy["eligible"]:
                        self._document(
                            db,
                            job["user_id"],
                            job["conversation_id"],
                            "user_fact",
                            fact.evidence,
                            job["id"],
                            retrievable=True,
                            source_type=str(policy["source_type"]),
                            confidence=float(policy["confidence"]),
                            memory_type="semantic",
                        )
                db.execute("DELETE FROM autonomous_memory_jobs WHERE id=?", (job["id"],))
            else:
                attempts = job["attempts"] + 1
                db.execute("UPDATE autonomous_memory_jobs SET attempts=?,due=?,lease=NULL,lease_until=0,status=? WHERE id=?",
                           (attempts, time.time() + 30 * attempts, "failed" if attempts >= 3 else "pending", job["id"]))

    async def _extract(self, job: dict[str, Any]) -> None:
        try:
            response = await self.ai.complete([
                {"role": "system", "content": (
                    'Extrais au plus 12 informations durables explicitement affirmees par utilisateur : '
                    'preferences, identite, decisions, projets, contraintes et taches durables. Ignore salutations, '
                    'questions, hypotheses, citations de tiers, bruit temporaire et affirmations de assistant. '
                    'Retourne JSON {"facts":[{"evidence":"citation exacte utilisateur"}]}. Si rien : {"facts":[]}')},
                {"role": "user", "content": json.dumps({"utilisateur": job["question"], "assistant": job["answer"]}, ensure_ascii=False)},
            ], json_mode=True)
            parsed = FactExtraction.model_validate_json(response.get("content") or "")
            await asyncio.to_thread(self._finish, job, parsed.facts)
        except Exception:
            await asyncio.to_thread(self._finish, job, None)

    def _unindexed(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as db, db:
            rows = [dict(row) for row in db.execute(
                "SELECT * FROM autonomous_documents WHERE retrievable=1 AND status='active' "
                "AND (indexed=0 OR index_space<>?) AND index_after<=? "
                "ORDER BY index_after,created LIMIT 32", (self._index_space, time.time()))]
            db.executemany("UPDATE autonomous_documents SET index_after=? WHERE id=?",
                           [(time.time() + 60, row["id"]) for row in rows])
            return rows

    def _index(self, rows: list[dict[str, Any]], vectors: list[list[float]]) -> None:
        if len(rows) != len(vectors):
            raise ValueError("Nombre de vecteurs incomplet")
        dimensions = {len(vector) for vector in vectors}
        if not vectors or len(dimensions) != 1 or next(iter(dimensions)) < 2:
            raise ValueError("Vecteurs incompatibles")
        self._chroma().upsert(
            ids=[row["id"] for row in rows], embeddings=vectors,
            documents=[row["content"] for row in rows],
            metadatas=[{
                "user_id": row["user_id"],
                "type": row["kind"],
                "source": row["source"],
                "source_type": row.get("source_type", "legacy"),
                "memory_type": row.get("memory_type", "episodic"),
                "conversation_id": row["conversation_id"],
                "embedding_space": self._index_space,
            } for row in rows],
        )
        with closing(self._connect()) as db, db:
            db.executemany("UPDATE autonomous_documents SET indexed=1,index_space=? WHERE id=?",
                           [(self._index_space, row["id"]) for row in rows])

    async def drain(self) -> None:
        if self._drain_lock.locked():
            return
        async with self._drain_lock:
            try:
                await self.initialize()
                for _ in range(4):
                    job = await asyncio.to_thread(self._claim)
                    if job is None:
                        break
                    await self._extract(job)
                rows = await asyncio.to_thread(self._unindexed)
                if rows:
                    try:
                        vectors = await self.ai.embed([row["content"] for row in rows])
                        await asyncio.to_thread(self._index, rows, vectors)
                        self._semantic_available = True
                    except Exception:
                        self._semantic_available = False
                        logger.warning("Indexation semantique differee; SQLite reste autoritaire.")
            except Exception:
                logger.warning("Worker memoire indisponible; reprise au prochain passage.")

    async def worker(self) -> None:
        while True:
            await asyncio.sleep(self.settings.worker_interval)
            await self.drain()
