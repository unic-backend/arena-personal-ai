"""La connexion OAuth de LinkedIn (flux « code d'autorisation à 3 pattes ») — DEC-0209.

LinkedIn propose un générateur de jeton sur son site ; il s'est figé chez le
propriétaire (01/10/2026). Ce module donne à ARENA les deux gestes que
`apps/backend/routers/connectors.py` enchaîne déjà pour Google et TikTok :
l'adresse du consentement, puis l'échange du code contre le jeton d'accès.

Une application LinkedIn ordinaire ne reçoit **pas** de jeton de
renouvellement (réservé aux partenaires agréés) : le jeton d'accès vit environ
60 jours, puis il faut reconnecter. Quand il a expiré, la santé du connecteur
le dit (refus 401), au lieu de laisser croire que tout va bien.

Rien n'est stocké ici, et aucun secret n'est journalisé.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple
from urllib.parse import quote, urlencode

import httpx

URL_AUTORISATION = "https://www.linkedin.com/oauth/v2/authorization"
URL_JETON = "https://www.linkedin.com/oauth/v2/accessToken"

VARIABLE_ID = "LINKEDIN_CLIENT_ID"
VARIABLE_SECRET = "LINKEDIN_CLIENT_SECRET"

#: Identité du compte, et publier sur le profil — rien d'autre. Pas d'e-mail.
PORTEES_LINKEDIN = ["openid", "profile", "w_member_social"]

DELAI_SECONDES = 20.0


class RefusLinkedIn(RuntimeError):
    """LinkedIn a refusé l'échange ; le message ne porte aucun secret."""


def identifiants() -> Tuple[str, str]:
    """L'identifiant et le secret de l'application, tels que `.env` les porte."""
    return (os.getenv(VARIABLE_ID, "").strip(), os.getenv(VARIABLE_SECRET, "").strip())


def url_consentement(client_id: str, redirect_uri: str, state: str,
                     portees: List[str]) -> str:
    """L'écran de consentement LinkedIn. Les portées sont séparées par des espaces."""
    return f"{URL_AUTORISATION}?" + urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": " ".join(portees),
    }, quote_via=quote)


def code_pour_jetons(client_id: str, client_secret: str, code: str,
                     redirect_uri: str) -> Dict[str, Any]:
    """Échange le code contre `access_token`.

    Un corps sans `access_token` est un refus, quel que soit le code HTTP :
    l'absence du jeton est le critère, pas le statut.
    """
    with httpx.Client(timeout=DELAI_SECONDES, trust_env=False) as client:
        reponse = client.post(URL_JETON, data={
            "grant_type": "authorization_code", "code": code,
            "client_id": client_id, "client_secret": client_secret,
            "redirect_uri": redirect_uri})
    try:
        charge = reponse.json()
    except ValueError as erreur:
        raise RefusLinkedIn(f"reponse illisible ({reponse.status_code})") from erreur
    if not isinstance(charge, dict) or not charge.get("access_token"):
        raison = (charge or {}).get("error") if isinstance(charge, dict) else None
        raise RefusLinkedIn(str(raison or reponse.status_code))
    return charge
