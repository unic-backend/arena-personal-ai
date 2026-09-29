"""Connecteur Fiche Google — la fiche d'etablissement du proprietaire (Maps).

Demande du 29/09/2026 (DEC-0184) : dernier compte du plan. Le proprietaire a
choisi « ma fiche entreprise ». Meme identifiant Google que le courrier et
l'agenda (`core/connectors/google_oauth.py`), avec une portee de plus :
`business.manage`.

Ce qu'il fait, par les API Business Profile et rien d'autre :

- **Lire** (autorise) : la fiche (nom, adresse, site) ; les avis, avec la
  note moyenne et le nombre total que Google calcule — jamais recalcules ici.
- **Repondre** a un avis (confirmation, coupe-circuit SEND_MESSAGES).

Il ne modifie pas la fiche (horaires, adresse, photos) et ne supprime rien.

**Google n'ouvre ces API qu'apres examen du projet** : tant que la demande
d'acces n'est pas acceptee, Google repond par un refus (quota a zero), et la
sante le rapporte tel quel. Ce n'est pas une panne du connecteur.

Un avis est ecrit par n'importe qui : son texte pret pour une invite voyage
enveloppe `EXTERNAL`, auteur compris.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

import httpx

from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from core.connectors.google_oauth import JetonGoogle, manquantes
from core.security.trust import TrustLevel, wrap

logger = logging.getLogger("usman.connecteurs.fiche_google")

#: La portee que la connexion Google doit accorder en plus du courrier.
PORTEE_FICHE = "https://www.googleapis.com/auth/business.manage"

URL_COMPTES = "https://mybusinessaccountmanagement.googleapis.com/v1"
URL_FICHES = "https://mybusinessbusinessinformation.googleapis.com/v1"
#: Les avis vivent encore dans l'API v4.
URL_AVIS = "https://mybusiness.googleapis.com/v4"

VARIABLE_COMPTE = "GOOGLE_BUSINESS_ACCOUNT"
VARIABLE_FICHE = "GOOGLE_BUSINESS_LOCATION"

CE_QUI_MANQUE = (
    "la connexion Google (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, "
    "GOOGLE_REFRESH_TOKEN) avec la portee business.manage, et l'acces aux API "
    "Business Profile accorde par Google. Marche a suivre : docs/CONNECTER_MES_COMPTES.md"
)

DELAI_SECONDES = 20.0
DUREE_SONDE_SECONDES = 60.0
AVIS_MAX = 50
REPONSE_MAX = 4096

#: L'API rend la note en toutes lettres.
ETOILES = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}


def texte_des_avis(fiche: str, avis: List[Dict[str, Any]]) -> str:
    """Les avis, auteur compris, dans une enveloppe `EXTERNAL`."""
    lignes = [f"{a.get('auteur') or 'anonyme'} ({a.get('etoiles') or '?'}/5) : "
              f"{a.get('commentaire') or '(sans commentaire)'}" for a in avis]
    return wrap("\n".join(lignes) or "(aucun avis)", TrustLevel.EXTERNAL,
                f"avis google {fiche}").text


def _avis_lisible(brut: Dict[str, Any]) -> Dict[str, Any]:
    reponse = brut.get("reviewReply") or {}
    return {
        "id": brut.get("reviewId"),
        "auteur": (brut.get("reviewer") or {}).get("displayName"),
        "etoiles": ETOILES.get(str(brut.get("starRating") or "")),
        "commentaire": brut.get("comment"),
        "date": brut.get("createTime"),
        "reponse": reponse.get("comment"),
    }


class FicheGoogleConnector(Connecteur):
    """La fiche Google du proprietaire. Sans connexion Google, il ne tente rien."""

    service = "business_profile"
    nom = "fiche_google"

    def __init__(self, transport: Optional[httpx.BaseTransport] = None,
                 appel_jeton: Optional[Callable[..., Dict[str, Any]]] = None,
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # `transport` et `appel_jeton` : pour les tests. Jamais d'appel reseau
        # reel depuis la suite.
        self._transport = transport
        self._jetons = JetonGoogle(echange=appel_jeton)
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a = 0.0

    # --- Capacites -----------------------------------------------------------------

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "fiche": Capacite(
                nom="fiche", action="read",
                description="Le nom, l'adresse et le site de la fiche Google.",
                quota_par_minute=30),
            "avis": Capacite(
                nom="avis", action="read",
                description="Les avis Google, avec la note moyenne et leur nombre.",
                quota_par_minute=30),
            "repondre_avis": Capacite(
                nom="repondre_avis", action="reply",
                description="Repond publiquement a un avis Google.",
                ecriture=True, quota_par_minute=10),
        }

    def resultat_attendu(self, capacite: Capacite, **parametres: Any) -> str:
        if capacite.nom == "repondre_avis":
            texte = str(parametres.get("message") or "")[:200]
            return (f"Une reponse PUBLIQUE a l'avis {parametres.get('avis_id', '?')} "
                    f"sur ta fiche Google : « {texte} »")
        return capacite.description

    # --- Sante ---------------------------------------------------------------------

    def authentifier(self) -> bool:
        return self.sonder().etat == EtatSante.OPERATIONNEL

    def sonder(self) -> Sante:
        if manquantes():
            return Sante(etat=EtatSante.NON_CONFIGURE,
                         message="La fiche Google n'est pas connectee.",
                         ce_qui_manque=CE_QUI_MANQUE)
        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante
        reponse = self._appel("GET", f"{URL_COMPTES}/accounts")
        if isinstance(reponse, str):
            sante = Sante(etat=EtatSante.EN_PANNE, message=reponse, mesure_le=_maintenant())
        else:
            nombre = len(reponse.get("accounts") or [])
            sante = Sante(etat=EtatSante.OPERATIONNEL,
                          message=f"{nombre} compte(s) Business Profile joignable(s).",
                          mesure_le=_maintenant())
        self._sante, self._sante_mesuree_a = sante, maintenant
        return sante

    # --- HTTP ----------------------------------------------------------------------

    def _appel(self, methode: str, url: str, parametres: Optional[Dict[str, Any]] = None,
               corps: Optional[Dict[str, Any]] = None) -> Dict[str, Any] | str:
        """Un appel Google : le corps JSON, ou la raison de l'echec (str)."""
        jeton = self._jetons.obtenir()
        if jeton is None:
            return "Google a refuse les identifiants : aucun jeton obtenu."
        try:
            with httpx.Client(timeout=DELAI_SECONDES, trust_env=False,
                              transport=self._transport) as client:
                reponse = client.request(methode, url, params=parametres, json=corps,
                                         headers={"Authorization": f"Bearer {jeton}"})
        except httpx.HTTPError as erreur:
            return f"Google injoignable : {type(erreur).__name__}"
        try:
            charge = reponse.json()
        except ValueError:
            charge = {}
        if reponse.status_code >= 300:
            detail = ((charge or {}).get("error") or {}).get("message") if isinstance(charge, dict) else None
            texte = f"Google a refuse ({reponse.status_code}) : {detail or reponse.text[:200]}"
            return texte.replace(jeton, "***")
        return charge if isinstance(charge, dict) else {}

    # --- Ou est la fiche -----------------------------------------------------------

    def _compte(self) -> str:
        """`accounts/123` : celui de `.env`, ou le premier du compte Google."""
        configure = os.getenv(VARIABLE_COMPTE, "").strip()
        if configure:
            return configure
        reponse = self._appel("GET", f"{URL_COMPTES}/accounts")
        if isinstance(reponse, str):
            return ""
        comptes = reponse.get("accounts") or []
        return str(comptes[0].get("name") or "") if comptes else ""

    def _fiche(self, compte: str) -> str:
        """`locations/456` : celle de `.env`, ou la premiere du compte."""
        configure = os.getenv(VARIABLE_FICHE, "").strip()
        if configure:
            return configure
        reponse = self._appel("GET", f"{URL_FICHES}/{compte}/locations",
                              {"readMask": "name,title", "pageSize": 10})
        if isinstance(reponse, str):
            return ""
        fiches = reponse.get("locations") or []
        return str(fiches[0].get("name") or "") if fiches else ""

    # --- Execution -----------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        compte = self._compte()
        if not compte:
            return echec(capacite.nom, self.nom,
                         "Aucun compte Business Profile trouve pour cette connexion Google.")
        if capacite.nom == "fiche":
            return self._lire_fiches(capacite, compte)
        fiche = self._fiche(compte)
        if not fiche:
            return echec(capacite.nom, self.nom, "Aucune fiche d'etablissement sur ce compte.")
        if capacite.nom == "avis":
            return self._lire_avis(capacite, compte, fiche, parametres)
        return self._repondre(capacite, compte, fiche, parametres)

    def _lire_fiches(self, capacite: Capacite, compte: str) -> ResultatAction:
        reponse = self._appel("GET", f"{URL_FICHES}/{compte}/locations", {
            "readMask": "name,title,storefrontAddress,websiteUri,phoneNumbers", "pageSize": 10})
        if isinstance(reponse, str):
            return echec(capacite.nom, self.nom, reponse)
        fiches = [{
            "id": f.get("name"), "nom": f.get("title"), "site": f.get("websiteUri"),
            "adresse": ", ".join((f.get("storefrontAddress") or {}).get("addressLines") or []) or None,
            "ville": (f.get("storefrontAddress") or {}).get("locality"),
        } for f in reponse.get("locations") or []]
        return succes(capacite.nom, self.nom, f"{len(fiches)} fiche(s) lue(s).",
                      preuve=f"google:GET:{compte}/locations", donnees=fiches,
                      mesure_le=_maintenant())

    def _lire_avis(self, capacite: Capacite, compte: str, fiche: str,
                   parametres: Dict[str, Any]) -> ResultatAction:
        try:
            limite = max(1, min(AVIS_MAX, int(parametres.get("limite", 10))))
        except (TypeError, ValueError):
            limite = 10
        chemin = f"{compte}/{fiche}/reviews"
        reponse = self._appel("GET", f"{URL_AVIS}/{chemin}", {"pageSize": limite})
        if isinstance(reponse, str):
            return echec(capacite.nom, self.nom, reponse)
        avis = [_avis_lisible(a) for a in reponse.get("reviews") or [] if isinstance(a, dict)]
        # La moyenne et le total sont ceux que GOOGLE calcule sur tous les avis,
        # pas une moyenne des seuls avis lus ici.
        moyenne = reponse.get("averageRating")
        total = reponse.get("totalReviewCount")
        return succes(capacite.nom, self.nom,
                      f"{len(avis)} avis lu(s) ; note Google : {moyenne if moyenne is not None else '?'}/5 "
                      f"sur {total if total is not None else '?'} avis.",
                      preuve=f"google:GET:{chemin}", donnees=avis, moyenne=moyenne, total=total,
                      texte=texte_des_avis(fiche, avis), mesure_le=_maintenant())

    def _repondre(self, capacite: Capacite, compte: str, fiche: str,
                  parametres: Dict[str, Any]) -> ResultatAction:
        avis_id = str(parametres.get("avis_id") or "").strip()
        message = str(parametres.get("message") or "").strip()
        if not avis_id or not message:
            return echec(capacite.nom, self.nom, "Il faut l'avis (avis_id) et la reponse.")
        if "/" in avis_id:
            return echec(capacite.nom, self.nom, "Identifiant d'avis invalide.")
        if len(message) > REPONSE_MAX:
            return echec(capacite.nom, self.nom,
                         f"La reponse fait {len(message)} caracteres ; Google en accepte {REPONSE_MAX}.")
        chemin = f"{compte}/{fiche}/reviews/{avis_id}/reply"
        reponse = self._appel("PUT", f"{URL_AVIS}/{chemin}", corps={"comment": message})
        if isinstance(reponse, str):
            return echec(capacite.nom, self.nom, reponse)
        if not reponse.get("updateTime"):
            return echec(capacite.nom, self.nom,
                         "Google n'a pas confirme la reponse : rien ne prouve qu'elle est en ligne.")
        return succes(capacite.nom, self.nom, "Reponse publiee sous l'avis.",
                      preuve=f"google:reply:{avis_id}:{reponse['updateTime']}")
