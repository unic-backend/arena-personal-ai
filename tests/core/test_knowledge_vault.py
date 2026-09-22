from __future__ import annotations

import json
from pathlib import Path

from apps.backend.services.tools.builtin import KnowledgeSearch, KnowledgeSearchArgs
from core.knowledge import KnowledgeVault


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
