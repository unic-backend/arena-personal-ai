import logging
from typing import Dict, List

logger = logging.getLogger("usman.tools.search")

class WebSearchTool:
    """Outil de recherche web autonome local via ddgs."""

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """Effectue une recherche Web et renvoie les résultats."""
        try:
            from ddgs import DDGS
            results = []
            with DDGS() as ddgs:
                ddg_results = list(ddgs.text(query, max_results=max_results))
                for r in ddg_results:
                    results.append({
                        "title": r.get("title", ""),
                        "href": r.get("href", ""),
                        "body": r.get("body", "")
                    })
            return results
        except Exception as e:
            logger.error(f"Erreur de recherche web: {e}")
            return []
