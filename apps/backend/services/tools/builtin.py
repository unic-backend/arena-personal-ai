"""Calcul arithmetique borne et recherche HTTP sans execution arbitraire."""
import ast
import math
import operator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field

from apps.backend.config import RENDERED_DIR
from apps.backend.security import validate_media_path
from apps.backend.services.tools.registry import Tool, ToolRegistry, ToolResult
from core.knowledge.vault import KnowledgeVault
from core.models.confidentialite import Confidentialite, classer
from core.security.trust import TrustLevel, wrap


class CalculateArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expression: str = Field(min_length=1, max_length=256)


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=500)


def evaluate(expression: str) -> float:
    """Whitelist AST : nombres, parentheses et + - * / // % ** seulement."""
    tree = ast.parse(expression, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 64:
        raise ValueError("Expression trop complexe")
    operations = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                  ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
                  ast.Pow: operator.pow}

    def visit(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            result = float(node.value)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            result = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and type(node.op) in operations:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("Exposant trop grand")
            result = operations[type(node.op)](left, right)
        else:
            raise ValueError("Syntaxe interdite")
        if not isinstance(result, (float, int)) or not math.isfinite(result) or abs(result) > 1e100:
            raise ValueError("Resultat hors limites")
        return float(result)

    return visit(tree.body)


async def calculate(args: CalculateArgs) -> ToolResult:
    try:
        return ToolResult(ok=True, data={"value": evaluate(args.expression), "precision": "float64"})
    except (ValueError, SyntaxError, ArithmeticError, RecursionError):
        return ToolResult(ok=False, error="invalid_expression")


class WebSearch:
    """Tavily si configure ; Instant Answer DDG sinon (couverture plus limitee)."""

    def __init__(self, client: httpx.AsyncClient, tavily_key: str = ""):
        self.client, self.tavily_key = client, tavily_key

    @staticmethod
    def _safe_url(url: str) -> bool:
        return urlparse(url).scheme in {"http", "https"}

    async def __call__(self, args: SearchArgs) -> ToolResult:
        if classer(args.query).niveau is Confidentialite.TRES_SENSIBLE:
            return ToolResult(ok=False, error="sensitive_query_blocked")
        if self.tavily_key:
            try:
                response = await self.client.post("https://api.tavily.com/search", json={
                    "api_key": self.tavily_key, "query": args.query, "max_results": 5,
                    "include_answer": False,
                })
                response.raise_for_status()
                sources = [{"title": str(item.get("title", ""))[:200],
                            "url": str(item.get("url", "")),
                            "text": str(item.get("content", ""))[:1200]}
                           for item in response.json().get("results", [])[:5]
                           if self._safe_url(str(item.get("url", "")))]
                if sources:
                    return ToolResult(ok=True, data={"provider": "tavily", "sources": sources})
            except (httpx.HTTPError, ValueError, TypeError, AttributeError):
                pass  # DDG remains usable when Tavily times out or exhausts its quota
        response = await self.client.get("https://api.duckduckgo.com/", params={
            "q": args.query, "format": "json", "no_html": 1, "no_redirect": 1,
        })
        response.raise_for_status()
        payload = response.json()
        sources: list[dict[str, str]] = []
        if payload.get("AbstractText") and self._safe_url(payload.get("AbstractURL", "")):
            sources.append({"title": str(payload.get("Heading", ""))[:200],
                            "url": payload["AbstractURL"], "text": payload["AbstractText"][:1200]})
        pending: list[Any] = list(payload.get("RelatedTopics", []))[:30]
        for item in pending:
            if not isinstance(item, dict):
                continue
            if item.get("Topics") and len(pending) < 100:
                pending.extend(item["Topics"][:10])
            if item.get("Text") and self._safe_url(str(item.get("FirstURL", ""))):
                sources.append({"title": str(item["Text"])[:120], "url": item["FirstURL"],
                                "text": str(item["Text"])[:1200]})
            if len(sources) >= 5:
                break
        return ToolResult(ok=bool(sources), data={"provider": "duckduckgo_instant",
                          "sources": sources, "limited_coverage": True},
                          error=None if sources else "no_sources")



class KnowledgeSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=10)


class KnowledgeSearch:
    """Recherche read-only dans le Knowledge Vault local."""

    def __init__(self, vault: KnowledgeVault | None = None):
        self.vault = vault or KnowledgeVault()

    async def __call__(self, args: KnowledgeSearchArgs) -> ToolResult:
        try:
            hits = self.vault.search(args.query, limit=args.limit)
        except OSError:
            return ToolResult(ok=False, error="knowledge_vault_unavailable")
        return ToolResult(
            ok=bool(hits),
            data={
                "source": "knowledge_vault",
                "results": [
                    {
                        "path": hit.path,
                        "title": hit.title,
                        "score": hit.score,
                        "sources": hit.sources,
                        "content": wrap(
                            hit.snippet,
                            TrustLevel.RETRIEVED,
                            f"knowledge_vault:{hit.path}",
                        ).text,
                    }
                    for hit in hits
                ],
            },
            error=None if hits else "no_knowledge_sources",
        )


class AttachmentArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    attachment_id: str = Field(min_length=8, max_length=128)


class VideoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    media_path: str = Field(min_length=1, max_length=1024)


class CreateDocumentArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1, max_length=100_000)
    format: str = Field(default="pdf", pattern=r"^(pdf|docx|md|txt|html)$")
    title: str = Field(default="document", min_length=1, max_length=120)


class AutonomousMediaTools:
    """Adaptateurs minces vers les capacités déjà présentes d'ARENA.

    Le contexte d'exécution porte les références autorisées pour CETTE requête.
    Un modèle ne peut donc pas nommer l'identifiant d'une ancienne pièce ou un
    chemin média arbitraire et le faire ouvrir.
    """

    def __init__(self, pieces_jointes: Any = None, vision_agent: Any = None,
                 video_agent: Any = None, registre: Any = None):
        self.pieces_jointes = pieces_jointes
        self.vision_agent = vision_agent
        self.video_agent = video_agent
        self.registre = registre

    @staticmethod
    def _autorise(valeur: str, cle: str, contexte: dict[str, Any]) -> bool:
        autorises = contexte.get(cle) or []
        return valeur in autorises

    async def lire_document(self, args: AttachmentArgs, contexte: dict[str, Any]) -> ToolResult:
        if not self._autorise(args.attachment_id, "attachments", contexte):
            return ToolResult(ok=False, error="attachment_not_allowed")
        if self.pieces_jointes is None:
            return ToolResult(ok=False, error="attachment_store_unavailable")
        piece = self.pieces_jointes.lire(args.attachment_id)
        if piece is None:
            return ToolResult(ok=False, error="attachment_missing_or_expired")
        if not piece.lisible:
            return ToolResult(ok=False, error="attachment_unreadable",
                              data={"name": piece.nom, "reason": piece.raison or piece.statut})
        if piece.est_image:
            return ToolResult(ok=False, error="attachment_is_image")
        return ToolResult(ok=True, data={
            "name": piece.nom,
            "text": piece.texte,
            "truncated": bool(piece.tronque),
            "source": "uploaded_document",
        })

    async def analyser_image(self, args: AttachmentArgs, contexte: dict[str, Any]) -> ToolResult:
        if not self._autorise(args.attachment_id, "attachments", contexte):
            return ToolResult(ok=False, error="attachment_not_allowed")
        if self.pieces_jointes is None or self.vision_agent is None:
            return ToolResult(ok=False, error="vision_unavailable")
        piece = self.pieces_jointes.lire(args.attachment_id)
        if piece is None:
            return ToolResult(ok=False, error="attachment_missing_or_expired")
        if not piece.lisible or not piece.est_image:
            return ToolResult(ok=False, error="attachment_not_readable_image")
        resultat = await self.vision_agent.run(
            str(contexte.get("message") or "Analyse cette image."),
            context={"attachments": [args.attachment_id]},
        )
        if resultat.get("status") != "success":
            return ToolResult(ok=False, error="vision_failed",
                              data={"message": resultat.get("response") or ""})
        return ToolResult(ok=True, data={
            "name": piece.nom,
            "analysis": resultat.get("response") or "",
            "source": "vision_model",
        })

    async def analyser_video(self, args: VideoArgs, contexte: dict[str, Any]) -> ToolResult:
        if not self._autorise(args.media_path, "media_paths", contexte):
            return ToolResult(ok=False, error="media_not_allowed")
        if self.video_agent is None:
            return ToolResult(ok=False, error="video_analysis_unavailable")
        try:
            chemin = validate_media_path(args.media_path)
        except Exception:
            return ToolResult(ok=False, error="invalid_media_path")
        if not chemin.is_file():
            return ToolResult(ok=False, error="media_missing")
        resultat = await self.video_agent.run(
            str(contexte.get("message") or "Transcris et analyse le contenu audio de cette vidéo."),
            context={"video_path": str(chemin)},
        )
        if resultat.get("status") != "success":
            return ToolResult(ok=False, error="video_analysis_failed",
                              data={"message": resultat.get("response") or ""})
        # L'agent actuel analyse la piste audio/transcription. Il ne faut jamais
        # faire passer ce résultat pour une compréhension visuelle des frames.
        return ToolResult(ok=True, data={
            "name": chemin.name,
            "analysis_kind": "audio_transcription_and_text_analysis",
            "transcription": resultat.get("transcription") or "",
            "duration": resultat.get("duration"),
            "segments": resultat.get("segments"),
            "analysis": resultat.get("ai_analysis") or "",
            "visual_frame_analysis": False,
        })

    async def creer_document(self, args: CreateDocumentArgs, contexte: dict[str, Any]) -> ToolResult:
        if self.registre is None:
            return ToolResult(ok=False, error="document_generation_unavailable")
        import asyncio

        resultat = await asyncio.to_thread(
            self.registre.executer, "file_conversion", "rediger",
            texte=args.text, format_cible=args.format, titre=args.title,
        )
        statut = getattr(getattr(resultat, "statut", None), "value", "")
        detail = getattr(resultat, "detail", None) or {}
        preuve = str(getattr(resultat, "preuve", "") or "")
        url = str(detail.get("url") or "")
        if statut != "SUCCESS":
            return ToolResult(ok=False, error="document_generation_failed",
                              data={"message": str(getattr(resultat, "message", "") or "")})
        chemin = Path(preuve)
        try:
            dans_rendus = chemin.resolve().is_relative_to(RENDERED_DIR.resolve())
        except (OSError, ValueError):
            dans_rendus = False
        if not url.startswith("/media/rendered/") or not dans_rendus:
            return ToolResult(ok=False, error="artifact_not_downloadable")
        if not chemin.is_file() or chemin.stat().st_size <= 0:
            return ToolResult(ok=False, error="artifact_missing")
        return ToolResult(ok=True, data={
            "artifact": {
                "url": url,
                "name": chemin.name,
                "format": args.format,
                "size_bytes": chemin.stat().st_size,
            }
        })

def builtin_registry(client: httpx.AsyncClient, tavily_key: str = "",
                     pieces_jointes: Any = None, vision_agent: Any = None,
                     video_agent: Any = None, registre: Any = None,
                     knowledge_vault: KnowledgeVault | None = None) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(Tool("calculate", "Calcule une expression arithmetique numerique.",
                           CalculateArgs, calculate, timeout=1))
    registry.register(Tool("web_search", "Recherche des faits et sources web. Ne jamais envoyer de secrets.",
                           SearchArgs, WebSearch(client, tavily_key), timeout=10))
    registry.register(Tool(
        "knowledge_search",
        "Recherche dans la base de connaissance locale sourcee du proprietaire.",
        KnowledgeSearchArgs, KnowledgeSearch(knowledge_vault), timeout=5,
    ))

    media = AutonomousMediaTools(
        pieces_jointes=pieces_jointes, vision_agent=vision_agent,
        video_agent=video_agent, registre=registre,
    )
    if pieces_jointes is not None:
        registry.register(Tool(
            "read_attachment",
            "Lit une pièce jointe documentaire déjà validée pour cette requête (PDF, DOCX, TXT, etc.).",
            AttachmentArgs, media.lire_document, timeout=10, contextual=True,
        ))
    if pieces_jointes is not None and vision_agent is not None:
        registry.register(Tool(
            "analyze_image",
            "Analyse réellement une image jointe à cette requête avec le moteur de vision d'ARENA.",
            AttachmentArgs, media.analyser_image, timeout=60, contextual=True,
        ))
    if video_agent is not None:
        registry.register(Tool(
            "analyze_video_audio",
            "Transcrit et analyse la piste audio d'une vidéo déjà uploadée. "
            "Ce n'est PAS une analyse visuelle des frames.",
            VideoArgs, media.analyser_video, timeout=120, contextual=True,
        ))
    if registre is not None:
        registry.register(Tool(
            "create_document",
            "Crée un vrai fichier téléchargeable (PDF/DOCX/MD/TXT/HTML) à partir d'un texte.",
            CreateDocumentArgs, media.creer_document, timeout=60, contextual=True,
        ))
    return registry
