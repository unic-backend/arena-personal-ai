"""Lecture d'une page web citée comme source.

Le web est une couche de connaissance externe : ARENA va y chercher ce qu'il ne
sait pas, puis **cite ce qu'il a lu**. Cet outil est l'étape de lecture.

Trois règles qui font la différence avec un simple `requests.get` :

1. **Une page inaccessible est signalée, jamais devinée.** L'outil renvoie un
   état (`FETCHED`, `REFUSED`, `FAILED`) ; il ne renvoie jamais un texte
   plausible à la place d'un texte réel.
2. **Une adresse interne est refusée.** Les URL viennent d'un moteur de
   recherche, donc de l'extérieur. Sans ce garde-fou, une adresse pointant sur
   `127.0.0.1` ou sur le réseau local ferait lire à ARENA ses propres services.
3. **La taille et la durée sont plafonnées.** Une page de 500 Mo ne doit pas
   pouvoir occuper la mémoire ni bloquer la requête.
"""
from __future__ import annotations

import ipaddress
import logging
import re
import socket
from html.parser import HTMLParser
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("arena.tools.source_fetcher")

# Un texte de source utile tient largement dans cette limite ; au-delà, on tronque.
TAILLE_MAX_OCTETS = 2 * 1024 * 1024
CARACTERES_MAX = 20_000
DELAI_SECONDES = 10.0

SCHEMAS_AUTORISES = {"http", "https"}
TYPES_LISIBLES = ("text/html", "text/plain", "application/xhtml+xml")

# Un en-tête honnête : le site sait qui le lit et peut refuser.
AGENT_UTILISATEUR = "ARENA-PersonalAI/1.0 (lecteur de sources, respecte robots.txt)"

# Balises dont le contenu n'est pas du texte lisible.
BALISES_IGNOREES = {"script", "style", "noscript", "template", "svg", "head"}
# Balises après lesquelles un saut de ligne a du sens.
BALISES_BLOC = {
    "p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "header", "footer", "blockquote",
}


class _ExtracteurDeTexte(HTMLParser):
    """Extrait le texte lisible d'une page HTML.

    Volontairement écrit sur la bibliothèque standard : `beautifulsoup4` ferait
    un peu mieux sur les pages mal formées, mais ce projet évite une dépendance
    directe de plus pour un gain marginal.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._morceaux: list[str] = []
        self._profondeur_ignoree = 0
        self.titre: Optional[str] = None
        self._dans_le_titre = False

    def handle_starttag(self, tag, attrs):
        if tag in BALISES_IGNOREES:
            self._profondeur_ignoree += 1
        elif tag == "title":
            self._dans_le_titre = True
        elif tag in BALISES_BLOC:
            self._morceaux.append("\n")

    def handle_endtag(self, tag):
        if tag in BALISES_IGNOREES and self._profondeur_ignoree:
            self._profondeur_ignoree -= 1
        elif tag == "title":
            self._dans_le_titre = False
        elif tag in BALISES_BLOC:
            self._morceaux.append("\n")

    def handle_data(self, data):
        if self._dans_le_titre and self.titre is None:
            self.titre = data.strip() or None
        if not self._profondeur_ignoree:
            self._morceaux.append(data)

    @property
    def texte(self) -> str:
        brut = "".join(self._morceaux)
        # Espaces multiples réduits, lignes vides successives réduites à une.
        brut = re.sub(r"[ \t ]+", " ", brut)
        brut = re.sub(r"\n\s*\n\s*", "\n\n", brut)
        return brut.strip()


def extraire_texte(contenu: str, type_contenu: str = "text/html") -> tuple[str, Optional[str]]:
    """Renvoie (texte lisible, titre) à partir du contenu d'une page."""
    if "html" not in type_contenu:
        return contenu.strip(), None

    extracteur = _ExtracteurDeTexte()
    try:
        extracteur.feed(contenu)
        extracteur.close()
    except Exception as e:  # une page mal formée ne doit pas faire tomber l'agent
        logger.debug(f"Extraction HTML interrompue : {e}")
    return extracteur.texte, extracteur.titre


def adresse_interne(hote: str) -> bool:
    """Vrai si le nom résout vers une adresse locale, privée ou de bouclage."""
    try:
        infos = socket.getaddrinfo(hote, None)
    except OSError:
        # Nom irrésolvable : on refuse, faute de pouvoir vérifier.
        return True

    for info in infos:
        adresse = ipaddress.ip_address(info[4][0])
        if (
            adresse.is_private
            or adresse.is_loopback
            or adresse.is_link_local
            or adresse.is_reserved
            or adresse.is_multicast
            or adresse.is_unspecified
        ):
            return True
    return False


def _refus(url: str, raison: str) -> Dict[str, Any]:
    logger.warning(f"Source refusee ({raison}) : {url}")
    return {"status": "REFUSED", "url": url, "reason": raison, "text": "", "title": None}


def _echec(url: str, raison: str) -> Dict[str, Any]:
    logger.info(f"Source illisible ({raison}) : {url}")
    return {"status": "FAILED", "url": url, "reason": raison, "text": "", "title": None}


class SourceFetcher:
    """Lit une page web et en extrait le texte, ou dit pourquoi elle ne l'a pas lue."""

    def __init__(
        self,
        delai_secondes: float = DELAI_SECONDES,
        taille_max: int = TAILLE_MAX_OCTETS,
        caracteres_max: int = CARACTERES_MAX,
        autoriser_adresses_internes: bool = False,
    ):
        self.delai_secondes = delai_secondes
        self.taille_max = taille_max
        self.caracteres_max = caracteres_max
        # Uniquement pour les tests : jamais vrai en fonctionnement normal.
        self.autoriser_adresses_internes = autoriser_adresses_internes

    def _verifier_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Renvoie un refus si l'URL ne doit pas être lue, sinon None."""
        try:
            analysee = urlparse(url)
        except ValueError:
            return _refus(url, "URL illisible")

        if analysee.scheme not in SCHEMAS_AUTORISES:
            return _refus(url, f"schema non autorise : {analysee.scheme or 'aucun'}")
        if not analysee.hostname:
            return _refus(url, "adresse sans nom d'hote")
        if not self.autoriser_adresses_internes and adresse_interne(analysee.hostname):
            return _refus(url, "adresse interne ou irresolvable")
        return None

    async def fetch(self, url: str) -> Dict[str, Any]:
        """Télécharge une page et renvoie son texte, ou l'état qui explique l'échec."""
        refus = self._verifier_url(url)
        if refus is not None:
            return refus

        try:
            async with httpx.AsyncClient(
                timeout=self.delai_secondes,
                follow_redirects=True,
                headers={"User-Agent": AGENT_UTILISATEUR},
            ) as client:
                async with client.stream("GET", url) as reponse:
                    if reponse.status_code >= 400:
                        return _echec(url, f"code HTTP {reponse.status_code}")

                    type_contenu = reponse.headers.get("content-type", "").lower()
                    if not any(t in type_contenu for t in TYPES_LISIBLES):
                        return _echec(url, f"type non lisible : {type_contenu or 'inconnu'}")

                    octets = bytearray()
                    async for bloc in reponse.aiter_bytes():
                        octets.extend(bloc)
                        if len(octets) >= self.taille_max:
                            logger.info(f"Source tronquee a {self.taille_max} octets : {url}")
                            break
                    encodage = reponse.encoding or "utf-8"
        except httpx.TimeoutException:
            return _echec(url, f"delai depasse ({self.delai_secondes} s)")
        except Exception as e:
            return _echec(url, f"{type(e).__name__}: {e}")

        contenu = bytes(octets).decode(encodage, errors="replace")
        texte, titre = extraire_texte(contenu, type_contenu)
        tronque = len(texte) > self.caracteres_max

        return {
            "status": "FETCHED",
            "url": url,
            "title": titre,
            "text": texte[: self.caracteres_max],
            "truncated": tronque,
            "characters": min(len(texte), self.caracteres_max),
        }


__all__ = ["SourceFetcher", "extraire_texte", "adresse_interne"]
