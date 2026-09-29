"""Connecteur Netlify — le site du proprietaire, tel que Netlify le sert.

Demande du 29/09/2026 (DEC-0180) : JARVIS doit « entrer dans » les sites web
du proprietaire, heberges chez Netlify. Deuxieme connecteur du plan, apres
Meta (DEC-0179).

Ce qu'il fait, par l'API officielle de Netlify et rien d'autre :

- **Inspecter** (autorise) : la liste des sites du compte, l'etat d'un site,
  ses derniers deploiements (reussis ou en echec, avec l'erreur de build), et
  les messages recus par ses formulaires — les demandes de devis des
  visiteurs.
- **Republier** (confirmation, coupe-circuit PUBLISH) : relancer la
  construction et la mise en ligne du site depuis son depot.

Il ne modifie ni les fichiers du site, ni ses reglages, ni son domaine, et il
ne supprime rien : aucune de ces capacites n'est declaree.

Un message de formulaire est ecrit par n'importe quel visiteur : son texte
pret pour une invite voyage enveloppe `EXTERNAL`, comme un e-mail.
**Le jeton ne sort jamais** : il voyage dans l'en-tete, jamais dans un
message, un journal ou une erreur.
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

import httpx

from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from core.security.trust import TrustLevel, wrap

logger = logging.getLogger("usman.connecteurs.netlify")

#: Les noms que la ligne de commande Netlify utilise deja.
VARIABLE_JETON = "NETLIFY_AUTH_TOKEN"
VARIABLE_SITE = "NETLIFY_SITE_ID"
BASE = "https://api.netlify.com/api/v1"

CE_QUI_MANQUE = (
    "un jeton d'acces personnel Netlify (NETLIFY_AUTH_TOKEN) ; pour un site "
    "precis, son identifiant (NETLIFY_SITE_ID). Marche a suivre : "
    "docs/CONNECTER_MES_COMPTES.md"
)

DELAI_SECONDES = 20.0
DUREE_SONDE_SECONDES = 60.0
ELEMENTS_MAX = 50
#: Un identifiant de site (uuid) ou son nom de domaine Netlify : jamais un
#: chemin. Sans ce filtre, « ../../user » atteindrait une autre ressource.
MOTIF_SITE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$")

CHAMPS_SITE = ("id", "name", "url", "ssl_url", "custom_domain", "admin_url",
               "state", "updated_at")
CHAMPS_DEPLOIEMENT = ("id", "state", "branch", "title", "error_message",
                      "created_at", "published_at", "deploy_ssl_url", "context")


def _garder(objet: Any, champs: tuple) -> Dict[str, Any]:
    """Seulement les champs utiles : un site Netlify en porte plus de cent."""
    return {c: objet.get(c) for c in champs} if isinstance(objet, dict) else {}


def texte_des_soumissions(site: str, soumissions: List[Dict[str, Any]]) -> str:
    """Les messages des visiteurs, expediteur compris, dans une enveloppe
    `EXTERNAL` : un nom se choisit aussi librement qu'un message."""
    blocs = []
    for soumission in soumissions:
        champs = soumission.get("data") or {}
        lignes = [f"Formulaire : {soumission.get('form_name') or '?'}",
                  f"Recu le : {soumission.get('created_at') or '?'}"]
        lignes += [f"{cle} : {valeur}" for cle, valeur in champs.items()
                   if cle not in ("ip", "user_agent", "referrer")]
        blocs.append("\n".join(lignes))
    contenu = "\n\n".join(blocs) or "(aucun message)"
    return wrap(contenu, TrustLevel.EXTERNAL, f"formulaires netlify {site}").text


class NetlifyConnector(Connecteur):
    """Les sites Netlify du proprietaire. Sans jeton, il ne tente rien."""

    service = "website"
    nom = "netlify"

    def __init__(self, transport: Optional[httpx.BaseTransport] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # `transport` : pour les tests (httpx.MockTransport). Jamais d'appel
        # reseau reel depuis la suite.
        self._transport = transport
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a = 0.0

    # --- Configuration -------------------------------------------------------------

    @staticmethod
    def _jeton() -> str:
        return os.getenv(VARIABLE_JETON, "").strip()

    def _sans_jeton(self, texte: str) -> str:
        """Retire le jeton d'un texte avant qu'il ne devienne un message."""
        jeton = self._jeton()
        return texte.replace(jeton, "***") if jeton else texte

    # --- Capacites -----------------------------------------------------------------

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "sites": Capacite(
                nom="sites", action="inspect",
                description="La liste des sites du compte Netlify, avec leur adresse.",
                quota_par_minute=30),
            "site_infos": Capacite(
                nom="site_infos", action="inspect",
                description="L'etat d'un site : adresse, domaine, derniere mise a jour.",
                quota_par_minute=30),
            "deploiements": Capacite(
                nom="deploiements", action="inspect",
                description="Les derniers deploiements du site, et l'erreur de ceux qui ont echoue.",
                quota_par_minute=30),
            "soumissions": Capacite(
                nom="soumissions", action="inspect",
                description="Les messages recus par les formulaires du site.",
                quota_par_minute=30),
            "redeployer": Capacite(
                nom="redeployer", action="publish",
                description="Relance la construction et la mise en ligne du site.",
                ecriture=True, quota_par_minute=2),
        }

    def resultat_attendu(self, capacite: Capacite, **parametres: Any) -> str:
        """Ce qui partira, en clair, avant la confirmation."""
        if capacite.nom == "redeployer":
            site = parametres.get("site_id") or os.getenv(VARIABLE_SITE, "") or "?"
            return (f"Le site {site} est reconstruit depuis son depot et remplace "
                    "la version en ligne s'il reussit.")
        return capacite.description

    # --- Sante ---------------------------------------------------------------------

    def authentifier(self) -> bool:
        return self.sonder().etat == EtatSante.OPERATIONNEL

    def sonder(self) -> Sante:
        if not self._jeton():
            return Sante(etat=EtatSante.NON_CONFIGURE,
                         message="Netlify n'est pas connecte.",
                         ce_qui_manque=CE_QUI_MANQUE)
        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante
        reponse = self._appel("GET", "/user")
        if isinstance(reponse, str):
            sante = Sante(etat=EtatSante.EN_PANNE, message=reponse, mesure_le=_maintenant())
        else:
            sante = Sante(etat=EtatSante.OPERATIONNEL, message="Compte Netlify joignable.",
                          mesure_le=_maintenant())
        self._sante, self._sante_mesuree_a = sante, maintenant
        return sante

    # --- HTTP ----------------------------------------------------------------------

    def _appel(self, methode: str, chemin: str,
               parametres: Optional[Dict[str, Any]] = None) -> Any:
        """Un appel a l'API Netlify : le corps JSON, ou la raison de l'echec (str)."""
        entetes = {"Authorization": f"Bearer {self._jeton()}"}
        try:
            with httpx.Client(timeout=DELAI_SECONDES, trust_env=False,
                              transport=self._transport) as client:
                reponse = client.request(methode, f"{BASE}{chemin}",
                                         params=parametres, headers=entetes)
        except httpx.HTTPError as erreur:
            return self._sans_jeton(f"Netlify injoignable : {type(erreur).__name__}")
        try:
            corps = reponse.json()
        except ValueError:
            corps = None
        if reponse.status_code >= 300:
            detail = corps.get("message") if isinstance(corps, dict) else None
            return self._sans_jeton(
                f"Netlify a refuse ({reponse.status_code}) : {detail or reponse.text[:200]}")
        return corps

    # --- Execution -----------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        if capacite.nom == "sites":
            return self._sites(capacite, **parametres)
        site = str(parametres.get("site_id") or os.getenv(VARIABLE_SITE, "")).strip()
        if not site:
            return echec(capacite.nom, self.nom,
                         f"Quel site ? {VARIABLE_SITE} manque — la capacite « sites » "
                         "liste ceux du compte (docs/CONNECTER_MES_COMPTES.md).")
        if not MOTIF_SITE.match(site):
            return echec(capacite.nom, self.nom, "Identifiant de site invalide.")
        methode = getattr(self, f"_{capacite.nom}")
        return methode(capacite, site, **parametres)

    def _limite(self, parametres: Dict[str, Any]) -> int:
        try:
            return max(1, min(ELEMENTS_MAX, int(parametres.get("limite", 10))))
        except (TypeError, ValueError):
            return 10

    def _sites(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        reponse = self._appel("GET", "/sites", {"filter": "all", "per_page": ELEMENTS_MAX})
        if isinstance(reponse, str):
            return echec(capacite.nom, self.nom, reponse)
        sites = [_garder(s, CHAMPS_SITE) for s in reponse or []]
        return succes(capacite.nom, self.nom, f"{len(sites)} site(s) sur le compte Netlify.",
                      preuve="netlify:GET:/sites", donnees=sites, mesure_le=_maintenant())

    def _site_infos(self, capacite: Capacite, site: str, **parametres: Any) -> ResultatAction:
        reponse = self._appel("GET", f"/sites/{site}")
        if isinstance(reponse, str):
            return echec(capacite.nom, self.nom, reponse)
        donnees = _garder(reponse, CHAMPS_SITE)
        publie = (reponse or {}).get("published_deploy") or {}
        donnees["derniere_publication"] = publie.get("published_at")
        return succes(capacite.nom, self.nom, f"Site « {donnees.get('name') or site} » lu.",
                      preuve=f"netlify:GET:/sites/{site}", donnees=donnees,
                      mesure_le=_maintenant())

    def _deploiements(self, capacite: Capacite, site: str, **parametres: Any) -> ResultatAction:
        reponse = self._appel("GET", f"/sites/{site}/deploys",
                              {"per_page": self._limite(parametres)})
        if isinstance(reponse, str):
            return echec(capacite.nom, self.nom, reponse)
        deploiements = [_garder(d, CHAMPS_DEPLOIEMENT) for d in reponse or []]
        en_echec = sum(1 for d in deploiements if d.get("state") == "error")
        return succes(capacite.nom, self.nom,
                      f"{len(deploiements)} deploiement(s) lu(s), dont {en_echec} en echec.",
                      preuve=f"netlify:GET:/sites/{site}/deploys", donnees=deploiements,
                      mesure_le=_maintenant())

    def _soumissions(self, capacite: Capacite, site: str, **parametres: Any) -> ResultatAction:
        reponse = self._appel("GET", f"/sites/{site}/submissions",
                              {"per_page": self._limite(parametres)})
        if isinstance(reponse, str):
            return echec(capacite.nom, self.nom, reponse)
        soumissions = [s for s in reponse or [] if isinstance(s, dict)]
        donnees = [{"id": s.get("id"), "form_name": s.get("form_name"),
                    "created_at": s.get("created_at"), "data": s.get("data") or {}}
                   for s in soumissions]
        return succes(capacite.nom, self.nom, f"{len(donnees)} message(s) de formulaire lu(s).",
                      preuve=f"netlify:GET:/sites/{site}/submissions", donnees=donnees,
                      # Ecrit par des visiteurs : le texte pour une invite voyage enveloppe.
                      texte=texte_des_soumissions(site, donnees), mesure_le=_maintenant())

    def _redeployer(self, capacite: Capacite, site: str, **parametres: Any) -> ResultatAction:
        reponse = self._appel("POST", f"/sites/{site}/builds")
        if isinstance(reponse, str):
            return echec(capacite.nom, self.nom, reponse)
        construction = str((reponse or {}).get("id") or "")
        if not construction:
            return echec(capacite.nom, self.nom,
                         "Netlify n'a rendu aucun identifiant : rien ne prouve que la construction a demarre.")
        # Demarree n'est pas en ligne : la construction peut encore echouer,
        # et la capacite « deploiements » le dira.
        return succes(capacite.nom, self.nom,
                      "Construction demarree. Elle n'est pas encore en ligne : "
                      "« deploiements » dira si elle a reussi.",
                      preuve=f"netlify:build:{construction}",
                      deploiement_id=(reponse or {}).get("deploy_id"))
