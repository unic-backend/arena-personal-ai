"""Connecteur Meta — la page Facebook et le compte Instagram du proprietaire.

Demande du 29/09/2026 (DEC-0179) : JARVIS doit publier, analyser et repondre
sur ses reseaux, « pas un simple question-reponse ». Meta sert Facebook et
Instagram par la meme API (Graph API) et le meme jeton de page : un seul
connecteur pour les deux.

Ce qu'il fait, par l'API officielle et rien d'autre :

- **Lire** (autorise) : la page et le compte Instagram (nom, abonnes), leurs
  dernieres publications avec leurs chiffres publics (mentions J'aime,
  commentaires), et les commentaires d'une publication.
- **Publier** (confirmation, coupe-circuit PUBLISH) : un post sur la page
  Facebook ; une photo sur Instagram — a partir d'une ADRESSE publique de
  l'image, c'est ce que l'API Instagram exige.
- **Repondre** a un commentaire (confirmation, coupe-circuit SEND_MESSAGES).

Les regles de `core/connectors/base.py` s'appliquent : sans jeton, rien ne
part et la sante dit ce qui manque ; un succes porte l'identifiant que Meta a
rendu (la preuve) ; une publication n'est jamais annoncee faite sans lui.

**Le jeton ne sort jamais** : il voyage dans la requete, jamais dans un
message, un journal ou une erreur (`_sans_jeton`).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from core.security.trust import TrustLevel, wrap

logger = logging.getLogger("usman.social.meta")

VARIABLE_JETON = "META_PAGE_ACCESS_TOKEN"
VARIABLE_PAGE = "META_PAGE_ID"
VARIABLE_INSTAGRAM = "META_IG_USER_ID"
VARIABLE_VERSION = "META_GRAPH_VERSION"
#: Reglable : Meta retire ses versions environ deux ans apres leur sortie.
VERSION_PAR_DEFAUT = "v23.0"

CE_QUI_MANQUE = (
    "un jeton de page Meta (META_PAGE_ACCESS_TOKEN) et l'identifiant de la page "
    "(META_PAGE_ID) ; pour Instagram, l'identifiant du compte professionnel relie "
    "(META_IG_USER_ID). Marche a suivre : docs/CONNECTER_MES_COMPTES.md"
)

DELAI_SECONDES = 20.0
DUREE_SONDE_SECONDES = 60.0
PUBLICATIONS_MAX = 25


def texte_des_commentaires(publication: str, commentaires: Any) -> str:
    """Les commentaires, auteur compris, dans une enveloppe `EXTERNAL`.

    L'auteur entre DANS l'enveloppe : un nom d'utilisateur se choisit aussi
    librement qu'un commentaire.
    """
    lignes = []
    for commentaire in commentaires if isinstance(commentaires, list) else []:
        auteur = commentaire.get("username") or (commentaire.get("from") or {}).get("name") or "inconnu"
        texte = commentaire.get("text") or commentaire.get("message") or ""
        lignes.append(f"{auteur} : {texte}")
    contenu = "\n".join(lignes) or "(aucun commentaire)"
    return wrap(contenu, TrustLevel.EXTERNAL, f"commentaires meta {publication}").text


class MetaConnector(Connecteur):
    """Facebook + Instagram par la Graph API. Sans jeton, il ne tente rien."""

    service = "social"
    nom = "meta"

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

    @staticmethod
    def _page() -> str:
        return os.getenv(VARIABLE_PAGE, "").strip()

    @staticmethod
    def _instagram() -> str:
        return os.getenv(VARIABLE_INSTAGRAM, "").strip()

    @staticmethod
    def _base() -> str:
        version = os.getenv(VARIABLE_VERSION, "").strip() or VERSION_PAR_DEFAUT
        return f"https://graph.facebook.com/{version}"

    def _sans_jeton(self, texte: str) -> str:
        """Retire le jeton d'un texte avant qu'il ne devienne un message."""
        jeton = self._jeton()
        return texte.replace(jeton, "***") if jeton else texte

    # --- Capacites -----------------------------------------------------------------

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "page_infos": Capacite(
                nom="page_infos", action="read",
                description="Nom, abonnes et lien de la page Facebook.",
                quota_par_minute=30),
            "page_publications": Capacite(
                nom="page_publications", action="read",
                description="Les dernieres publications de la page Facebook.",
                quota_par_minute=30),
            "instagram_infos": Capacite(
                nom="instagram_infos", action="read",
                description="Nom, abonnes et nombre de publications du compte Instagram.",
                quota_par_minute=30),
            "instagram_publications": Capacite(
                nom="instagram_publications", action="read",
                description="Les dernieres publications Instagram, avec J'aime et commentaires.",
                quota_par_minute=30),
            "commentaires": Capacite(
                nom="commentaires", action="read",
                description="Les commentaires d'une publication Facebook ou Instagram.",
                quota_par_minute=30),
            "publier_facebook": Capacite(
                nom="publier_facebook", action="publish",
                description="Publie un post sur la page Facebook.",
                ecriture=True, quota_par_minute=2),
            "publier_instagram": Capacite(
                nom="publier_instagram", action="publish",
                description="Publie une photo sur Instagram avec sa legende.",
                ecriture=True, quota_par_minute=2),
            "repondre_commentaire": Capacite(
                nom="repondre_commentaire", action="reply",
                description="Repond a un commentaire Facebook ou Instagram.",
                ecriture=True, quota_par_minute=10),
        }

    def resultat_attendu(self, capacite: Capacite, **parametres: Any) -> str:
        """Ce qui partira, en clair, avant la confirmation."""
        texte = str(parametres.get("message") or parametres.get("legende") or "")[:200]
        if capacite.nom == "publier_facebook":
            return f"Un post sur la page Facebook : « {texte} »"
        if capacite.nom == "publier_instagram":
            return (f"Une photo sur Instagram ({parametres.get('image_url', '?')}) "
                    f"avec la legende : « {texte} »")
        if capacite.nom == "repondre_commentaire":
            return f"Une reponse au commentaire {parametres.get('commentaire_id', '?')} : « {texte} »"
        return capacite.description

    # --- Sante ---------------------------------------------------------------------

    def authentifier(self) -> bool:
        return self.sonder().etat == EtatSante.OPERATIONNEL

    def sonder(self) -> Sante:
        if not self._jeton() or not self._page():
            return Sante(etat=EtatSante.NON_CONFIGURE,
                         message="Facebook et Instagram ne sont pas connectes.",
                         ce_qui_manque=CE_QUI_MANQUE)
        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante
        reponse = self._get(f"/{self._page()}", {"fields": "id,name"})
        if isinstance(reponse, str):
            sante = Sante(etat=EtatSante.EN_PANNE, message=reponse, mesure_le=_maintenant())
        else:
            sante = Sante(etat=EtatSante.OPERATIONNEL,
                          message=f"Page « {reponse.get('name', '?')} » joignable.",
                          mesure_le=_maintenant())
        self._sante, self._sante_mesuree_a = sante, maintenant
        return sante

    # --- HTTP ----------------------------------------------------------------------

    def _appel(self, methode: str, chemin: str, donnees: Dict[str, Any]) -> Dict[str, Any] | str:
        """Un appel a la Graph API : le corps JSON, ou la raison de l'echec."""
        parametres = {**donnees, "access_token": self._jeton()}
        try:
            with httpx.Client(timeout=DELAI_SECONDES, trust_env=False,
                              transport=self._transport) as client:
                if methode == "GET":
                    reponse = client.get(f"{self._base()}{chemin}", params=parametres)
                else:
                    reponse = client.post(f"{self._base()}{chemin}", data=parametres)
        except httpx.HTTPError as erreur:
            return self._sans_jeton(f"Meta injoignable : {type(erreur).__name__}")
        try:
            corps = reponse.json()
        except ValueError:
            corps = {}
        if reponse.status_code != 200 or "error" in corps:
            detail = (corps.get("error") or {}).get("message") if isinstance(corps, dict) else None
            return self._sans_jeton(
                f"Meta a refuse ({reponse.status_code}) : {detail or reponse.text[:200]}")
        return corps

    def _get(self, chemin: str, donnees: Dict[str, Any]) -> Dict[str, Any] | str:
        return self._appel("GET", chemin, donnees)

    def _post(self, chemin: str, donnees: Dict[str, Any]) -> Dict[str, Any] | str:
        return self._appel("POST", chemin, donnees)

    # --- Execution -----------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        methode = getattr(self, f"_{capacite.nom}")
        return methode(capacite, **parametres)

    def _lecture(self, capacite: Capacite, chemin: str, champs: str,
                 message: str, **extra: Any) -> ResultatAction:
        reponse = self._get(chemin, {"fields": champs, **extra})
        if isinstance(reponse, str):
            return echec(capacite.nom, self.nom, reponse)
        return succes(capacite.nom, self.nom, message, preuve=f"meta:GET:{chemin}",
                      donnees=reponse.get("data", reponse), mesure_le=_maintenant())

    def _limite(self, parametres: Dict[str, Any]) -> int:
        try:
            return max(1, min(PUBLICATIONS_MAX, int(parametres.get("limite", 10))))
        except (TypeError, ValueError):
            return 10

    def _page_infos(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        return self._lecture(capacite, f"/{self._page()}",
                             "id,name,fan_count,followers_count,link",
                             "Informations de la page Facebook lues.")

    def _page_publications(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        return self._lecture(capacite, f"/{self._page()}/posts",
                             "id,message,created_time,permalink_url",
                             "Publications de la page Facebook lues.",
                             limit=self._limite(parametres))

    def _sans_instagram(self, capacite: Capacite) -> Optional[ResultatAction]:
        if self._instagram():
            return None
        return echec(capacite.nom, self.nom,
                     f"Instagram n'est pas relie : {VARIABLE_INSTAGRAM} manque "
                     "(docs/CONNECTER_MES_COMPTES.md).")

    def _instagram_infos(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        return self._sans_instagram(capacite) or self._lecture(
            capacite, f"/{self._instagram()}",
            "id,username,followers_count,follows_count,media_count",
            "Informations du compte Instagram lues.")

    def _instagram_publications(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        return self._sans_instagram(capacite) or self._lecture(
            capacite, f"/{self._instagram()}/media",
            "id,caption,media_type,permalink,timestamp,like_count,comments_count",
            "Publications Instagram lues.", limit=self._limite(parametres))

    def _commentaires(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        publication = str(parametres.get("publication_id") or "").strip()
        if not publication:
            return echec(capacite.nom, self.nom, "Quelle publication ? (publication_id manquant)")
        resultat = self._lecture(capacite, f"/{publication}/comments",
                                 "id,text,message,username,from,timestamp,created_time",
                                 "Commentaires lus.", limit=self._limite(parametres))
        if resultat.statut.value == "SUCCESS":
            # N'importe qui peut commenter : le texte pret pour une invite
            # voyage a part, ENVELOPPE comme une donnee etrangere (voir gmail).
            resultat.detail["texte"] = texte_des_commentaires(publication, resultat.detail["donnees"])
        return resultat

    def _publier_facebook(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        message = str(parametres.get("message") or "").strip()
        if not message:
            return echec(capacite.nom, self.nom, "Aucun texte a publier.")
        donnees: Dict[str, Any] = {"message": message}
        if parametres.get("lien"):
            donnees["link"] = str(parametres["lien"])
        reponse = self._post(f"/{self._page()}/feed", donnees)
        if isinstance(reponse, str):
            return echec(capacite.nom, self.nom, reponse)
        identifiant = str(reponse.get("id") or "")
        if not identifiant:
            return echec(capacite.nom, self.nom, "Meta n'a rendu aucun identifiant : rien ne prouve la publication.")
        return succes(capacite.nom, self.nom, "Post publie sur la page Facebook.",
                      preuve=f"facebook:{identifiant}", publication_id=identifiant)

    def _publier_instagram(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        manque = self._sans_instagram(capacite)
        if manque:
            return manque
        image = str(parametres.get("image_url") or "").strip()
        if not image.startswith("https://"):
            return echec(capacite.nom, self.nom,
                         "Instagram publie une image a partir d'une adresse publique https:// "
                         "(image_url) ; aucune n'a ete donnee.")
        legende = str(parametres.get("legende") or parametres.get("message") or "")
        # Deux temps, comme l'API l'impose : un conteneur, puis sa publication.
        conteneur = self._post(f"/{self._instagram()}/media",
                               {"image_url": image, "caption": legende})
        if isinstance(conteneur, str):
            return echec(capacite.nom, self.nom, conteneur)
        creation = str(conteneur.get("id") or "")
        if not creation:
            return echec(capacite.nom, self.nom, "Meta n'a pas cree le conteneur de la photo.")
        publie = self._post(f"/{self._instagram()}/media_publish", {"creation_id": creation})
        if isinstance(publie, str):
            return echec(capacite.nom, self.nom, f"Conteneur cree ({creation}) mais non publie : {publie}")
        identifiant = str(publie.get("id") or "")
        if not identifiant:
            return echec(capacite.nom, self.nom, "Meta n'a rendu aucun identifiant de publication.")
        return succes(capacite.nom, self.nom, "Photo publiee sur Instagram.",
                      preuve=f"instagram:{identifiant}", publication_id=identifiant)

    def _repondre_commentaire(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        commentaire = str(parametres.get("commentaire_id") or "").strip()
        message = str(parametres.get("message") or "").strip()
        if not commentaire or not message:
            return echec(capacite.nom, self.nom, "Il faut le commentaire (commentaire_id) et la reponse.")
        # Instagram repond par /replies, Facebook par /comments.
        chemin = (f"/{commentaire}/replies" if parametres.get("reseau") == "instagram"
                  else f"/{commentaire}/comments")
        reponse = self._post(chemin, {"message": message})
        if isinstance(reponse, str):
            return echec(capacite.nom, self.nom, reponse)
        identifiant = str(reponse.get("id") or "")
        if not identifiant:
            return echec(capacite.nom, self.nom, "Meta n'a rendu aucun identifiant de reponse.")
        return succes(capacite.nom, self.nom, "Reponse publiee.",
                      preuve=f"meta:{identifiant}", reponse_id=identifiant)
