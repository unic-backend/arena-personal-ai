"""Compréhension conversationnelle déterministe et locale.

Le module privilégie la précision : une mémoire douteuse est rejetée plutôt
qu'injectée. Il ne produit ni ne conserve de chaîne de pensée privée.
"""
from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal

TopicRelation = Literal["CONTINUATION", "TOPIC_SHIFT", "TOPIC_RETURN", "AMBIGUOUS"]

_STOP = {
    "avec", "dans", "pour", "mais", "donc", "alors", "comme", "cette", "celui",
    "celle", "ceci", "cela", "quoi", "quel", "quelle", "comment", "pourquoi",
    "est", "sont", "des", "les", "une", "un", "mon", "ma", "mes", "ton", "ta",
    "tes", "son", "sa", "ses", "notre", "votre", "leur", "leurs", "plus", "pas",
    "que", "qui", "sur", "par", "aux", "the", "and", "this", "that", "what",
}
_REFERENCES = re.compile(
    r"\b(?:il|elle|ils|elles|lui|ça|ca|ceci|cela|celui|celle|celui-ci|celle-ci|"
    r"l'autre|le premier|la première|le second|la seconde|ce projet|cette vidéo|"
    r"cette video|ce modèle|ce modele|the other one|the first one|the previous one)\b",
    re.IGNORECASE,
)
_RETURN = re.compile(r"\b(?:revenons?|retournons?|reviens?|reprends?|je parle de|celui de|pas l'autre|plus tôt|plus tot|avant)\b", re.I)
_ENTITY = re.compile(r"\b(?:[A-ZÀ-ÖØ-Ý][\wÀ-ÿ.-]{2,}|RTX\s*A?\d{3,4}|Qwen[\w.-]*|Wan[\w.-]*|BMW)\b")


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[\wÀ-ÿ-]{3,}", (text or "").casefold()) if w not in _STOP}


def overlap(a: str, b: str) -> float:
    left, right = tokens(a), tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left | right))


def entities(text: str) -> list[str]:
    seen: list[str] = []
    for item in _ENTITY.findall(text or ""):
        normalized = item.strip()
        if normalized.casefold() not in {x.casefold() for x in seen}:
            seen.append(normalized)
    return seen[-8:]


@dataclass
class ConversationState:
    active_topic: str = ""
    previous_topics: list[str] = field(default_factory=list)
    active_entities: list[str] = field(default_factory=list)
    relation: TopicRelation = "AMBIGUOUS"
    resolved_references: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0

    def debug(self) -> dict[str, Any]:
        return {
            "active_topic": self.active_topic,
            "previous_topics": self.previous_topics[-4:],
            "active_entities": self.active_entities,
            "relation": self.relation,
            "resolved_references": self.resolved_references,
            "confidence": round(self.confidence, 3),
        }


def understand(message: str, history: list[dict[str, str]]) -> ConversationState:
    recent_users = [m.get("content", "") for m in history if m.get("role") == "user"][-8:]
    current_entities = entities(message)
    candidates = list(reversed(recent_users))
    scored = [(overlap(message, candidate), candidate) for candidate in candidates]
    best_score, best = max(scored, default=(0.0, ""), key=lambda x: x[0])
    latest = recent_users[-1] if recent_users else ""
    latest_score = overlap(message, latest)

    if _RETURN.search(message) and best:
        relation: TopicRelation = "TOPIC_RETURN"
        topic = best
        confidence = max(0.72, best_score)
    elif latest and (latest_score >= 0.12 or _REFERENCES.search(message)):
        relation = "CONTINUATION"
        topic = latest
        confidence = max(0.65, latest_score)
    elif recent_users and current_entities and not any(
        entity.casefold() in latest.casefold() for entity in current_entities
    ):
        relation = "TOPIC_SHIFT"
        topic = message
        confidence = 0.72
    elif recent_users:
        relation = "AMBIGUOUS"
        topic = latest
        confidence = 0.45
    else:
        relation = "CONTINUATION"
        topic = message
        confidence = 0.7

    active = current_entities or entities(topic)
    resolved: dict[str, str] = {}
    refs = _REFERENCES.findall(message)
    if refs and active:
        # Une seule entité récente est un cas sûr. Plusieurs restent ambigües.
        unique = list(dict.fromkeys(x.casefold() for x in active))
        if len(unique) == 1:
            for ref in refs:
                resolved[ref.casefold()] = active[-1]

    previous = [item for item in recent_users if item != topic][-4:]
    return ConversationState(topic[:500], previous, active, relation, resolved, confidence)


@dataclass
class MemoryCandidate:
    item: dict[str, Any]
    lexical: float
    entity: float
    topic: float
    recency: float
    score: float
    accepted: bool
    reason: str


def rank_memory(
    query: str,
    state: ConversationState,
    candidates: list[dict[str, Any]],
    *,
    lexical_weight: float = 0.35,
    entity_weight: float = 0.30,
    topic_weight: float = 0.25,
    recency_weight: float = 0.10,
    threshold: float = 0.22,
    limit: int = 6,
) -> list[MemoryCandidate]:
    ranked: list[MemoryCandidate] = []
    query_entities = {x.casefold() for x in state.active_entities}
    now = time.time()
    for item in candidates:
        content = str(item.get("content") or "")
        lex = overlap(query, content)
        item_entities = {x.casefold() for x in entities(content)}
        entity_score = (len(query_entities & item_entities) / len(query_entities)) if query_entities else 0.0
        topic_score = overlap(state.active_topic, content) if state.active_topic else 0.0
        created = float(item.get("created") or now)
        age_days = max(0.0, (now - created) / 86400)
        recency = math.exp(-age_days / 30.0)
        score = lex * lexical_weight + entity_score * entity_weight + topic_score * topic_weight + recency * recency_weight
        mismatch = bool(query_entities and item_entities and not (query_entities & item_entities))
        accepted = score >= threshold and not (mismatch and lex < 0.20 and topic_score < 0.20)
        reason = "accepted" if accepted else "entity_mismatch" if mismatch else "below_threshold"
        ranked.append(MemoryCandidate(item, lex, entity_score, topic_score, recency, score, accepted, reason))
    ranked.sort(key=lambda x: x.score, reverse=True)
    return ranked[:limit]


def needs_long_term(message: str, history: list[dict[str, str]], state: ConversationState) -> bool:
    """Évite une recherche globale lorsque le fil récent suffit manifestement."""
    if not history:
        return True
    if _REFERENCES.search(message) and state.resolved_references:
        return False
    recent = " ".join(m.get("content", "") for m in history[-6:])
    if overlap(message, recent) >= 0.10:
        return False
    return state.relation in {"TOPIC_RETURN", "AMBIGUOUS"} or bool(state.active_entities)
