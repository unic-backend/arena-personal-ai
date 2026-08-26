"""Recherche web, avec ce qu'il faut pour trouver de l'information récente.

Trois reglages de `ddgs` n'etaient pas utilises, et chacun coute une reponse :

- `region` : la recherche partait en `us-en` par defaut. Une question en
  francais sur un club espagnol remontait des pages americaines.
- `timelimit` : aucune contrainte de fraicheur. « Le dernier match » ramenait
  des pages de 2019 aussi volontiers que celle d'hier.
- la categorie `news` : distincte de `text`, elle rend des articles dates,
  classes par date. C'est la seule qui voit ce qui a moins d'une heure.

Mesure du 2026-08-26 : « quelle est la derniere victoire du Real Madrid en
championnat » a rendu **zero resultat**, et « quand joue-t-il son prochain
match » des pages sans aucune date.
"""
import logging
from typing import Dict, List

logger = logging.getLogger("usman.tools.search")

REGION_PAR_DEFAUT = "fr-fr"


class WebSearchTool:
    """Outil de recherche web autonome local via ddgs."""

    def __init__(self, region: str = REGION_PAR_DEFAUT):
        self.region = region

    def _executer(self, categorie: str, query: str, max_results: int, timelimit=None) -> List[Dict[str, str]]:
        """Lance une recherche d'une categorie donnee. Rend [] plutot que lever."""
        try:
            from ddgs import DDGS

            with DDGS() as ddgs:
                methode = getattr(ddgs, categorie)
                bruts = list(methode(
                    query,
                    region=self.region,
                    max_results=max_results,
                    **({"timelimit": timelimit} if timelimit else {}),
                ))
        except Exception as erreur:
            logger.warning(f"Recherche {categorie} impossible : {erreur}")
            return []

        resultats = []
        for r in bruts:
            resultats.append({
                "title": r.get("title", ""),
                "href": r.get("href") or r.get("url", ""),
                "body": r.get("body") or r.get("excerpt", ""),
                # `news` date ses articles ; `text` ne le fait pas. L'absence de
                # date est dite par None, jamais remplacee par la date du jour.
                "date": r.get("date"),
                "source": categorie,
            })
        return resultats

    def search(self, query: str, max_results: int = 5, recent: bool = False) -> List[Dict[str, str]]:
        """Cherche, et privilegie le recent quand `recent` est demande.

        Trois passes, et chacune n'a lieu que si la precedente n'a pas suffi :

        1. `news` du jour — la seule qui voit ce qui a moins d'une heure ;
        2. `text` de la semaine ;
        3. `text` sans contrainte de date, pour ne jamais rendre zero resultat
           quand la reponse existe mais n'est pas recente.

        Sans `recent`, seule la troisieme passe a lieu : une question intemporelle
        n'a rien a gagner a un filtre de fraicheur.
        """
        resultats: List[Dict[str, str]] = []
        vus = set()

        def ajouter(nouveaux):
            for r in nouveaux:
                if r["href"] and r["href"] not in vus:
                    vus.add(r["href"])
                    resultats.append(r)

        if recent:
            ajouter(self._executer("news", query, max_results, timelimit="d"))
            if len(resultats) < max_results:
                ajouter(self._executer("text", query, max_results, timelimit="w"))

        if len(resultats) < max_results:
            ajouter(self._executer("text", query, max_results))

        if not resultats:
            logger.warning(f"Aucun resultat pour : {query[:60]!r}")
        return resultats[:max_results]
