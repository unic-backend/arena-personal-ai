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
QuestionScope = Literal["CURRENT_CONVERSATION", "PERSONAL_CONTEXT", "GENERAL_KNOWLEDGE", "UNKNOWN"]

STOPWORDS = {
    "alors", "avec", "avoir", "cette", "comme", "dans", "des", "donc", "elle", "elles",
    "encore", "est", "ils", "mais", "mes", "mon", "nous", "pour", "que", "quel", "quelle",
    "qui", "quoi", "son", "sur", "tes", "ton", "tous", "tout", "une", "vous", "the", "and",
    "this", "that", "what", "why", "from", "pas", "plus", "moi", "toi", "lui",
    "et", "le", "la", "les", "de", "du", "au", "aux", "un", "ce", "ces", "cet",
    "déjà", "deja", "était", "etait", "être", "etre", "problème", "probleme",
    "encore", "avait", "avais", "avons", "avez",
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
QUESTION = re.compile(
    r"^\s*(?:est-ce|es-tu|sais-tu|peux-tu|pourquoi|comment|combien|quel(?:le|s)?|"
    r"qui|quoi|où|ou\b|quand|does|do|did|is|are|why|how|what|which|who|when)\b",
    re.IGNORECASE,
)
SPECULATION = re.compile(
    r"\b(?:peut[- ]?être|peut etre|maybe|perhaps|probablement|possiblement|"
    r"j'envisage|je pourrais|je pense peut-être|si jamais|supposons?|imaginons?|par exemple)\b",
    re.IGNORECASE,
)
CORRECTION = re.compile(
    r"\b(?:correction|en fait|actually|je me suis tromp[ée]|j'avais tort|i was wrong|"
    r"je voulais dire|i meant|le précédent .* faux|previous .* wrong)\b",
    re.IGNORECASE,
)
PLAN = re.compile(
    r"\b(?:je vais|je compte|je prévois|je prevois|j'envisage de|i plan to|i'm going to|"
    r"je veux tester|nous allons tester|on va tester)\b",
    re.IGNORECASE,
)
PREFERENCE = re.compile(
    r"\b(?:je préfère|je prefere|ma préférence|ma preference|i prefer)\b",
    re.IGNORECASE,
)
DECISION_QUERY = re.compile(
    r"\b(?:choisi|choisie|choisir|décidé|decide|décision|decision|retenu|validé|valide|"
    r"selected|chosen|decided)\b",
    re.IGNORECASE,
)
PERSONAL_MARKER = re.compile(
    r"\b(?:mon|ma|mes|notre|nos|moi|je|j['’]ai|j['’]avais|me|my|mine|i paid|i bought|"
    r"ai-je|avais-je|est-ce que j['’])\b",
    re.IGNORECASE,
)
GENERAL_MARKER = re.compile(
    r"\b(?:normalement|en général|en general|typiquement|caractéristiques|caracteristiques|"
    r"spécifications|specifications|specs|normally|typically|in general)\b",
    re.IGNORECASE,
)


def classify_question_scope(message: str, *, has_reference: bool = False) -> QuestionScope:
    value = (message or "").strip()
    if not value:
        return "UNKNOWN"
    if GENERAL_MARKER.search(value):
        return "GENERAL_KNOWLEDGE"
    if has_reference or RETURN.search(value):
        return "CURRENT_CONVERSATION"
    if PERSONAL_MARKER.search(value):
        return "PERSONAL_CONTEXT"
    return "UNKNOWN"


def classify_user_evidence(text: str) -> dict[str, Any]:
    """Classifie sans LLM si un message peut nourrir la mémoire longue.

    Le texte original est toujours conservé dans l'historique de conversation.
    Cette décision ne contrôle que son éligibilité comme preuve réutilisable.
    """
    value = (text or "").strip()
    if not value:
        return {"eligible": False, "source_type": "empty", "confidence": 0.0}
    if "?" in value or QUESTION.search(value):
        return {"eligible": False, "source_type": "user_question", "confidence": 0.0}
    if SPECULATION.search(value):
        return {"eligible": False, "source_type": "user_speculation", "confidence": 0.25}
    if CORRECTION.search(value):
        return {"eligible": True, "source_type": "user_correction", "confidence": 1.0}
    if PREFERENCE.search(value):
        return {"eligible": True, "source_type": "user_preference", "confidence": 0.9}
    if PLAN.search(value):
        return {"eligible": True, "source_type": "user_plan", "confidence": 0.65}
    return {"eligible": True, "source_type": "user_assertion", "confidence": 0.95}


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
    question_scope: QuestionScope = "UNKNOWN"

    def as_debug(self) -> dict[str, Any]:
        return {
            "active_topic": self.active_topic,
            "previous_topics": self.previous_topics[-5:],
            "active_entities": self.active_entities[-8:],
            "transition": self.transition,
            "references": self.references,
            "confidence": round(self.confidence, 3),
            "question_scope": self.question_scope,
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


def understand(
    message: str,
    history: list[dict[str, str]],
    *,
    recent_window: int = 8,
) -> ConversationState:
    user_history = [str(item.get("content", "")) for item in history if item.get("role") == "user"]
    recent_window = max(2, min(int(recent_window), 30))
    recent = user_history[-recent_window:]
    current_tokens = tokens(message)

    scored_all = [
        (overlap(current_tokens, tokens(text)), index, text)
        for index, text in enumerate(user_history)
    ]
    best_score, best_index, best_text = max(
        scored_all,
        default=(0.0, -1, ""),
        key=lambda item: item[0],
    )
    recent_start = max(0, len(user_history) - recent_window)
    best_is_older = best_index >= 0 and best_index < recent_start
    recent_scores = [
        (score, index, text) for score, index, text in scored_all if index >= recent_start
    ]
    recent_best_score, _, _ = max(
        recent_scores,
        default=(0.0, -1, ""),
        key=lambda item: item[0],
    )

    previous_topics = [" ".join(sorted(tokens(text))[:8]) for text in user_history if tokens(text)]
    has_reference = bool(REFERENCE.search(message or ""))
    explicit_return = bool(RETURN.search(message or ""))
    question_scope = classify_question_scope(message, has_reference=has_reference)

    # A retour explicite doit pointer vers un ancien message qui partage
    # réellement le sujet demandé. Sinon on garde le message courant comme
    # sujet au lieu de choisir arbitrairement un distracteur récent.
    if explicit_return and best_score >= 0.10:
        transition: TopicTransition = "TOPIC_RETURN"
        confidence = min(1.0, 0.72 + best_score)
    elif best_is_older and best_score >= 0.12:
        transition = "TOPIC_RETURN"
        confidence = min(1.0, 0.62 + best_score)
    elif has_reference and user_history:
        transition = "CONTINUATION"
        confidence = max(0.70, min(1.0, 0.55 + best_score))
    elif recent_best_score >= 0.18:
        transition = "CONTINUATION"
        confidence = min(1.0, 0.55 + recent_best_score)
    elif current_tokens and user_history:
        transition = "TOPIC_SHIFT"
        confidence = 0.62
    else:
        transition = "AMBIGUOUS"
        confidence = 0.35

    entities = _entities(message)
    reference_candidates: list[str] = []
    if has_reference:
        # Le meilleur ancrage lexical gagne sur un sujet récent sans rapport.
        if best_text and best_score >= 0.10:
            reference_candidates.extend(_entities(best_text))
            if best_index > 0:
                reference_candidates.extend(_entities(user_history[best_index - 1]))
        reference_candidates.extend(_reference_entities(recent))
        if not reference_candidates:
            reference_candidates.extend(_reference_entities(user_history))
        reference_candidates = list(dict.fromkeys(reference_candidates))
        for entity in reference_candidates:
            if entity not in entities:
                entities.append(entity)

    topic_source = (
        best_text
        if transition == "TOPIC_RETURN" and best_text and best_score >= 0.10
        else message
    )
    topic = " ".join(sorted(tokens(topic_source))[:8])
    references = {}
    if has_reference and reference_candidates:
        references["recent_reference"] = reference_candidates[0]
    return ConversationState(
        topic,
        previous_topics[-12:],
        entities[-12:],
        transition,
        references,
        confidence,
        question_scope,
    )


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
    shared_entities = candidate_entities & active_entities
    entity = (len(shared_entities) / max(1, len(active_entities))) if active_entities else 0.0
    entity_conflict = bool(active_entities and candidate_entities and not shared_entities)
    topic = overlap(tokens(state.active_topic), tokens(content)) if state.active_topic else lexical
    recent = recency_score(candidate.get("created"))
    semantic = max(0.0, min(1.0, float(semantic_score or 0.0)))
    score = (
        semantic * weights["semantic"] + lexical * weights["lexical"] +
        entity * weights["entity"] + topic * weights["topic"] +
        recent * weights["recency"] + (1.0 if same_conversation else 0.0) * weights["conversation"]
    )
    confidence = max(0.0, min(1.0, float(candidate.get("confidence", 1.0))))
    return {
        "score": score,
        "semantic": semantic,
        "lexical": lexical,
        "entity": entity,
        "entity_conflict": entity_conflict,
        "topic": topic,
        "recency": recent,
        "same_conversation": same_conversation,
        "memory_kind": str(candidate.get("kind") or ""),
        "source_type": str(candidate.get("source_type") or "legacy"),
        "confidence": confidence,
        "query_requires_decision": bool(DECISION_QUERY.search(query or "")),
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
    if features.get("entity_conflict"):
        return False
    if float(features.get("confidence", 1.0)) < 0.5:
        return False
    if (
        features.get("query_requires_decision")
        and features.get("source_type") in {"user_plan", "user_speculation"}
    ):
        return False
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
    """Route la mémoire longue seulement quand elle peut apporter une preuve utile."""
    if state.question_scope == "GENERAL_KNOWLEDGE" and state.transition != "TOPIC_RETURN":
        return False
    if not history:
        return state.question_scope in {"PERSONAL_CONTEXT", "CURRENT_CONVERSATION", "UNKNOWN"}
    if REFERENCE.search(message or ""):
        # Les références se résolvent d'abord dans le fil courant.
        recent_text = " ".join(str(x.get("content", "")) for x in history[-8:])
        if state.active_entities and any(e.casefold() in recent_text.casefold() for e in state.active_entities):
            return False
    return (
        state.transition in {"TOPIC_RETURN", "AMBIGUOUS"}
        or state.question_scope == "PERSONAL_CONTEXT"
        or len(tokens(message)) >= 4
    )
