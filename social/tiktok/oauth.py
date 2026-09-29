"""La connexion OAuth de TikTok (Login Kit pour le web) — DEC-0186.

TikTok ne donne un jeton de renouvellement qu'au bout d'un consentement : il
n'existe pas de generateur de jeton comme chez LinkedIn. Ce module fournit les
deux gestes que `apps/backend/routers/connectors.py` enchaine deja pour
Google : l'adresse du consentement, puis l'echange du code contre les jetons.

Rien n'est stocke ici, et aucun secret n'est journalise.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple
from urllib.parse import urlencode

import httpx

from social.tiktok.tiktok_connector import URL_JETON, VARIABLE_CLE, VARIABLE_SECRET

URL_AUTORISATION = "https://www.tiktok.com/v2/auth/authorize/"

#: Lire le compte, publier, deposer un brouillon — rien d'autre.
PORTEES_TIKTOK = ["user.info.basic", "video.publish", "video.upload"]

DELAI_SECONDES = 20.0


class RefusTikTok(RuntimeError):
    """TikTok a refuse l'echange ; le message ne porte aucun secret."""


def identifiants() -> Tuple[str, str]:
    """La cle et le secret de l'application, tels que `.env` les porte."""
    return (os.getenv(VARIABLE_CLE, "").strip(), os.getenv(VARIABLE_SECRET, "").strip())


def url_consentement(client_key: str, redirect_uri: str, state: str,
                     portees: List[str]) -> str:
    """L'ecran de consentement TikTok. Les portees sont separees par des virgules."""
    return f"{URL_AUTORISATION}?" + urlencode({
        "client_key": client_key,
        "scope": ",".join(portees),
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
    })


def code_pour_jetons(client_key: str, client_secret: str, code: str,
                     redirect_uri: str) -> Dict[str, Any]:
    """Echange le code contre `access_token` et `refresh_token`.

    TikTok peut repondre 200 avec une erreur dans le corps : l'absence de
    `refresh_token` est donc le critere, pas le code HTTP.
    """
    with httpx.Client(timeout=DELAI_SECONDES) as client:
        reponse = client.post(URL_JETON, data={
            "client_key": client_key, "client_secret": client_secret, "code": code,
            "grant_type": "authorization_code", "redirect_uri": redirect_uri})
    try:
        charge = reponse.json()
    except ValueError as erreur:
        raise RefusTikTok(f"reponse illisible ({reponse.status_code})") from erreur
    if not isinstance(charge, dict) or not charge.get("refresh_token"):
        raise RefusTikTok(str((charge or {}).get("error") or reponse.status_code))
    return charge
