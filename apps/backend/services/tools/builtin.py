"""Calcul arithmetique borne et recherche HTTP sans execution arbitraire."""
import ast
import math
import operator
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field

from apps.backend.services.tools.registry import Tool, ToolRegistry, ToolResult
from core.models.confidentialite import Confidentialite, classer


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


def builtin_registry(client: httpx.AsyncClient, tavily_key: str = "") -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(Tool("calculate", "Calcule une expression arithmetique numerique.",
                           CalculateArgs, calculate, timeout=1))
    registry.register(Tool("web_search", "Recherche des faits et sources web. Ne jamais envoyer de secrets.",
                           SearchArgs, WebSearch(client, tavily_key), timeout=10))
    return registry
