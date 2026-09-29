"""Connecteur LinkedIn — publier sur le profil du proprietaire.

Demande du 29/09/2026 (DEC-0183) : troisieme connecteur du plan, apres Meta
(DEC-0179) et Netlify (DEC-0180).

**Ce que LinkedIn permet a une application ordinaire, et donc ce qu'il fait** :

- dire a qui appartient le jeton (produit « Sign In with LinkedIn using
  OpenID Connect », `/v2/userinfo`) ;
- **publier** un post texte, avec un lien s'il y en a un, sur le profil du
  proprietaire (produit « Share on LinkedIn », autorisation
  `w_member_social`) — confirmation et coupe-circuit PUBLISH.

**Ce qu'il ne fait pas, et pourquoi** : lire ses posts, leurs statistiques ou
leurs commentaires, et publier au nom d'une page entreprise, demandent des
autorisations (`r_member_social`, API « Community Management ») que LinkedIn
n'accorde qu'apres examen de l'application. Aucune de ces capacites n'est
declaree : elles ne seraient qu'un refus deguise.

**Le jeton ne sort jamais** : il voyage dans l'en-tete, jamais dans un
message, un journal ou une erreur.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

logger = logging.getLogger("usman.social.linkedin")

VARIABLE_JETON = "LINKEDIN_ACCESS_TOKEN"
VARIABLE_VERSION = "LINKEDIN_API_VERSION"
#: Reglable : LinkedIn date ses versions (AAAAMM) et retire les anciennes
#: environ un an apres leur sortie.
VERSION_PAR_DEFAUT = "202509"
BASE = "https://api.linkedin.com"

CE_QUI_MANQUE = (
    "un jeton d'acces LinkedIn (LINKEDIN_ACCESS_TOKEN) portant les autorisations "
    "openid, profile et w_member_social. Marche a suivre : docs/CONNECTER_MES_COMPTES.md"
)

DELAI_SECONDES = 20.0
DUREE_SONDE_SECONDES = 60.0
#: La limite de LinkedIn pour le texte d'un post.
CARACTERES_MAX = 3000


class LinkedInConnector(Connecteur):
    """Le profil LinkedIn du proprietaire. Sans jeton, il ne tente rien."""

    service = "social"
    nom = "linkedin"

    def __init__(self, transport: Optional[httpx.BaseTransport] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # `transport` : pour les tests (httpx.MockTransport). Jamais d'appel
        # reseau reel depuis la suite.
        self._transport = transport
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a = 0.0
        self._membre: Optional[Dict[str, Any]] = None

    # --- Configuration -------------------------------------------------------------

    @staticmethod
    def _jeton() -> str:
        return os.getenv(VARIABLE_JETON, "").strip()

    @staticmethod
    def _version() -> str:
        return os.getenv(VARIABLE_VERSION, "").strip() or VERSION_PAR_DEFAUT

    def _sans_jeton(self, texte: str) -> str:
        """Retire le jeton d'un texte avant qu'il ne devienne un message."""
        jeton = self._jeton()
        return texte.replace(jeton, "***") if jeton else texte

    # --- Capacites -----------------------------------------------------------------

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "profil": Capacite(
                nom="profil", action="read",
                description="Le nom du compte LinkedIn auquel JARVIS est relie.",
                quota_par_minute=30),
            "publier": Capacite(
                nom="publier", action="publish",
                description="Publie un post sur le profil LinkedIn.",
                ecriture=True, quota_par_minute=2),
        }

    def resultat_attendu(self, capacite: Capacite, **parametres: Any) -> str:
        """Ce qui partira, en clair, avant la confirmation."""
        if capacite.nom == "publier":
            texte = str(parametres.get("message") or "")[:200]
            lien = f" avec le lien {parametres['lien']}" if parametres.get("lien") else ""
            return f"Un post public sur ton profil LinkedIn{lien} : « {texte} »"
        return capacite.description

    # --- Sante ---------------------------------------------------------------------

    def authentifier(self) -> bool:
        return self.sonder().etat == EtatSante.OPERATIONNEL

    def sonder(self) -> Sante:
        if not self._jeton():
            return Sante(etat=EtatSante.NON_CONFIGURE,
                         message="LinkedIn n'est pas connecte.",
                         ce_qui_manque=CE_QUI_MANQUE)
        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante
        # Une sonde MESURE : elle ne reprend pas un membre connu d'avant.
        membre = self._qui(frais=True)
        if isinstance(membre, str):
            sante = Sante(etat=EtatSante.EN_PANNE, message=membre, mesure_le=_maintenant())
        else:
            sante = Sante(etat=EtatSante.OPERATIONNEL,
                          message=f"Compte LinkedIn de {membre.get('name') or '?'} joignable.",
                          mesure_le=_maintenant())
        self._sante, self._sante_mesuree_a = sante, maintenant
        return sante

    # --- HTTP ----------------------------------------------------------------------

    def _appel(self, methode: str, chemin: str,
               corps: Optional[Dict[str, Any]] = None) -> httpx.Response | str:
        """Un appel a l'API LinkedIn : la reponse, ou la raison de l'echec (str)."""
        entetes = {
            "Authorization": f"Bearer {self._jeton()}",
            "LinkedIn-Version": self._version(),
            "X-Restli-Protocol-Version": "2.0.0",
        }
        try:
            with httpx.Client(timeout=DELAI_SECONDES, trust_env=False,
                              transport=self._transport) as client:
                reponse = client.request(methode, f"{BASE}{chemin}", json=corps, headers=entetes)
        except httpx.HTTPError as erreur:
            return self._sans_jeton(f"LinkedIn injoignable : {type(erreur).__name__}")
        if reponse.status_code >= 300:
            try:
                detail = reponse.json().get("message")
            except (ValueError, AttributeError):
                detail = None
            return self._sans_jeton(
                f"LinkedIn a refuse ({reponse.status_code}) : {detail or reponse.text[:200]}")
        return reponse

    def _qui(self, frais: bool = False) -> Dict[str, Any] | str:
        """Le membre a qui appartient le jeton (`sub` est son identifiant)."""
        if self._membre is not None and not frais:
            return self._membre
        reponse = self._appel("GET", "/v2/userinfo")
        if isinstance(reponse, str):
            return reponse
        try:
            membre = reponse.json()
        except ValueError:
            return "LinkedIn a rendu un profil illisible."
        if not isinstance(membre, dict) or not membre.get("sub"):
            return "LinkedIn n'a pas dit a qui appartient le jeton (autorisation openid manquante ?)."
        self._membre = membre
        return membre

    # --- Execution -----------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        if capacite.nom == "profil":
            return self._profil(capacite)
        return self._publier(capacite, **parametres)

    def _profil(self, capacite: Capacite) -> ResultatAction:
        membre = self._qui()
        if isinstance(membre, str):
            return echec(capacite.nom, self.nom, membre)
        return succes(capacite.nom, self.nom, f"Compte LinkedIn : {membre.get('name') or '?'}.",
                      preuve="linkedin:GET:/v2/userinfo",
                      donnees={"nom": membre.get("name"), "sub": membre.get("sub")},
                      mesure_le=_maintenant())

    def _publier(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        texte = str(parametres.get("message") or "").strip()
        if not texte:
            return echec(capacite.nom, self.nom, "Aucun texte a publier.")
        if len(texte) > CARACTERES_MAX:
            return echec(capacite.nom, self.nom,
                         f"Le post fait {len(texte)} caracteres ; LinkedIn en accepte {CARACTERES_MAX}.")
        membre = self._qui()
        if isinstance(membre, str):
            return echec(capacite.nom, self.nom, membre)
        corps: Dict[str, Any] = {
            "author": f"urn:li:person:{membre['sub']}",
            "commentary": texte,
            "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [],
                             "thirdPartyDistributionChannels": []},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        lien = str(parametres.get("lien") or "").strip()
        if lien:
            if not lien.startswith("https://"):
                return echec(capacite.nom, self.nom, "Le lien doit commencer par https://.")
            corps["content"] = {"article": {"source": lien,
                                            "title": str(parametres.get("titre_lien") or lien)[:200]}}
        reponse = self._appel("POST", "/rest/posts", corps)
        if isinstance(reponse, str):
            return echec(capacite.nom, self.nom, reponse)
        # LinkedIn rend l'identifiant du post dans un en-tete, pas dans le corps.
        identifiant = reponse.headers.get("x-restli-id", "").strip()
        if not identifiant:
            return echec(capacite.nom, self.nom,
                         "LinkedIn n'a rendu aucun identifiant : rien ne prouve la publication.")
        return succes(capacite.nom, self.nom, "Post publie sur LinkedIn.",
                      preuve=f"linkedin:{identifiant}", publication_id=identifiant)
