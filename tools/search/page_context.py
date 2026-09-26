"""Contexte borné d'une page web pour le mode « discuter avec cette page ».

Inspire de Page Assist (MIT), sans reprendre son extension ni son stockage.
Arena reutilise SourceFetcher : meme SSRF guard, limites et extraction HTML.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from core.security.trust import TrustLevel, wrap
from tools.search.source_fetcher import SourceFetcher

CARACTERES_CONTEXTE_MAX = 12_000


@dataclass(frozen=True)
class ContextePage:
    url: str
    titre: str
    texte: str
    tronque: bool
    caracteres_source: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "titre": self.titre,
            "texte": self.texte,
            "tronque": self.tronque,
            "caracteres_source": self.caracteres_source,
            "provenance": self.url,
            "confiance": TrustLevel.EXTERNAL.value,
        }


class LecteurContextePage:
    """Lit une URL externe et la transforme en contexte non fiable borne."""

    def __init__(self, fetcher: SourceFetcher | None = None, limite: int = CARACTERES_CONTEXTE_MAX):
        self.fetcher = fetcher or SourceFetcher()
        self.limite = max(1, min(int(limite), CARACTERES_CONTEXTE_MAX))

    async def lire(self, url: str) -> Dict[str, Any]:
        source = await self.fetcher.fetch(url)
        if source.get("status") != "FETCHED":
            return {
                "status": source.get("status") or "FAILED",
                "url": source.get("url") or url,
                "reason": source.get("reason") or "page illisible",
            }

        brut = str(source.get("text") or "")
        texte = brut[: self.limite]
        enveloppe = wrap(texte, TrustLevel.EXTERNAL, f"page:{source['url']}").text
        contexte = ContextePage(
            url=str(source["url"]),
            titre=str(source.get("title") or ""),
            texte=enveloppe,
            tronque=bool(source.get("truncated")) or len(brut) > self.limite,
            caracteres_source=int(source.get("characters") or len(brut)),
        )
        return {"status": "READY", **contexte.to_dict()}


__all__ = ["CARACTERES_CONTEXTE_MAX", "ContextePage", "LecteurContextePage"]
