"""Contrôles de sécurité des routes : authentification, débit, chemins de fichiers.

Ces trois fonctions décident si une requête a le droit d'aller plus loin. Les
regrouper les rend lisibles d'un seul coup d'œil — et rend visible ce qui n'y
figure pas.
"""
import logging
import secrets
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

#: Au-dela de ce nombre de clients suivis, la table est purgee de ceux qui
#: n'ont plus aucun passage dans la fenetre.
#:
#: `LimiteurDebit.nettoyer()` existait, etait teste, et **personne ne
#: l'appelait** — mesure du 31/08/2026. Son propre module annonce pourtant la
#: consequence : « sans cela, la table grandirait indefiniment au fil des
#: adresses vues ». Une adresse vue une fois y restait pour la duree de vie du
#: processus.
#:
#: Purger ici plutot que dans une tache de fond : le limiteur est deja sur le
#: chemin de chaque requete limitee, et `nettoyer()` ne coute qu'un parcours
#: de la table — sans nouveau fil ni nouvelle horloge a entretenir.
CLIENTS_AVANT_PURGE = 512


def purger_les_clients_inactifs() -> int:
    """Purge la table du limiteur quand elle depasse le seuil. Rend le nombre efface.

    Un client encore dans sa fenetre n'est jamais efface : `nettoyer()` ne
    retire que ceux dont tous les passages sont sortis de la fenetre.
    """
    if limiteur.clients_suivis() <= CLIENTS_AVANT_PURGE:
        return 0
    efaces = limiteur.nettoyer()
    if efaces:
        logger.info("Limiteur de debit : %s client(s) inactif(s) oublie(s).", efaces)
    return efaces


def client_de(request: Request) -> str:
    """Identifie l'appelant pour la limitation de debit et les journaux."""
    return request.client.host if request.client else "inconnu"


def _egales(presente: str, attendue: str) -> bool:
    """Compare deux secrets sans que la duree de la comparaison en dise long.

    `==` sur des chaines s'arrete au premier caractere qui differe : le temps
    de reponse depend alors du nombre de caracteres devines juste. Ce n'est pas
    un defaut mesure ici — le canal est etroit et le serveur est personnel —
    c'est la facon standard de comparer un secret, et elle ne coute rien.

    `compare_digest` exige des octets comparables : un en-tete non-ASCII leve
    plutot que de repondre, et une clé n'est jamais non-ASCII.
    """
    try:
        return secrets.compare_digest(presente, attendue)
    except TypeError:  # en-tete non-ASCII : ce n'est pas la cle
        return False


def cle_presentee_valide(authorization: Optional[str]) -> bool:
    """Dit si l'en-tete presente la bonne cle. **Ne leve jamais.**

    Existe pour que `/health` puisse *dire* si la cle est bonne sans refuser la
    requete. Le panneau de l'interface passait au vert avec une mauvaise cle,
    parce que la seule facon de verifier levait une erreur — donc `/health` ne
    verifiait rien. Mesure le 2026-08-27 : « BACKEND · ARENA · 544MS » en vert,
    et chaque message refuse en 401.
    """
    if not USMAN_API_KEY or not authorization:
        return False
    return _egales(authorization, f"Bearer {USMAN_API_KEY}")


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


def verify_media_access(request: Request, authorization: Optional[str] = Header(None)):
    """Comme `verify_api_key`, avec un repli en parametre `cle` — pour tout appel
    qui ne part pas d'un `fetch()`/XHR et ne peut donc jamais poser d'en-tete
    `Authorization`.

    Deux usages reels : un `<video src="...">` ou `<img src="...">` qui charge
    son URL directement depuis le navigateur (`/media/rendered`, VOLET « ARENA
    en ligne », phase 4.2), et la redirection `window.open()` vers
    `/connectors/{fournisseur}/auth` (chapitre 8.2, connecteurs reels) — un
    popup OAuth navigue vers l'URL, il ne l'appelle pas en `fetch()`. Le reste
    de la passerelle garde `verify_api_key` tel quel.
    """
    if not USMAN_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="USMAN_API_KEY absente du fichier .env : passerelle desactivee par securite."
        )
    if cle_presentee_valide(authorization):
        return True
    cle_en_parametre = request.query_params.get("cle")
    if cle_en_parametre and _egales(cle_en_parametre, USMAN_API_KEY):
        return True

    motif = "cle absente" if not authorization and "cle" not in request.query_params else "cle invalide"
    logger.warning(
        "Authentification refusee media (%s) : %s -> %s",
        motif, client_de(request), request.url.path,
    )
    raise HTTPException(status_code=401, detail="Cle API invalide ou manquante.")


def limiter_debit(request: Request):
    """Refuse une requete de trop et indique dans combien de temps reessayer."""
    purger_les_clients_inactifs()
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
