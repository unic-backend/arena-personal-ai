"""Briques de retrieval du Knowledge Vault.

Adapte les motifs utiles du projet MIT daveebbelaar/ai-cookbook sans importer
ses dependances cloud : BM25 local, Reciprocal Rank Fusion, recherche dense
optionnelle et metriques d'evaluation. ARENA garde ses fournisseurs locaux et
ses propres garde-fous.

Aucune base vectorielle supplementaire n'est creee ici. Le fournisseur dense
est injecte ; si aucun vecteur exploitable n'est rendu, le moteur reste en
BM25 et le dit explicitement.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Awaitable, Callable, Mapping, Sequence

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9._/-]*")
STOP_WORDS = frozenset({
    "avec", "pour", "dans", "cette", "cela", "ceci", "comme", "faire", "fait",
    "quel", "quelle", "quels", "quelles", "comment", "pourquoi", "quand",
    "peut", "peux", "doit", "dois", "veux", "votre", "notre", "mon", "mes",
    "ton", "tes", "une", "des", "les", "est", "sont", "sur", "plus", "moins",
    "sans", "mais", "donc", "alors", "voici", "the", "and", "for", "with",
    "from", "that", "this", "what", "how", "why", "when", "your", "our",
})
Embedder = Callable[[Sequence[str]], Awaitable[list[list[float]]]]


def normaliser(texte: str) -> str:
    """Normalise pour la recherche sans modifier le texte source."""
    decompose = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in decompose if not unicodedata.combining(c)).casefold()


def tokens(texte: str) -> list[str]:
    """Tokens simples qui gardent les identifiants techniques et metier."""
    return [mot for mot in TOKEN_RE.findall(normaliser(texte)) if mot not in STOP_WORDS]


@dataclass(frozen=True)
class KnowledgeRecord:
    identifiant: str
    title: str
    text: str
    sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class RankedRecord:
    identifiant: str
    score: float
    lexical_rank: int | None = None
    semantic_rank: int | None = None
    mode: str = "BM25"


def bm25_ranking(
    query: str,
    records: Sequence[KnowledgeRecord],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[tuple[str, float]]:
    """Classe avec Okapi BM25, sans dependance externe.

    Le titre est ajoute une seconde fois au document : un titre qui nomme
    exactement le sujet est une preuve plus forte qu'une occurrence perdue
    dans un long corps.
    """
    query_tokens = tokens(query)
    if not query_tokens or not records:
        return []

    docs: list[list[str]] = []
    frequencies: list[Counter[str]] = []
    document_frequency: Counter[str] = Counter()
    for record in records:
        doc_tokens = tokens(record.title) + tokens(record.title) + tokens(record.text)
        docs.append(doc_tokens)
        freq = Counter(doc_tokens)
        frequencies.append(freq)
        for token in freq:
            document_frequency[token] += 1

    average_length = sum(len(doc) for doc in docs) / max(1, len(docs))
    query_counts = Counter(query_tokens)
    total_docs = len(records)
    scores: list[tuple[str, float]] = []

    for record, doc, freq in zip(records, docs, frequencies, strict=True):
        score = 0.0
        doc_length = max(1, len(doc))
        for token, query_count in query_counts.items():
            tf = freq.get(token, 0)
            if not tf:
                continue
            df = document_frequency[token]
            idf = math.log(1.0 + (total_docs - df + 0.5) / (df + 0.5))
            denominator = tf + k1 * (1.0 - b + b * doc_length / max(1.0, average_length))
            score += query_count * idf * (tf * (k1 + 1.0) / denominator)
        if score > 0:
            scores.append((record.identifiant, score))

    scores.sort(key=lambda item: (-item[1], item[0]))
    return scores


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or len(a) != len(b):
        return 0.0
    produit = sum(x * y for x, y in zip(a, b, strict=True))
    norme_a = math.sqrt(sum(x * x for x in a))
    norme_b = math.sqrt(sum(y * y for y in b))
    if norme_a == 0.0 or norme_b == 0.0:
        return 0.0
    return produit / (norme_a * norme_b)


async def semantic_ranking(
    query: str,
    records: Sequence[KnowledgeRecord],
    embedder: Embedder,
) -> list[tuple[str, float]]:
    """Classe par cosinus. Une panne dense rend une liste vide, jamais un faux score."""
    if not records:
        return []
    textes = [query, *[f"{record.title}\n{record.text}" for record in records]]
    try:
        vecteurs = await embedder(textes)
    except Exception:
        return []
    if len(vecteurs) != len(textes) or not vecteurs:
        return []
    dimensions = {len(vector) for vector in vecteurs}
    if len(dimensions) != 1 or next(iter(dimensions)) < 2:
        return []

    requete = vecteurs[0]
    scores = [
        (record.identifiant, cosine(requete, vector))
        for record, vector in zip(records, vecteurs[1:], strict=True)
    ]
    scores = [item for item in scores if item[1] > 0]
    scores.sort(key=lambda item: (-item[1], item[0]))
    return scores


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]],
    *,
    k: int = 60,
) -> list[tuple[str, float]]:
    """Fusionne des rangs heterogenes sans moyenner des echelles incompatibles."""
    if k < 1:
        raise ValueError("k doit etre >= 1")
    scores: defaultdict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, identifiant in enumerate(ranking, start=1):
            scores[identifiant] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


async def hybrid_ranking(
    query: str,
    records: Sequence[KnowledgeRecord],
    *,
    embedder: Embedder | None = None,
    candidate_k: int = 50,
) -> list[RankedRecord]:
    """BM25 toujours ; dense + RRF seulement quand le fournisseur rend des vecteurs."""
    lexical = bm25_ranking(query, records)
    lexical = lexical[:max(1, candidate_k)]
    lexical_ids = [identifiant for identifiant, _ in lexical]
    lexical_rank = {identifiant: rank for rank, identifiant in enumerate(lexical_ids, start=1)}

    semantic: list[tuple[str, float]] = []
    if embedder is not None:
        semantic = await semantic_ranking(query, records, embedder)
        semantic = semantic[:max(1, candidate_k)]
    semantic_ids = [identifiant for identifiant, _ in semantic]
    semantic_rank = {identifiant: rank for rank, identifiant in enumerate(semantic_ids, start=1)}

    if semantic_ids:
        fusion = reciprocal_rank_fusion([lexical_ids, semantic_ids])
        mode = "HYBRID_RRF"
    else:
        fusion = lexical
        mode = "BM25"

    return [
        RankedRecord(
            identifiant=identifiant,
            score=float(score),
            lexical_rank=lexical_rank.get(identifiant),
            semantic_rank=semantic_rank.get(identifiant),
            mode=mode,
        )
        for identifiant, score in fusion
    ]


def ndcg_at_k(
    predicted_ids: Sequence[str],
    relevant: Mapping[str, int | float],
    *,
    k: int = 10,
) -> float:
    """NDCG@k : qualite du rang, 1.0 = classement ideal."""
    dcg = sum(
        float(relevant.get(doc_id, 0.0)) / math.log2(rank + 2)
        for rank, doc_id in enumerate(predicted_ids[:k])
    )
    ideal = sorted((float(v) for v in relevant.values()), reverse=True)[:k]
    idcg = sum(rel / math.log2(rank + 2) for rank, rel in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0


def recall_at_k(
    predicted_ids: Sequence[str],
    relevant_ids: Sequence[str] | set[str],
    *,
    k: int = 10,
) -> float:
    """Part des documents pertinents retrouves dans les k premiers."""
    attendus = set(relevant_ids)
    if not attendus:
        return 0.0
    trouves = set(predicted_ids[:k]) & attendus
    return len(trouves) / len(attendus)
