from __future__ import annotations

from core.knowledge.retrieval import (
    KnowledgeRecord,
    bm25_ranking,
    hybrid_ranking,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank_fusion,
)


def test_bm25_prefere_identifiant_exact_et_ignore_les_mots_vides():
    records = [
        KnowledgeRecord("exact", "Formulaire 1099-MISC", "Declaration freelance."),
        KnowledgeRecord("general", "Fiscalite freelance", "Taxes et revenus independants."),
    ]

    classement = bm25_ranking("comment faire avec le 1099-MISC", records)

    assert classement
    assert classement[0][0] == "exact"
    assert bm25_ranking("comment faire avec cette chose", records) == []


def test_rrf_fusionne_des_rangs_sans_melanger_leurs_scores():
    fusion = reciprocal_rank_fusion([
        ["lexical", "commun", "semantic"],
        ["semantic", "commun", "lexical"],
    ])

    ids = [identifiant for identifiant, _ in fusion]
    assert ids[0] == "commun"
    assert set(ids) == {"lexical", "commun", "semantic"}


async def test_hybrid_retrieval_recupere_une_paraphrase_absente_du_lexical():
    records = [
        KnowledgeRecord(
            "emergency",
            "Emergency savings",
            "Keep emergency savings in a liquid account.",
        ),
        KnowledgeRecord(
            "mortgage",
            "Mortgage",
            "A mortgage finances a property purchase.",
        ),
    ]

    async def embedder(texts):
        # query "rainy day fund" est semantiquement proche du premier document,
        # sans partager ses mots utiles. Le deuxieme reste orthogonal.
        assert len(texts) == 3
        return [
            [1.0, 0.0],
            [0.99, 0.01],
            [0.0, 1.0],
        ]

    assert bm25_ranking("Where should I park my rainy-day fund?", records) == []

    classement = await hybrid_ranking(
        "Where should I park my rainy-day fund?",
        records,
        embedder=embedder,
    )

    assert classement[0].identifiant == "emergency"
    assert classement[0].mode == "HYBRID_RRF"
    assert classement[0].semantic_rank == 1


async def test_hybrid_retrieval_retombe_honnetement_sur_bm25_si_dense_absent():
    records = [
        KnowledgeRecord("ba13", "BA13", "Double montant aux joints de plaques."),
        KnowledgeRecord("peinture", "Peinture", "Deux couches de finition."),
    ]

    async def indisponible(_texts):
        return []

    classement = await hybrid_ranking(
        "double montant joints",
        records,
        embedder=indisponible,
    )

    assert classement
    assert classement[0].identifiant == "ba13"
    assert all(item.mode == "BM25" for item in classement)
    assert all(item.semantic_rank is None for item in classement)


def test_metriques_de_retrieval_mesurent_le_classement():
    prediction = ["hors_sujet", "bon", "autre"]
    pertinent = {"bon": 2, "autre": 1}

    ndcg = ndcg_at_k(prediction, pertinent, k=3)
    rappel = recall_at_k(prediction, set(pertinent), k=2)

    assert 0.0 < ndcg < 1.0
    assert rappel == 0.5
