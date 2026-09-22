"""Knowledge Vault local, source et compatible Obsidian.

Ce module adapte le motif LLM Wiki au contrat d'ARENA sans introduire un
second moteur de memoire ni une base vectorielle parallele.

Trois couches restent distinctes :
- raw/    : sources originales, immuables une fois ingerees ;
- wiki/   : notes Markdown interliees, compilees et consultables ;
- output/ : graphes et rapports derives, toujours regenerables.

Le vault est une base de connaissance documentaire. Il ne remplace ni
core/memory/ (memoire personnelle), ni PROJECT_MEMORY/ (memoire operationnelle
du depot). Toutes les donnees vivent sous data/knowledge_vault/, donc hors Git.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from tools.documents.reader import EXTENSIONS_LISIBLES, lire_document

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = BASE_DIR / "data" / "knowledge_vault"

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
MOT_RE = re.compile(r"[a-z0-9]{3,}")
STOP_WORDS = frozenset({
    "avec", "pour", "dans", "cette", "cela", "ceci", "comme", "faire", "fait",
    "quel", "quelle", "quels", "quelles", "comment", "pourquoi", "quand",
    "peut", "peux", "doit", "dois", "veux", "votre", "notre", "mon", "mes",
    "ton", "tes", "une", "des", "les", "est", "sont", "sur", "plus", "moins",
    "sans", "mais", "donc", "alors", "voici", "the", "and", "for", "with",
    "from", "that", "this", "what", "how", "why", "when", "your", "our",
})


def _maintenant() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normaliser(texte: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", texte or "")
    ascii_compatible = "".join(c for c in sans_accents if not unicodedata.combining(c))
    return ascii_compatible.casefold()


def _mots(texte: str) -> set[str]:
    return {mot for mot in MOT_RE.findall(_normaliser(texte)) if mot not in STOP_WORDS}


def _slug(texte: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", _normaliser(texte)).strip("-")
    return (base[:80] or "source").strip("-")


def _sha256(chemin: Path) -> str:
    hacheur = hashlib.sha256()
    with chemin.open("rb") as flux:
        for bloc in iter(lambda: flux.read(1024 * 1024), b""):
            hacheur.update(bloc)
    return hacheur.hexdigest()


def _titre_markdown(texte: str, defaut: str) -> str:
    for ligne in texte.splitlines():
        if ligne.startswith("# "):
            titre = ligne[2:].strip()
            if titre:
                return titre
    return defaut


def _sources_frontmatter(texte: str) -> list[str]:
    lignes = texte.splitlines()
    if not lignes or lignes[0].strip() != "---":
        return []
    trouvees: list[str] = []
    dans_sources = False
    for ligne in lignes[1:]:
        if ligne.strip() == "---":
            break
        if ligne.startswith("sources:"):
            dans_sources = True
            reste = ligne.split(":", 1)[1].strip().strip('"')
            if reste:
                trouvees.append(reste)
            continue
        if dans_sources and ligne.lstrip().startswith("- "):
            trouvees.append(ligne.split("- ", 1)[1].strip().strip('"'))
            continue
        if ligne and not ligne.startswith((" ", "\t")):
            dans_sources = False
        if ligne.startswith("source:"):
            valeur = ligne.split(":", 1)[1].strip().strip('"')
            if valeur:
                trouvees.append(valeur)
    return trouvees


@dataclass(frozen=True)
class SearchHit:
    """Une note retenue avec provenance, jamais un texte anonyme."""

    path: str
    title: str
    score: float
    snippet: str
    sources: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LintReport:
    """Sante structurelle du wiki."""

    broken_links: list[dict[str, str]]
    orphans: list[str]
    unprocessed_raw: list[str]
    missing_provenance: list[str]
    duplicate_pages: list[list[str]]

    @property
    def healthy(self) -> bool:
        return not any((
            self.broken_links,
            self.orphans,
            self.unprocessed_raw,
            self.missing_provenance,
            self.duplicate_pages,
        ))

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "healthy": self.healthy}


class KnowledgeVault:
    """Base Markdown locale, navigable et sourcee."""

    def __init__(self, root: Path | str = DEFAULT_ROOT):
        self.root = Path(root)
        self.raw_dir = self.root / "raw"
        self.wiki_dir = self.root / "wiki"
        self.sources_dir = self.wiki_dir / "sources"
        self.output_dir = self.root / "output"
        self.schema_path = self.root / "SCHEMA.md"
        self.index_path = self.wiki_dir / "index.md"
        self.log_path = self.wiki_dir / "log.md"

    def initialize(self) -> dict[str, str]:
        """Cree uniquement l'ossature manquante, sans ecraser un vault existant."""
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if not self.schema_path.exists():
            self.schema_path.write_text(
                "# ARENA Knowledge Vault — schema\n\n"
                "Le vault separe strictement raw/, wiki/ et output/.\n\n"
                "## Regles\n\n"
                "1. raw/ conserve la source originale : ne jamais la reecrire.\n"
                "2. Toute affirmation de wiki/ doit pointer vers au moins une source.\n"
                "3. Les liens internes utilisent la syntaxe Obsidian [[chemin|Titre]].\n"
                "4. Une contradiction se signale ; elle n'est jamais arbitree sans preuve.\n"
                "5. wiki/log.md est append-only.\n"
                "6. Les sorties de output/ sont derivees et peuvent etre regenerees.\n",
                encoding="utf-8",
            )
        if not self.index_path.exists():
            self.index_path.write_text(
                "# Knowledge Vault\n\n"
                "Carte d'entree de la base de connaissance.\n\n"
                "## Sources\n\n",
                encoding="utf-8",
            )
        if not self.log_path.exists():
            self.log_path.write_text(
                "# Journal du Knowledge Vault\n\n"
                "Historique append-only des ingestions et maintenances.\n",
                encoding="utf-8",
            )
        return {
            "root": str(self.root),
            "raw": str(self.raw_dir),
            "wiki": str(self.wiki_dir),
            "output": str(self.output_dir),
        }

    def _source_markdown(
        self,
        *,
        title: str,
        raw_name: str,
        source_url: str | None,
        digest: str,
        texte: str,
        passages: Iterable[Any],
    ) -> str:
        provenance = []
        for passage in passages:
            source = getattr(passage, "source", raw_name)
            provenance.append(f"- {source}")
        provenance_texte = "\n".join(provenance) or f"- {raw_name}"
        url = source_url or ""
        return (
            "---\n"
            "type: source\n"
            f"title: {json.dumps(title, ensure_ascii=False)}\n"
            f"source: {json.dumps('raw/' + raw_name, ensure_ascii=False)}\n"
            f"source_url: {json.dumps(url, ensure_ascii=False)}\n"
            f"sha256: {json.dumps(digest)}\n"
            f"ingested_at: {json.dumps(_maintenant())}\n"
            "---\n\n"
            f"# {title}\n\n"
            "## Provenance\n\n"
            f"- Fichier brut : raw/{raw_name}\n"
            + (f"- URL : {url}\n" if url else "")
            + f"- SHA-256 : {digest}\n\n"
            "## Reperes de lecture\n\n"
            f"{provenance_texte}\n\n"
            "## Contenu extrait\n\n"
            f"{texte.strip()}\n"
        )

    def _ajouter_index(self, lien: str, title: str) -> None:
        contenu = self.index_path.read_text(encoding="utf-8")
        marqueur = f"[[{lien}|"
        if marqueur in contenu:
            return
        with self.index_path.open("a", encoding="utf-8") as flux:
            flux.write(f"- [[{lien}|{title}]]\n")

    def _journaliser(self, action: str, detail: str) -> None:
        with self.log_path.open("a", encoding="utf-8") as flux:
            flux.write(f"\n## [{_maintenant()}] {action}\n\n{detail.strip()}\n")

    def ingest(
        self,
        source_path: Path | str,
        *,
        source_url: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Ingere un fichier reel en conservant l'original et sa provenance."""
        self.initialize()
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            return {"status": "REFUSED", "reason": "source_absente", "path": str(source)}
        if source.suffix.lower() not in EXTENSIONS_LISIBLES:
            return {
                "status": "REFUSED",
                "reason": "format_non_pris_en_charge",
                "extension": source.suffix.lower(),
            }

        document = lire_document(source)
        if not document.lu:
            return {
                "status": "REFUSED",
                "reason": document.raison or document.statut,
                "document_status": document.statut,
            }

        digest = _sha256(source)
        nom_base = _slug(title or source.stem)
        raw_name = f"{nom_base}-{digest[:12]}{source.suffix.lower()}"
        raw_target = self.raw_dir / raw_name
        if not raw_target.exists():
            shutil.copy2(source, raw_target)

        note_name = f"{nom_base}-{digest[:12]}.md"
        note_path = self.sources_dir / note_name
        note_title = title or source.stem.replace("_", " ").replace("-", " ").strip()
        if not note_path.exists():
            note_path.write_text(
                self._source_markdown(
                    title=note_title,
                    raw_name=raw_name,
                    source_url=source_url,
                    digest=digest,
                    texte=document.texte,
                    passages=document.passages,
                ),
                encoding="utf-8",
            )
            self._ajouter_index(f"sources/{note_path.stem}", note_title)
            self._journaliser(
                "INGEST",
                f"Source {raw_name} -> wiki/sources/{note_name} ({digest[:12]}).",
            )
            statut = "INGESTED"
        else:
            statut = "UNCHANGED"

        return {
            "status": statut,
            "source": str(raw_target),
            "wiki_page": str(note_path),
            "sha256": digest,
            "passages": len(document.passages),
            "characters": document.caracteres,
        }

    def _wiki_pages(self) -> list[Path]:
        if not self.wiki_dir.exists():
            return []
        return sorted(p for p in self.wiki_dir.rglob("*.md") if p.is_file())

    def _relative_wiki(self, path: Path) -> str:
        return path.relative_to(self.wiki_dir).as_posix()

    def _resolve_links(
        self,
    ) -> tuple[dict[str, Path], list[dict[str, str]], list[dict[str, str]]]:
        pages = self._wiki_pages()
        aliases: dict[str, Path] = {}
        for page in pages:
            relatif = self._relative_wiki(page)
            sans_ext = relatif[:-3] if relatif.endswith(".md") else relatif
            aliases[_normaliser(sans_ext)] = page
            aliases.setdefault(_normaliser(page.stem), page)

        edges: list[dict[str, str]] = []
        broken: list[dict[str, str]] = []
        for page in pages:
            source = self._relative_wiki(page)
            texte = page.read_text(encoding="utf-8", errors="replace")
            for cible_brute in WIKILINK_RE.findall(texte):
                cible = cible_brute.strip().replace("\\", "/")
                if not cible or "://" in cible:
                    continue
                cle = _normaliser(cible.removesuffix(".md"))
                destination = aliases.get(cle)
                if destination is None:
                    broken.append({"source": source, "target": cible})
                    continue
                edges.append({
                    "source": source,
                    "target": self._relative_wiki(destination),
                })
        return aliases, edges, broken

    def graph(self) -> dict[str, Any]:
        """Rend la carte navigable du wiki, sans dependre d'Obsidian."""
        pages = self._wiki_pages()
        _, edges, broken = self._resolve_links()
        entrants = {self._relative_wiki(page): 0 for page in pages}
        sortants = {self._relative_wiki(page): 0 for page in pages}
        for edge in edges:
            entrants[edge["target"]] += 1
            sortants[edge["source"]] += 1
        nodes = [
            {
                "id": self._relative_wiki(page),
                "title": _titre_markdown(
                    page.read_text(encoding="utf-8", errors="replace"),
                    page.stem,
                ),
                "inbound": entrants[self._relative_wiki(page)],
                "outbound": sortants[self._relative_wiki(page)],
            }
            for page in pages
        ]
        return {"nodes": nodes, "edges": edges, "broken_links": broken}

    def search(self, query: str, *, limit: int = 5) -> list[SearchHit]:
        """Recherche lexicale bornee, index-first, avec provenance."""
        termes = _mots(query)
        if not termes or not self.wiki_dir.exists():
            return []

        index_links: set[str] = set()
        if self.index_path.exists():
            index_text = self.index_path.read_text(encoding="utf-8", errors="replace")
            for cible in WIKILINK_RE.findall(index_text):
                index_links.add(_normaliser(cible.strip().removesuffix(".md")))

        resultats: list[SearchHit] = []
        for page in self._wiki_pages():
            if page.name in {"index.md", "log.md"}:
                continue
            texte = page.read_text(encoding="utf-8", errors="replace")
            relatif = self._relative_wiki(page)
            titre = _titre_markdown(texte, page.stem)
            mots_titre = _mots(titre)
            mots_corps = _mots(texte)
            titre_matches = len(termes & mots_titre)
            corps_matches = len(termes & mots_corps)
            if not titre_matches and not corps_matches:
                continue
            score = float(titre_matches * 4 + corps_matches)
            cle = _normaliser(relatif.removesuffix(".md"))
            if cle in index_links:
                score += 1.5
            normalise = _normaliser(texte)
            positions = [
                normalise.find(terme)
                for terme in termes
                if normalise.find(terme) >= 0
            ]
            debut = max(0, min(positions) - 180) if positions else 0
            snippet = re.sub(r"\s+", " ", texte[debut:debut + 520]).strip()
            resultats.append(SearchHit(
                path=relatif,
                title=titre,
                score=score,
                snippet=snippet,
                sources=_sources_frontmatter(texte),
            ))

        resultats.sort(key=lambda item: (-item.score, item.path))
        return resultats[:max(1, min(limit, 20))]

    def lint(self) -> LintReport:
        """Verifie liens, provenance, doublons et sources non compilees."""
        pages = self._wiki_pages()
        _, edges, broken = self._resolve_links()
        entrants = {self._relative_wiki(page): 0 for page in pages}
        sortants = {self._relative_wiki(page): 0 for page in pages}
        for edge in edges:
            entrants[edge["target"]] += 1
            sortants[edge["source"]] += 1

        orphans = [
            relatif
            for relatif in entrants
            if Path(relatif).name not in {"index.md", "log.md"}
            and entrants[relatif] == 0
            and sortants[relatif] == 0
        ]

        missing_provenance: list[str] = []
        digest_to_pages: dict[str, list[str]] = {}
        digests_compiles: set[str] = set()
        for page in pages:
            relatif = self._relative_wiki(page)
            if Path(relatif).name in {"index.md", "log.md"}:
                continue
            texte = page.read_text(encoding="utf-8", errors="replace")
            if not _sources_frontmatter(texte):
                missing_provenance.append(relatif)
            match = re.search(r'^sha256:\s*["\']?([0-9a-f]{64})', texte, re.MULTILINE)
            if match:
                digest = match.group(1)
                digests_compiles.add(digest)
                digest_to_pages.setdefault(digest, []).append(relatif)

        unprocessed_raw: list[str] = []
        if self.raw_dir.exists():
            for source in sorted(p for p in self.raw_dir.iterdir() if p.is_file()):
                if _sha256(source) not in digests_compiles:
                    unprocessed_raw.append(source.name)

        duplicate_pages = [
            sorted(noms)
            for noms in digest_to_pages.values()
            if len(noms) > 1
        ]
        return LintReport(
            broken_links=broken,
            orphans=sorted(orphans),
            unprocessed_raw=unprocessed_raw,
            missing_provenance=sorted(missing_provenance),
            duplicate_pages=sorted(duplicate_pages),
        )

    def write_graph(self) -> Path:
        """Ecrit un JSON regenerable que l'interface ou Obsidian peut exploiter."""
        self.initialize()
        cible = self.output_dir / "graph.json"
        cible.write_text(
            json.dumps(self.graph(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return cible
