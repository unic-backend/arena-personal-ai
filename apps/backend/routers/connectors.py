"""`/connectors` — le vrai chemin CONNECT -> OAUTH -> CONSENTEMENT -> CALLBACK
-> JETON STOCKE, pour de vrai.

Avant ce fichier, l'interface (PWA) affichait un bouton « Connecter » sur
Gmail qui n'appelait **aucune route existante** : `apps/backend/main.py` ne
montait aucun routeur `connectors`, et l'echange Google
(`core/connectors/google_oauth.py`) ne savait qu'echanger un
`refresh_token` deja obtenu ailleurs — jamais initier le consentement.
Le clic ne faisait donc rien, sans le dire.

**Seul Gmail est cable ici** (demande explicite du 31/08/2026 : Gmail
d'abord, de bout en bout). Un fournisseur qui n'est pas dans
`FOURNISSEURS_OAUTH` recoit une reponse honnete — jamais un faux succes.

Trois regles :

1. **`/auth` exige la cle d'ARENA.** Sans elle, n'importe qui pourrait relier
   son propre compte Google au courrier du proprietaire — la cle est en
   parametre `cle` en plus de l'en-tete, parce qu'une redirection de
   navigateur (`window.open`) ne peut jamais poser d'en-tete `Authorization`.
2. **Le `state` est a usage unique et court.** Il protege le retour du
   consentement contre un lien rejoue ou force depuis un autre onglet — la
   seule chose qu'un attaquant pourrait manipuler sur `/callback`, qui est
   appele par Google lui-meme, jamais par la cle d'ARENA.
3. **Le jeton obtenu est ecrit cote serveur, jamais renvoye au navigateur.**
   `os.environ` pour un effet immediat ; `.env` pour survivre a un
   redemarrage quand ce fichier existe (deploiement hors plateforme
   Railway/Render, ou la variable vit dans leur panneau, pas dans un fichier).
"""
import json
import logging
import os
import secrets
import time
from typing import Dict, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from apps.backend import security as securite
from apps.backend.config import BASE_DIR
from apps.backend.runtime import registre
from apps.backend.security import cle_presentee_valide, limiter_debit
from core.connectors.base import EtatSante
from core.connectors.google_oauth import (
    PORTEE_GMAIL_ENVOI,
    PORTEE_GMAIL_LECTURE,
    code_pour_jetons,
    identifiants,
    url_consentement,
)

logger = logging.getLogger("usman.backend.connectors")
router = APIRouter(prefix="/connectors", tags=["connectors"])

#: Duree de vie d'un `state` CSRF avant expiration : le temps de choisir un
#: compte Google et de consentir, jamais plus.
DUREE_STATE_SECONDES = 600.0

#: state -> (fournisseur, expiration monotonic). En memoire : ARENA est
#: mono-processus et mono-proprietaire, rien n'exige un stockage partage.
_ETATS_EN_ATTENTE: Dict[str, Tuple[str, float]] = {}

#: Ce que ce chantier cable reellement. Un fournisseur absent d'ici recoit une
#: erreur qui le dit, plutot qu'un bouton qui ne fait rien.
FOURNISSEURS_OAUTH = {
    "gmail": {
        "portees": [PORTEE_GMAIL_LECTURE, PORTEE_GMAIL_ENVOI],
        "variable_env": "GOOGLE_REFRESH_TOKEN",
    },
}


def _cle_valide(request: Request) -> bool:
    """En-tete `Authorization` OU parametre `cle` — la meme regle que
    `verify_media_access` (`apps/backend/security.py`), pour la meme raison :
    une redirection de navigateur ne pose jamais d'en-tete."""
    if cle_presentee_valide(request.headers.get("authorization")):
        return True
    return bool(securite.USMAN_API_KEY) and request.query_params.get("cle") == securite.USMAN_API_KEY


def _redirect_uri(fournisseur: str) -> str:
    """L'URL de retour, telle qu'elle doit etre enregistree dans la console du
    fournisseur. Explicite dans `.env` — jamais devinee depuis les en-tetes de
    la requete, qu'un proxy (DEC-0021) peut reecrire."""
    base = os.getenv(
        "PUBLIC_BASE_URL", f"http://127.0.0.1:{os.getenv('APP_PORT', '8000')}"
    ).rstrip("/")
    return f"{base}/connectors/{fournisseur}/callback"


def _purger_etats_expires() -> None:
    maintenant = time.monotonic()
    perimes = [s for s, (_, expire) in _ETATS_EN_ATTENTE.items() if expire < maintenant]
    for s in perimes:
        _ETATS_EN_ATTENTE.pop(s, None)


def _persister_refresh_token(variable: str, valeur: str) -> None:
    """Ecrit le jeton dans le processus courant ET, si possible, dans `.env`.

    L'environnement du processus d'abord : le prochain appel Gmail marche
    sans redemarrer le serveur. `.env` ensuite, en best-effort — sur une
    plateforme hebergee (Railway et semblables), les variables vivent dans
    son panneau et aucun fichier `.env` n'existe sur le disque : l'ecriture
    fichier est alors sautee et journalisee, jamais une erreur qui casserait
    la connexion pourtant reussie.
    """
    os.environ[variable] = valeur
    chemin = BASE_DIR / ".env"
    if not chemin.exists():
        logger.info(
            "%s mis a jour en memoire ; aucun fichier .env sur disque pour le "
            "persister (plateforme hebergee ?).", variable)
        return
    try:
        lignes = chemin.read_text(encoding="utf-8").splitlines()
        prefixe = f"{variable}="
        trouve = False
        for i, ligne in enumerate(lignes):
            if ligne.startswith(prefixe):
                lignes[i] = f"{prefixe}{valeur}"
                trouve = True
                break
        if not trouve:
            lignes.append(f"{prefixe}{valeur}")
        chemin.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    except OSError as erreur:
        logger.warning(
            "%s mis a jour en memoire mais pas persiste dans .env (%s) : il "
            "faudra reconnecter apres un redemarrage.", variable, erreur)


def _page(message: str, script: str = "") -> HTMLResponse:
    """Une page minimale pour la fenetre popup — jamais l'interface elle-meme."""
    return HTMLResponse(
        "<!doctype html><html><body style=\"font-family:sans-serif;"
        "background:#0a0a0a;color:#e5e5e5;display:flex;align-items:center;"
        "justify-content:center;height:100vh;margin:0;text-align:center;"
        "padding:0 24px\">"
        f"<p>{message}</p></body>"
        f"<script>{script}</script></html>"
    )


def _page_succes(fournisseur: str, compte: str) -> HTMLResponse:
    charge = json.dumps({"type": "usman_oauth_success", "connector": fournisseur,
                         "account": compte})
    script = (
        f"if (window.opener) {{ window.opener.postMessage({charge}, "
        "window.location.origin); }} setTimeout(function(){ window.close(); }, 600);"
    )
    return _page(f"{fournisseur} connecte. Cette fenetre se ferme...", script)


def _page_erreur(message: str) -> HTMLResponse:
    return _page(message, "setTimeout(function(){ window.close(); }, 4000);")


# --- CONNECT -> AUTHENTIFICATION -----------------------------------------------

@router.get("/{fournisseur}/auth")
async def demarrer_oauth(fournisseur: str, request: Request):
    """Redirige vers l'ecran de consentement du fournisseur. Rien n'est stocke ici."""
    limiter_debit(request)
    if not _cle_valide(request):
        raise HTTPException(status_code=401, detail="Cle API invalide ou manquante.")

    config = FOURNISSEURS_OAUTH.get(fournisseur)
    if config is None:
        raise HTTPException(
            status_code=404,
            detail=(f"« {fournisseur} » n'a pas de flux OAuth cable. Cables "
                    f"aujourd'hui : {', '.join(sorted(FOURNISSEURS_OAUTH)) or 'aucun'}."),
        )

    client_id, client_secret, _ = identifiants()
    if not (client_id and client_secret):
        raise HTTPException(
            status_code=409,
            detail=("GOOGLE_CLIENT_ID et GOOGLE_CLIENT_SECRET absents de .env : "
                     "cree l'app OAuth sur console.cloud.google.com (ecran de "
                     "consentement + identifiant « application web », URI de "
                     f"redirection {_redirect_uri(fournisseur)}) avant de connecter."),
        )

    _purger_etats_expires()
    state = secrets.token_urlsafe(32)
    _ETATS_EN_ATTENTE[state] = (fournisseur, time.monotonic() + DUREE_STATE_SECONDES)

    url = url_consentement(client_id, _redirect_uri(fournisseur), state, config["portees"])
    return RedirectResponse(url, status_code=302)


# --- CALLBACK -> TOKEN STORAGE --------------------------------------------------

@router.get("/{fournisseur}/callback")
async def recevoir_callback(
    fournisseur: str,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
) -> HTMLResponse:
    """Google revient ici avec `code`+`state`, ou `error` si le proprietaire refuse."""
    if error:
        return _page_erreur(f"Google a refuse : {error}")

    config = FOURNISSEURS_OAUTH.get(fournisseur)
    if config is None:
        return _page_erreur(f"« {fournisseur} » n'a pas de flux OAuth cable.")

    if not code or not state:
        return _page_erreur("Reponse incomplete de Google : rien a echanger.")

    _purger_etats_expires()
    entree = _ETATS_EN_ATTENTE.pop(state, None)
    if entree is None or entree[0] != fournisseur:
        return _page_erreur(
            "Lien de consentement expire ou deja utilise. Relance la "
            "connexion depuis ARENA.")

    client_id, client_secret, _ = identifiants()
    if not (client_id and client_secret):
        return _page_erreur("GOOGLE_CLIENT_ID/SECRET absents : impossible d'echanger le code.")

    try:
        jetons = code_pour_jetons(client_id, client_secret, code, _redirect_uri(fournisseur))
    except Exception as erreur:  # noqa: BLE001 — un refus Google se rapporte, ne remonte pas
        logger.info("Echange du code OAuth %s refuse : %s", fournisseur, type(erreur).__name__)
        return _page_erreur("Google a refuse l'echange du code.")

    refresh = jetons.get("refresh_token") if isinstance(jetons, dict) else None
    if not refresh:
        # `prompt=consent&access_type=offline` (deja force a l'etape /auth)
        # garantit normalement un refresh_token — ceci ne devrait arriver que
        # si Google change son comportement.
        return _page_erreur(
            "Google n'a pas renvoye de jeton de rafraichissement. Revoque "
            "l'acces sur myaccount.google.com/permissions puis reessaie.")

    _persister_refresh_token(config["variable_env"], str(refresh))

    sante = registre.sante(fournisseur)
    compte = sante.message if sante.etat == EtatSante.OPERATIONNEL else "compte connecte"
    return _page_succes(fournisseur, compte)


# --- STATUT & DECONNEXION -------------------------------------------------------

@router.get("/{fournisseur}/status")
async def etat_connecteur(fournisseur: str, request: Request) -> Dict[str, object]:
    """Interroge (via `sonder()`, deja mis en cache 60 s cote connecteur) sans
    jamais rien affirmer de plausible : `connected` vient d'un vrai appel API."""
    limiter_debit(request)
    if not _cle_valide(request):
        raise HTTPException(status_code=401, detail="Cle API invalide ou manquante.")
    if fournisseur not in FOURNISSEURS_OAUTH and not registre.est_declare(fournisseur):
        raise HTTPException(status_code=404, detail=f"Connecteur « {fournisseur} » inconnu.")

    sante = registre.sante(fournisseur)
    connecte = sante.etat == EtatSante.OPERATIONNEL
    return {
        "connected": connecte,
        "verified": connecte,
        "account": sante.message if connecte else None,
        "etat": sante.etat.value,
        "message": sante.message or sante.ce_qui_manque,
    }


@router.post("/{fournisseur}/disconnect")
async def deconnecter(fournisseur: str, request: Request) -> Dict[str, bool]:
    """Efface uniquement le jeton de rafraichissement — jamais l'identifiant OAuth
    (client_id/secret), qui reste utile pour se reconnecter ensuite."""
    limiter_debit(request)
    if not _cle_valide(request):
        raise HTTPException(status_code=401, detail="Cle API invalide ou manquante.")

    config = FOURNISSEURS_OAUTH.get(fournisseur)
    if config is None:
        raise HTTPException(
            status_code=404, detail=f"« {fournisseur} » n'a pas de flux OAuth cable.")

    _persister_refresh_token(config["variable_env"], "")
    return {"connected": False}
