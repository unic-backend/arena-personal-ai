"""`/connectors` — le vrai chemin CONNECT -> OAUTH -> CONSENTEMENT -> CALLBACK
-> JETON STOCKE, pour de vrai.

Avant ce fichier, l'interface (PWA) affichait un bouton « Connecter » sur
Gmail qui n'appelait **aucune route existante** : `apps/backend/main.py` ne
montait aucun routeur `connectors`, et l'echange Google
(`core/connectors/google_oauth.py`) ne savait qu'echanger un
`refresh_token` deja obtenu ailleurs — jamais initier le consentement.
Le clic ne faisait donc rien, sans le dire.

**Cables ici** : Gmail (demande explicite du 31/08/2026, de bout en bout),
la fiche Google (DEC-0184, meme jeton) et TikTok (DEC-0186, Login Kit). Un
fournisseur qui n'est pas dans `FOURNISSEURS_OAUTH` recoit une reponse
honnete — jamais un faux succes.

Trois regles :

1. **`/auth` exige la cle d'ARENA — via `verify_media_access`, deja ecrite et
   testee.** Sans elle, n'importe qui pourrait relier son propre compte
   Google au courrier du proprietaire. Cette dependance accepte l'en-tete OU
   le parametre `cle` : une redirection de navigateur (`window.open`) ne peut
   jamais poser d'en-tete `Authorization`. `/status` et `/disconnect`
   viennent d'un `fetch()`, qui le peut : ils gardent `verify_api_key`.
2. **Le `state` est a usage unique et court.** Il protege le retour du
   consentement contre un lien rejoue ou force depuis un autre onglet — la
   seule chose qu'un attaquant pourrait manipuler sur `/callback`, qui est
   appele par Google lui-meme, jamais par la cle d'ARENA.
3. **Le jeton obtenu est ecrit cote serveur, jamais renvoye au navigateur,
   et survit a un redemarrage.** `os.environ` pour un effet immediat ;
   `.env` quand ce fichier existe (poste local) ; la meme base SQLite que
   la memoire personnelle sinon (`core/connectors/stockage_jetons.py`) —
   deja prouvee persistante sur un hebergement comme Railway (DEC-0021),
   la ou aucun fichier `.env` n'existe sur le disque. Trouve le
   31/08/2026 : sans cette troisieme voie, un redeploiement perdait le
   jeton qui n'avait jamais vecu qu'en memoire, forcant a reconnecter
   Gmail a chaque mise a jour du code.

Les dependances d'authentification/debit sont declarees a cote de chaque
route (`dependencies=[Depends(...)]`), jamais appelees a la main dans le
corps : c'est ce que `tests/test_surface_api.py` fige et audite pour tout le
reste de l'API — ce fichier suit la meme regle plutot que d'en inventer une
seconde, invisible pour ce test.
"""
import json
import logging
import os
import secrets
import time
from typing import Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from apps.backend.config import BASE_DIR, DB_PATH
from apps.backend.runtime import registre
from apps.backend.security import limiter_debit, verify_api_key, verify_media_access
from core.connectors import stockage_jetons
from core.connectors.base import EtatSante
from core.connectors.fiche_google import PORTEE_FICHE
from core.connectors.google_oauth import (
    PORTEE_GMAIL_ENVOI,
    PORTEE_GMAIL_LECTURE,
    code_pour_jetons,
    identifiants,
    url_consentement,
)
from social.tiktok import oauth as oauth_tiktok

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
    # La fiche Google (DEC-0184) : le MEME jeton que le courrier. Le
    # consentement demande `include_granted_scopes` (google_oauth.py) : le
    # nouveau jeton garde les portees deja accordees, le courrier continue.
    "fiche_google": {
        "portees": [PORTEE_FICHE],
        "variable_env": "GOOGLE_REFRESH_TOKEN",
    },
    # TikTok (DEC-0186) : Login Kit pour le web. TikTok ne donne un jeton de
    # renouvellement qu'au bout de ce consentement — aucun generateur.
    "tiktok": {
        "famille": "tiktok",
        "portees": oauth_tiktok.PORTEES_TIKTOK,
        "variable_env": "TIKTOK_REFRESH_TOKEN",
    },
}


# --- Les gestes propres a chaque famille ----------------------------------------
# Resolus a l'appel, jamais figes a l'import : un test remplace `identifiants`
# ou `code_pour_jetons` de ce module, et le flux Google doit le voir.

def _famille(config: Dict[str, object]) -> str:
    return str(config.get("famille") or "google")


def _nom_fournisseur(config: Dict[str, object]) -> str:
    return "TikTok" if _famille(config) == "tiktok" else "Google"


def _identifiants_de(config: Dict[str, object]) -> Tuple[str, str]:
    if _famille(config) == "tiktok":
        return oauth_tiktok.identifiants()
    client_id, client_secret, _ = identifiants()
    return client_id, client_secret


def _ce_qui_manque(config: Dict[str, object], fournisseur: str) -> str:
    if _famille(config) == "tiktok":
        return ("TIKTOK_CLIENT_KEY et TIKTOK_CLIENT_SECRET absents de .env : cree "
                "l'application sur developers.tiktok.com (Login Kit + Content Posting "
                f"API, URI de redirection {_redirect_uri(fournisseur)}) avant de connecter.")
    return ("GOOGLE_CLIENT_ID et GOOGLE_CLIENT_SECRET absents de .env : "
            "cree l'app OAuth sur console.cloud.google.com (ecran de "
            "consentement + identifiant « application web », URI de "
            f"redirection {_redirect_uri(fournisseur)}) avant de connecter.")


def _url_de(config: Dict[str, object], client_id: str, redirect: str, state: str) -> str:
    if _famille(config) == "tiktok":
        return oauth_tiktok.url_consentement(client_id, redirect, state, config["portees"])
    return url_consentement(client_id, redirect, state, config["portees"])


def _echanger_de(config: Dict[str, object], client_id: str, client_secret: str,
                 code: str, redirect: str) -> Dict[str, object]:
    if _famille(config) == "tiktok":
        return oauth_tiktok.code_pour_jetons(client_id, client_secret, code, redirect)
    return code_pour_jetons(client_id, client_secret, code, redirect)


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
    """Le processus, la base persistante et `.env` : voir
    `stockage_jetons.persister`, partage depuis DEC-0185 avec TikTok."""
    stockage_jetons.persister(str(DB_PATH), BASE_DIR / ".env", variable, valeur)


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

@router.get("/{fournisseur}/auth",
           dependencies=[Depends(verify_media_access), Depends(limiter_debit)])
async def demarrer_oauth(fournisseur: str):
    """Redirige vers l'ecran de consentement du fournisseur. Rien n'est stocke ici."""
    config = FOURNISSEURS_OAUTH.get(fournisseur)
    if config is None:
        raise HTTPException(
            status_code=404,
            detail=(f"« {fournisseur} » n'a pas de flux OAuth cable. Cables "
                    f"aujourd'hui : {', '.join(sorted(FOURNISSEURS_OAUTH)) or 'aucun'}."),
        )

    client_id, client_secret = _identifiants_de(config)
    if not (client_id and client_secret):
        raise HTTPException(status_code=409, detail=_ce_qui_manque(config, fournisseur))

    _purger_etats_expires()
    state = secrets.token_urlsafe(32)
    _ETATS_EN_ATTENTE[state] = (fournisseur, time.monotonic() + DUREE_STATE_SECONDES)

    url = _url_de(config, client_id, _redirect_uri(fournisseur), state)
    return RedirectResponse(url, status_code=302)


# --- CALLBACK -> TOKEN STORAGE --------------------------------------------------

@router.get("/{fournisseur}/callback")
async def recevoir_callback(
    fournisseur: str,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
) -> HTMLResponse:
    """Le fournisseur revient ici avec `code`+`state`, ou `error` si le
    proprietaire refuse."""
    config = FOURNISSEURS_OAUTH.get(fournisseur)
    nom = _nom_fournisseur(config) if config else fournisseur
    if error:
        return _page_erreur(f"{nom} a refuse : {error}")

    if config is None:
        return _page_erreur(f"« {fournisseur} » n'a pas de flux OAuth cable.")

    if not code or not state:
        return _page_erreur(f"Reponse incomplete de {nom} : rien a echanger.")

    _purger_etats_expires()
    entree = _ETATS_EN_ATTENTE.pop(state, None)
    if entree is None or entree[0] != fournisseur:
        return _page_erreur(
            "Lien de consentement expire ou deja utilise. Relance la "
            "connexion depuis ARENA.")

    client_id, client_secret = _identifiants_de(config)
    if not (client_id and client_secret):
        return _page_erreur(f"Identifiants {nom} absents : impossible d'echanger le code.")

    try:
        jetons = _echanger_de(config, client_id, client_secret, code, _redirect_uri(fournisseur))
    except Exception as erreur:  # noqa: BLE001 — un refus du fournisseur se rapporte, ne remonte pas
        logger.info("Echange du code OAuth %s refuse : %s", fournisseur, type(erreur).__name__)
        return _page_erreur(f"{nom} a refuse l'echange du code.")

    refresh = jetons.get("refresh_token") if isinstance(jetons, dict) else None
    if not refresh:
        # `prompt=consent&access_type=offline` (deja force a l'etape /auth)
        # garantit normalement un refresh_token — ceci ne devrait arriver que
        # si Google change son comportement.
        if _famille(config) == "tiktok":
            return _page_erreur("TikTok n'a pas renvoye de jeton de renouvellement : relance la connexion.")
        return _page_erreur(
            "Google n'a pas renvoye de jeton de rafraichissement. Revoque "
            "l'acces sur myaccount.google.com/permissions puis reessaie.")

    _persister_refresh_token(config["variable_env"], str(refresh))

    # Une sonde recente (la PWA interroge /status pendant qu'elle attend le
    # popup) resterait en cache jusqu'a 60 s et rendrait encore NON_CONFIGURE
    # ici, juste apres une connexion pourtant reussie — purement cosmetique
    # (la page dirait "compte connecte" plutot que la vraie adresse), corrige
    # quand meme. `/status` (etat_connecteur, plus bas) garde le cache tel
    # quel : forcer une sonde fraiche a chaque appel viderait tout l'interet
    # du cache pour la seule route qui est vraiment interrogee en boucle.
    connecteur = registre.obtenir(fournisseur)
    if connecteur is not None and hasattr(connecteur, "invalider_sonde"):
        connecteur.invalider_sonde()

    sante = registre.sante(fournisseur)
    compte = sante.message if sante.etat == EtatSante.OPERATIONNEL else "compte connecte"
    return _page_succes(fournisseur, compte)


# --- STATUT & DECONNEXION -------------------------------------------------------

@router.get("/{fournisseur}/status",
           dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def etat_connecteur(fournisseur: str) -> Dict[str, object]:
    """Interroge (via `sonder()`, deja mis en cache 60 s cote connecteur) sans
    jamais rien affirmer de plausible : `connected` vient d'un vrai appel API."""
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


@router.post("/{fournisseur}/disconnect",
            dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def deconnecter(fournisseur: str) -> Dict[str, bool]:
    """Efface uniquement le jeton de rafraichissement — jamais l'identifiant OAuth
    (client_id/secret), qui reste utile pour se reconnecter ensuite."""
    config = FOURNISSEURS_OAUTH.get(fournisseur)
    if config is None:
        raise HTTPException(
            status_code=404, detail=f"« {fournisseur} » n'a pas de flux OAuth cable.")

    _persister_refresh_token(config["variable_env"], "")
    return {"connected": False}
