"""Compréhension conversationnelle déterministe et garde de pertinence mémoire.

Le but est la précision : le contexte récent gagne sur la mémoire longue et un
souvenir douteux est rejeté plutôt qu'injecté. Aucun raisonnement privé n'est
persisté ici ; uniquement des décisions diagnostiques compactes.
"""
from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

TopicTransition = Literal["CONTINUATION", "TOPIC_SHIFT", "TOPIC_RETURN", "AMBIGUOUS"]

STOPWORDS = {
    "alors", "avec", "avoir", "cette", "comme", "dans", "des", "donc", "elle", "elles",
    "encore", "est", "ils", "mais", "mes", "mon", "nous", "pour", "que", "quel", "quelle",
    "qui", "quoi", "son", "sur", "tes", "ton", "tous", "tout", "une", "vous", "the", "and",
    "this", "that", "what", "why", "from", "pas", "plus", "moi", "toi", "lui",
}
ENTITY_STOPWORDS = {
    "Alors", "Avec", "Cette", "Comme", "Dans", "Donc", "Elle", "Elles", "Encore", "Il", "Ils",
    "Je", "Le", "La", "Les", "Ma", "Mes", "Mon", "Nous", "On", "Pourquoi", "Quel", "Quelle",
    "Quels", "Quelles", "Son", "Ta", "Tes", "Ton", "Tu", "Une", "Un", "Vous",
}
REFERENCE = re.compile(
    r"\b(?:il|elle|ils|elles|ça|ca|ceci|cela|celui|celle|ceux|celles|this|that|it|he|she|they|"
    r"premier|première|deuxième|second|seconde|autre|précédent|precedent|avant|earlier)\b",
    re.IGNORECASE,
)
RETURN = re.compile(
    r"\b(?:revenons?|retournons?|reprenons?|reviens?|retourne|je parle de|celui de|celle de|"
    r"pas l'autre|not the other|back to|earlier)\b", re.IGNORECASE,
)


def tokens(text: str) -> set[str]:
    return {
        word for word in re.findall(r"[\wÀ-ÿ-]{2,}", (text or "").casefold())
        if word not in STOPWORDS and (not word.isdigit() or len(word) >= 2)
    }


def overlap(left: Iterable[str], right: Iterable[str]) -> float:
    a, b = set(left), set(right)
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def recency_score(created: float | None, now: float | None = None) -> float:
    if not created:
        return 0.0
    age_days = max(0.0, ((now or time.time()) - float(created)) / 86400.0)
    return math.exp(-age_days / 30.0)


@dataclass
class ConversationState:
    active_topic: str = ""
    previous_topics: list[str] = field(default_factory=list)
    active_entities: list[str] = field(default_factory=list)
    transition: TopicTransition = "AMBIGUOUS"
    references: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0

    def as_debug(self) -> dict[str, Any]:
        return {
            "active_topic": self.active_topic,
            "previous_topics": self.previous_topics[-5:],
            "active_entities": self.active_entities[-8:],
            "transition": self.transition,
            "references": self.references,
            "confidence": round(self.confidence, 3),
        }


def _entities(text: str) -> list[str]:
    # Entités explicites seulement : noms propres/acronymes/modèles visibles.
    found = re.findall(r"\b(?:[A-ZÀ-ÖØ-Þ][\wÀ-ÿ-]{2,}|[A-Z]{2,}[\w.-]*|[A-Za-z]+\d[\w.-]*)\b", text or "")
    return [item for item in dict.fromkeys(found) if item not in ENTITY_STOPWORDS][:12]


def _reference_entities(recent: list[str]) -> list[str]:
    """Priorise les entités susceptibles d'être l'antécédent d'un pronom.

    Une entité introduite comme complément après « chez » (ex. Orange dans
    « Il travaille chez Orange ») reste suivie, mais passe après un nom propre
    de personne explicite rencontré dans le contexte récent.
    """
    preferred: list[str] = []
    secondary: list[str] = []
    for text in reversed(recent):
        for entity in _entities(text):
            target = secondary if re.search(rf"\bchez\s+{re.escape(entity)}\b", text, re.IGNORECASE) else preferred
            if entity not in preferred and entity not in secondary:
                target.append(entity)
        if len(preferred) >= 3:
            break
    return (preferred + secondary)[:8]


def understand(message: str, history: list[dict[str, str]]) -> ConversationState:
    user_history = [str(item.get("content", "")) for item in history if item.get("role") == "user"]
    recent = user_history[-6:]
    current_tokens = tokens(message)
    scored = [(overlap(current_tokens, tokens(text)), text) for text in recent]
    best_score, best_text = max(scored, default=(0.0, ""), key=lambda pair: pair[0])
    previous_topics = [" ".join(list(tokens(text))[:8]) for text in recent if tokens(text)]

    has_reference = bool(REFERENCE.search(message or ""))
    explicit_return = bool(RETURN.search(message or ""))
    if explicit_return and best_text:
        transition: TopicTransition = "TOPIC_RETURN"
        confidence = max(0.7, best_score)
    elif has_reference and recent:
        transition = "CONTINUATION"
        confidence = 0.75
    elif best_score >= 0.18:
        transition = "CONTINUATION"
        confidence = min(1.0, 0.55 + best_score)
    elif current_tokens and recent:
        transition = "TOPIC_SHIFT"
        confidence = 0.62
    else:
        transition = "AMBIGUOUS"
        confidence = 0.35

    entities = _entities(message)
    if has_reference:
        for entity in _reference_entities(recent):
            if entity not in entities:
                entities.append(entity)
    topic_source = best_text if transition == "TOPIC_RETURN" and best_text else message
    topic = " ".join(sorted(tokens(topic_source))[:8])
    references = {}
    if has_reference:
        candidates = _reference_entities(recent)
        if candidates:
            references["recent_reference"] = candidates[0]
    return ConversationState(topic, previous_topics[-6:], entities[-8:], transition, references, confidence)


def score_memory(query: str, candidate: dict[str, Any], state: ConversationState,
                 semantic_score: float | None = None, *, same_conversation: bool = False,
                 weights: dict[str, float] | None = None) -> dict[str, Any]:
    weights = weights or {
        "semantic": 0.34, "lexical": 0.20, "entity": 0.20,
        "topic": 0.16, "recency": 0.06, "conversation": 0.04,
    }
    content = str(candidate.get("content", ""))
    lexical = overlap(tokens(query), tokens(content))
    candidate_entities = {x.casefold() for x in _entities(content)}
    active_entities = {x.casefold() for x in state.active_entities}
    entity = (len(candidate_entities & active_entities) / max(1, len(active_entities))) if active_entities else 0.0
    topic = overlap(tokens(state.active_topic), tokens(content)) if state.active_topic else lexical
    recent = recency_score(candidate.get("created"))
    semantic = max(0.0, min(1.0, float(semantic_score or 0.0)))
    score = (
        semantic * weights["semantic"] + lexical * weights["lexical"] +
        entity * weights["entity"] + topic * weights["topic"] +
        recent * weights["recency"] + (1.0 if same_conversation else 0.0) * weights["conversation"]
    )
    return {
        "score": score, "semantic": semantic, "lexical": lexical, "entity": entity,
        "topic": topic, "recency": recent, "same_conversation": same_conversation,
        "memory_kind": str(candidate.get("kind") or ""),
    }


def accept_memory(features: dict[str, Any], threshold: float) -> bool:
    """Precision-first gate: aucun signal faible isolé ne suffit.

    Un candidat de la même conversation ou qui partage seulement une entité
    peut encore appartenir à un autre sujet. Il faut donc un ancrage lexical
    ou thématique, sauf paraphrase utilisateur très récente et très proche.
    """
    lexical = float(features["lexical"])
    topic = float(features["topic"])
    entity = float(features["entity"])
    contextual_support = (
        lexical >= 0.20
        or topic >= 0.18
        or (entity >= 0.10 and (lexical >= 0.10 or topic >= 0.18))
    )
    recent_user_support = (
        features["semantic"] >= 0.93
        and features["recency"] >= 0.85
        and features.get("memory_kind") in {"user_fact", "user_message"}
    )
    if not contextual_support and not recent_user_support:
        return False
    return float(features["score"]) >= threshold


def needs_long_term(message: str, history: list[dict[str, str]], state: ConversationState) -> bool:
    """Évite une recherche globale quand le fil récent suffit vraisemblablement."""
    if not history:
        return True
    if REFERENCE.search(message or ""):
        # Les références se résolvent d'abord dans les derniers tours.
        recent_text = " ".join(str(x.get("content", "")) for x in history[-6:])
        if state.active_entities and any(e.casefold() in recent_text.casefold() for e in state.active_entities):
            return False
    return state.transition in {"TOPIC_RETURN", "AMBIGUOUS"} or len(tokens(message)) >= 4
