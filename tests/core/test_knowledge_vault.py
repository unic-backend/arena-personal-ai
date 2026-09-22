from __future__ import annotations

import json
from pathlib import Path

from apps.backend.services.tools.builtin import (
    KnowledgeExplorer,
    KnowledgeFindArgs,
    KnowledgeListArgs,
    KnowledgeReadArgs,
    KnowledgeSearch,
    KnowledgeSearchArgs,
)
from core.knowledge.vault import KnowledgeVault


def test_initialize_cree_les_trois_couches_sans_ecraser(tmp_path: Path):
    vault = KnowledgeVault(tmp_path / "vault")
    chemins = vault.initialize()

    assert Path(chemins["raw"]).is_dir()
    assert Path(chemins["wiki"]).is_dir()
    assert Path(chemins["output"]).is_dir()
    assert vault.schema_path.exists()
    assert vault.index_path.exists()
    assert vault.log_path.exists()

    vault.index_path.write_text("# Mon index\n", encoding="utf-8")
    vault.initialize()
    assert vault.index_path.read_text(encoding="utf-8") == "# Mon index\n"


def test_ingest_est_idempotent_et_garde_la_provenance(tmp_path: Path):
    source = tmp_path / "papier.md"
    source.write_text(
        "# Isolation acoustique\n\nLa laine de roche absorbe une partie du bruit.",
        encoding="utf-8",
    )
    vault = KnowledgeVault(tmp_path / "vault")

    premier = vault.ingest(source, source_url="https://example.test/papier")
    second = vault.ingest(source, source_url="https://example.test/papier")

    assert premier["status"] == "INGESTED"
    assert second["status"] == "UNCHANGED"
    note = Path(premier["wiki_page"]).read_text(encoding="utf-8")
    assert "Isolation acoustique" in note
    assert "https://example.test/papier" in note
    assert premier["sha256"] in note
    assert len(list(vault.raw_dir.iterdir())) == 1
    assert len(list(vault.sources_dir.glob("*.md"))) == 1
    assert "[[sources/" in vault.index_path.read_text(encoding="utf-8")


def test_search_retourne_le_passage_et_sa_source(tmp_path: Path):
    source = tmp_path / "acoustique.txt"
    source.write_text(
        "Une cloison avec laine de roche limite la transmission acoustique.",
        encoding="utf-8",
    )
    vault = KnowledgeVault(tmp_path / "vault")
    vault.ingest(source)

    resultats = vault.search("transmission acoustique")

    assert len(resultats) == 1
    assert resultats[0].score > 0
    assert "transmission acoustique" in resultats[0].snippet.lower()
    assert resultats[0].sources
    assert resultats[0].sources[0].startswith("raw/")


def test_graph_et_lint_detectent_lien_casse_orphelin_et_provenance(tmp_path: Path):
    vault = KnowledgeVault(tmp_path / "vault")
    vault.initialize()
    concepts = vault.wiki_dir / "concepts"
    concepts.mkdir()

    (concepts / "a.md").write_text(
        "---\nsources:\n  - raw/source-a.md\n---\n"
        "# A\n\nVoir [[concepts/b|B]] et [[concepts/inconnu|Inconnu]].\n",
        encoding="utf-8",
    )
    (concepts / "b.md").write_text(
        "---\nsources:\n  - raw/source-b.md\n---\n# B\n",
        encoding="utf-8",
    )
    (concepts / "orphelin.md").write_text("# Orphelin\n", encoding="utf-8")

    graphe = vault.graph()
    rapport = vault.lint()

    assert {
        "source": "concepts/a.md",
        "target": "concepts/b.md",
    } in graphe["edges"]
    assert any(item["target"] == "concepts/inconnu" for item in rapport.broken_links)
    assert "concepts/orphelin.md" in rapport.orphans
    assert "concepts/orphelin.md" in rapport.missing_provenance
    assert rapport.healthy is False


def test_lint_signale_une_source_brute_non_compilee(tmp_path: Path):
    vault = KnowledgeVault(tmp_path / "vault")
    vault.initialize()
    (vault.raw_dir / "nouvelle-source.md").write_text("source brute", encoding="utf-8")

    rapport = vault.lint()

    assert rapport.unprocessed_raw == ["nouvelle-source.md"]


def test_write_graph_produit_un_json_regenerable(tmp_path: Path):
    vault = KnowledgeVault(tmp_path / "vault")
    vault.initialize()

    cible = vault.write_graph()
    charge = json.loads(cible.read_text(encoding="utf-8"))

    assert cible == vault.output_dir / "graph.json"
    assert set(charge) == {"nodes", "edges", "broken_links"}


async def test_autonomous_tool_reutilise_le_meme_vault(tmp_path: Path):
    source = tmp_path / "reference.md"
    source.write_text(
        "# Reference BA13\n\nLe document source parle de double montant aux joints.",
        encoding="utf-8",
    )
    vault = KnowledgeVault(tmp_path / "vault")
    vault.ingest(source)

    resultat = await KnowledgeSearch(vault)(
        KnowledgeSearchArgs(query="double montant joints", limit=3)
    )

    assert resultat.ok is True
    assert resultat.data["source"] == "knowledge_vault"
    assert resultat.data["results"][0]["sources"]
    contenu = resultat.data["results"][0]["content"].lower()
    assert "double montant" in contenu
    assert "knowledge_vault:" in contenu


def test_search_ignore_les_mots_vides_pour_eviter_la_contamination(tmp_path: Path):
    source = tmp_path / "reference.md"
    source.write_text(
        "# Cloison acoustique\n\nCette fiche explique comment faire une cloison avec isolant.",
        encoding="utf-8",
    )
    vault = KnowledgeVault(tmp_path / "vault")
    vault.ingest(source)

    assert vault.search("comment faire avec cette chose") == []



async def test_hybrid_search_signale_son_mode_et_ses_rangs(tmp_path: Path):
    source = tmp_path / "urgence.md"
    source.write_text(
        "# Fonds de secours\n\nConserver une reserve liquide pour les urgences.",
        encoding="utf-8",
    )
    vault = KnowledgeVault(tmp_path / "vault")
    vault.ingest(source)

    async def embedder(texts):
        assert len(texts) == 2
        return [[1.0, 0.0], [0.99, 0.01]]

    resultats = await vault.hybrid_search(
        "epargne de precaution",
        limit=3,
        embedder=embedder,
    )

    assert resultats
    assert resultats[0].mode == "HYBRID_RRF"
    assert resultats[0].signals["semantic_rank"] == 1
    assert resultats[0].sources


def test_agentic_vault_liste_trouve_et_lit_sans_sortir_du_dossier(tmp_path: Path):
    vault = KnowledgeVault(tmp_path / "vault")
    vault.initialize()
    dossier = vault.wiki_dir / "concepts"
    dossier.mkdir()
    (dossier / "ba13.md").write_text(
        "---\nsources:\n  - raw/ba13.md\n---\n"
        "# BA13\n\nLe double montant est pose aux joints de plaques.\n",
        encoding="utf-8",
    )

    assert vault.list_pages("**/*.md") == ["concepts/ba13.md", "index.md", "log.md"]
    trouves = vault.find_text("double montant", context=0)
    assert trouves == [{
        "path": "concepts/ba13.md",
        "line": 7,
        "excerpt": "7: Le double montant est pose aux joints de plaques.",
    }]

    page = vault.read_page("concepts/ba13.md", offset=5, limit=2)
    assert page["path"] == "concepts/ba13.md"
    assert "double montant" in page["content"]
    assert page["sources"] == ["raw/ba13.md"]

    import pytest

    with pytest.raises(ValueError):
        vault.read_page("../../CLAUDE.md")


async def test_agentic_tools_transportent_des_preuves_bornees(tmp_path: Path):
    vault = KnowledgeVault(tmp_path / "vault")
    vault.initialize()
    dossier = vault.wiki_dir / "sources"
    (dossier / "chantier.md").write_text(
        "---\nsources:\n  - raw/chantier.md\n---\n"
        "# Chantier\n\nDouble montant aux joints.\n",
        encoding="utf-8",
    )
    explorer = KnowledgeExplorer(vault)

    listing = await explorer.list_pages(KnowledgeListArgs(pattern="**/*.md", limit=10))
    assert listing.ok is True
    assert "sources/chantier.md" in listing.data["pages"]

    trouve = await explorer.find_text(
        KnowledgeFindArgs(query="double montant", max_results=5, context=0)
    )
    assert trouve.ok is True
    assert "knowledge_vault:sources/chantier.md" in trouve.data["results"][0]["content"]

    lu = await explorer.read_page(
        KnowledgeReadArgs(path="sources/chantier.md", offset=0, limit=20)
    )
    assert lu.ok is True
    assert lu.data["sources"] == ["raw/chantier.md"]
    assert "Double montant" in lu.data["content"]



async def test_hybrid_search_reutilise_les_embeddings_locaux_en_memoire(
    tmp_path: Path, monkeypatch
):
    source = tmp_path / "memoire.md"
    source.write_text(
        "# Memoire locale\n\nUne reserve de securite reste disponible rapidement.",
        encoding="utf-8",
    )
    vault = KnowledgeVault(tmp_path / "vault")
    vault.ingest(source)

    appels = 0

    async def faux_embeddings(texts, **_kwargs):
        nonlocal appels
        appels += 1
        return [[1.0, float(index)] for index, _ in enumerate(texts)]

    monkeypatch.setattr("core.memory.semantique.embeddings_ollama", faux_embeddings)

    premier = await vault.hybrid_search("reserve securite", limit=3)
    second = await vault.hybrid_search("reserve securite", limit=3)

    assert premier and second
    assert appels == 1
    assert premier[0].mode == "HYBRID_RRF"
