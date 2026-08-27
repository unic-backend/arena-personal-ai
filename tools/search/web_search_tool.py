"""Recherche web, avec ce qu'il faut pour trouver de l'information récente.

Trois reglages de `ddgs` sont utilises ici, et chacun coute une reponse quand il
manque :

- `region` : sans lui, la recherche part en `us-en`. Une question en francais sur
  un club espagnol remonte des pages americaines.
- `timelimit` : sans contrainte de fraicheur, « le dernier match » ramene des
  pages de 2019 aussi volontiers que celle d'hier.
- la categorie `news` : distincte de `text`, elle rend des articles **dates**,
  classes par date. C'est la seule qui voit ce qui a moins d'une heure.

Mesure du 2026-08-27, machine du proprietaire. `news` sur « actualite Senegal »
avec un filtre de 24 h leve `DDGSException: No results found.` La version
precedente traitait cette exception comme une panne, se rabattait sur `text`, et
rendait cinq pages d'accueil de journaux — `seneweb.com`, `senego.com` — toutes
sans date. Le modele recevait donc des sommaires non dates pour repondre a une
question d'actualite, et comblait le vide en inventant.

Trois corrections en decoulent :

1. **une recherche vide n'est pas une erreur.** `No results found` est un
   resultat, pas une panne : on elargit au lieu d'abandonner.
2. **on elargit la requete avant de changer de categorie.** « actualite Senegal »
   sur 24 h rend zero ; « Senegal » sur 24 h rend cinq articles dates. Les mots
   de remplissage — actualite, dernieres, nouvelles — retrecissent la recherche
   au lieu de la preciser.
3. **une page d'accueil ne vaut pas un article.** `https://seneweb.com/` n'a pas
   de date et n'a pas de sujet ; elle passe apres tout ce qui est date.
"""
import logging
import re
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger("usman.tools.search")

REGION_PAR_DEFAUT = "fr-fr"

# `ddgs` leve une exception quand il ne trouve rien, au lieu de rendre une liste
# vide. Ce message-la ne signale aucune panne : ni reseau coupe, ni moteur en
# erreur, seulement une requete trop etroite.
ABSENCE_DE_RESULTAT = "no results found"

# Mots qui decrivent le *genre* de la demande, pas son sujet. Un moteur
# d'actualites indexe deja des actualites : les lui redemander ne fait que
# reduire le nombre de pages qui correspondent.
MOTS_DE_REMPLISSAGE = {
    "actualite", "actualites", "actu", "actus",
    "nouvelle", "nouvelles", "info", "infos", "information", "informations",
    "derniere", "dernieres", "dernier", "derniers",
    "recent", "recente", "recents", "recentes",
    "aujourd", "hui", "maintenant", "quoi", "de", "neuf", "sur", "les", "la",
    "le", "des", "du", "en", "au", "aux", "et",
}

ACCENTS = str.maketrans("àâäéèêëîïôöùûüç", "aaaeeeeiioouuuc")


def _sans_accent(mot: str) -> str:
    return mot.lower().translate(ACCENTS)


class WebSearchTool:
    """Outil de recherche web autonome local via ddgs."""

    def __init__(self, region: str = REGION_PAR_DEFAUT):
        self.region = region

    # --- Acces au moteur ------------------------------------------------------

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
            # Distinguer « rien trouve » de « le moteur est tombe » : le premier
            # est une information sur la requete, le second sur le systeme. Les
            # confondre a fait passer une requete trop etroite pour une panne.
            if ABSENCE_DE_RESULTAT in str(erreur).lower():
                logger.info(
                    "Aucun resultat en %s%s pour %r : on elargit.",
                    categorie,
                    f" ({timelimit})" if timelimit else "",
                    query[:60],
                )
            else:
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

    # --- Preparation de la requete -------------------------------------------

    @staticmethod
    def elargir(query: str) -> str:
        """Retire les mots qui decrivent le genre de la demande, pas son sujet.

        « dernieres actualites Senegal » devient « Senegal ». Rend une chaine
        vide si la requete n'etait faite que de ces mots-la : l'appelant saura
        alors qu'il n'y a rien a elargir.
        """
        mots = re.findall(r"[\w'-]+", query, flags=re.UNICODE)
        gardes = [m for m in mots if _sans_accent(m.strip("'-")) not in MOTS_DE_REMPLISSAGE]
        return " ".join(gardes).strip()

    @staticmethod
    def _est_page_daccueil(href: str) -> bool:
        """Vrai pour `https://seneweb.com/` ou `https://senego.com`, faux pour un article.

        Une page d'accueil change toutes les heures et ne porte aucune date : elle
        ne peut pas servir de source a une affirmation datee.
        """
        try:
            chemin = urlparse(href).path
        except Exception:
            return False
        return chemin.strip("/") == ""

    # --- Recherche ------------------------------------------------------------

    def search(self, query: str, max_results: int = 5, recent: bool = False) -> List[Dict[str, str]]:
        """Cherche, et privilegie ce qui est date quand `recent` est demande.

        Passes, dans l'ordre, chacune n'ayant lieu que si la precedente n'a pas
        suffi :

        1. `news` du jour — la seule qui voit ce qui a moins d'une heure ;
        2. `news` du jour sur la requete elargie — le cas mesure : « actualite
           Senegal » rend zero, « Senegal » rend cinq articles dates ;
        3. `news` de la semaine — un sujet peu couvert n'a pas d'article du jour ;
        4. `text` de la semaine ;
        5. `text` sans contrainte de date, pour ne jamais rendre zero resultat
           quand la reponse existe mais n'est pas recente.

        Sans `recent`, seule la derniere passe a lieu : une question intemporelle
        n'a rien a gagner a un filtre de fraicheur.

        Les resultats dates passent devant les autres, et les pages d'accueil
        passent en dernier : elles n'ont ni date ni sujet.
        """
        resultats: List[Dict[str, str]] = []
        vus = set()

        def ajouter(nouveaux):
            for r in nouveaux:
                if r["href"] and r["href"] not in vus:
                    vus.add(r["href"])
                    resultats.append(r)

        def il_en_manque() -> bool:
            return len(resultats) < max_results

        if recent:
            ajouter(self._executer("news", query, max_results, timelimit="d"))

            elargie = self.elargir(query)
            if il_en_manque() and elargie and elargie.lower() != query.lower():
                ajouter(self._executer("news", elargie, max_results, timelimit="d"))

            if il_en_manque():
                ajouter(self._executer("news", query, max_results, timelimit="w"))

            if il_en_manque():
                ajouter(self._executer("text", query, max_results, timelimit="w"))

        if il_en_manque():
            ajouter(self._executer("text", query, max_results))

        if not resultats:
            logger.warning(f"Aucun resultat pour : {query[:60]!r}")

        return self._classer(resultats, recent)[:max_results]

    @staticmethod
    def _classer(resultats: List[Dict[str, str]], recent: bool) -> List[Dict[str, str]]:
        """Date d'abord, page d'accueil en dernier. Ordre d'arrivee sinon.

        `sorted` est stable : a rang egal, l'ordre des passes est conserve, donc
        un article du jour reste devant un article de la semaine.
        """
        if not recent:
            return resultats

        def rang(r: Dict[str, str]) -> int:
            if WebSearchTool._est_page_daccueil(r.get("href", "")):
                return 2
            return 0 if r.get("date") else 1

        return sorted(resultats, key=rang)
