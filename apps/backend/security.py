"""Contrôles de sécurité des routes : authentification, débit, chemins de fichiers.

Ces trois fonctions décident si une requête a le droit d'aller plus loin. Les
regrouper les rend lisibles d'un seul coup d'œil — et rend visible ce qui n'y
figure pas.
"""
import logging
from pathlib import Path
from typing import Optional

from fastapi import Header, HTTPException, Request

from apps.backend.config import (
    FENETRE_SECONDES,
    MEDIA_DIR,
    REQUETES_MAX,
    USMAN_API_KEY,
)
from apps.backend.rate_limit import LimiteurDebit

logger = logging.getLogger("usman.backend")

# Compteur partage par toutes les routes limitees.
limiteur = LimiteurDebit(requetes_max=REQUETES_MAX, fenetre_secondes=FENETRE_SECONDES)


def client_de(request: Request) -> str:
    """Identifie l'appelant pour la limitation de debit et les journaux."""
    return request.client.host if request.client else "inconnu"


def cle_presentee_valide(authorization: Optional[str]) -> bool:
    """Dit si l'en-tete presente la bonne cle. **Ne leve jamais.**

    Existe pour que `/health` puisse *dire* si la cle est bonne sans refuser la
    requete. Le panneau de l'interface passait au vert avec une mauvaise cle,
    parce que la seule facon de verifier levait une erreur — donc `/health` ne
    verifiait rien. Mesure le 2026-08-27 : « BACKEND · ARENA · 544MS » en vert,
    et chaque message refuse en 401.
    """
    return bool(USMAN_API_KEY) and authorization == f"Bearer {USMAN_API_KEY}"


def verify_api_key(request: Request, authorization: Optional[str] = Header(None)):
    """Bloque tout appel a /v1 ou /api qui ne presente pas la bonne cle Bearer.

    Un refus est journalise avec l'adresse de l'appelant et la route visee.
    La cle presentee n'est jamais ecrite dans les journaux : un journal qui
    contient des secrets est un secret de plus a proteger.
    """
    if not USMAN_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="USMAN_API_KEY absente du fichier .env : passerelle desactivee par securite."
        )
    if not cle_presentee_valide(authorization):
        motif = "cle absente" if not authorization else "cle invalide"
        logger.warning(
            "Authentification refusee (%s) : %s -> %s",
            motif, client_de(request), request.url.path,
        )
        raise HTTPException(status_code=401, detail="Cle API invalide ou manquante.")
    return True


def limiter_debit(request: Request):
    """Refuse une requete de trop et indique dans combien de temps reessayer."""
    client = client_de(request)
    attente = limiteur.secondes_a_attendre(client)
    if attente is None:
        return True

    logger.warning(
        "Debit depasse : %s -> %s (%s requetes / %ss)",
        client, request.url.path, REQUETES_MAX, FENETRE_SECONDES,
    )
    raise HTTPException(
        status_code=429,
        detail=f"Trop de requetes : maximum {REQUETES_MAX} par {FENETRE_SECONDES:.0f} s.",
        headers={"Retry-After": str(max(1, int(attente) + 1))},
    )


def validate_media_path(raw_path: str) -> Path:
    """Garantit qu'un chemin de fichier reste a l'interieur du dossier media/."""
    p = Path(raw_path).resolve()
    try:
        p.relative_to(MEDIA_DIR.resolve())
    except ValueError:
        # `from None` : l'erreur interne de chemin n'a pas a remonter au client.
        raise HTTPException(
            status_code=403,
            detail="Acces refuse : le fichier doit se trouver dans le dossier media/."
        ) from None
    return p
