"""Connecteur TikTok — l'API Content Posting, reelle (DEC-0185).

Historique : jusqu'au 2026-08-27 ce fichier rendait `status: "success"` pour
une publication qui n'avait pas eu lieu. Il a ensuite declare son absence de
configuration pendant un mois. Il parle maintenant a TikTok — et garde la
regle qui a corrige le premier defaut : **aucun succes sans la preuve que
TikTok a rendue** (`publish_id`, et l'envoi du fichier accepte).

Ce qu'il fait, par l'API officielle et rien d'autre :

- **Lire** (autorise) : le compte relie (nom, niveaux de confidentialite
  permis, duree maximale d'une video) ; l'etat d'une publication envoyee.
- **Publier** une video (confirmation, coupe-circuit PUBLISH), avec sa
  legende, au niveau de confidentialite de `TIKTOK_PRIVACY_LEVEL`
  (`SELF_ONLY` par defaut). **Une application que TikTok n'a pas encore
  auditee ne peut publier qu'en prive** : c'est une regle de TikTok.
- **Deposer un brouillon** dans sa boite TikTok (confirmation, coupe-circuit
  PUBLISH) : il finit la publication dans l'application, ou il peut la
  rendre publique meme sans audit.

**Le jeton** : un jeton d'acces TikTok expire apres 24 heures. Le connecteur
le renouvelle avec `TIKTOK_REFRESH_TOKEN` et l'identifiant de l'application ;
quand TikTok rend un nouveau jeton de renouvellement, il est confie a
`persister` (la base persistante, cablee par `runtime.py`). Aucun jeton ne
sort dans un message, un journal ou une erreur.
"""
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import httpx

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

logger = logging.getLogger("usman.social.tiktok")

# Ce qui manque, dit une seule fois, pour que le message, la sante et la
# documentation ne puissent pas diverger.
CE_QUI_MANQUE = (
    "une application TikTok for Developers avec le scope video.publish (et "
    "video.upload pour les brouillons), puis la connexion OAuth : "
    "TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET et TIKTOK_REFRESH_TOKEN, hors du "
    "code source. Marche a suivre : docs/CONNECTER_MES_COMPTES.md"
)

#: Un jeton d'acces donne a la main (24 h) : utile pour un premier essai.
VARIABLE_JETON = "TIKTOK_ACCESS_TOKEN"
VARIABLE_CLE = "TIKTOK_CLIENT_KEY"
VARIABLE_SECRET = "TIKTOK_CLIENT_SECRET"
VARIABLE_RENOUVELLEMENT = "TIKTOK_REFRESH_TOKEN"
VARIABLE_CONFIDENTIALITE = "TIKTOK_PRIVACY_LEVEL"
CONFIDENTIALITE_PAR_DEFAUT = "SELF_ONLY"

BASE = "https://open.tiktokapis.com/v2"
URL_JETON = f"{BASE}/oauth/token/"

# Plafond de publication. Declare d'avance : un quota decouvert le jour ou le
# compte est suspendu coute plus cher qu'un quota ecrit.
QUOTA_PUBLICATIONS_PAR_MINUTE = 2

DELAI_SECONDES = 60.0
DUREE_SONDE_SECONDES = 60.0
MARGE_SECONDES = 60.0
LEGENDE_MAX = 2200

#: Regles d'envoi de TikTok : une video de 64 Mo au plus part d'un seul
#: tenant ; au-dela, des morceaux de 10 Mo, le dernier absorbant le reste.
MORCEAU_UNIQUE_MAX = 64 * 1024 * 1024
TAILLE_MORCEAU = 10 * 1024 * 1024
TAILLE_MAX = 4 * 1024 * 1024 * 1024
TYPES_VIDEO = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}

Persister = Callable[[str, str], None]


def _persister_en_memoire(variable: str, valeur: str) -> None:
    """Par defaut : le processus courant seulement. `runtime.py` branche mieux."""
    os.environ[variable] = valeur


def decouper(taille: int) -> Dict[str, int]:
    """La facon d'envoyer un fichier de `taille` octets, selon les regles de TikTok."""
    if taille <= MORCEAU_UNIQUE_MAX:
        return {"video_size": taille, "chunk_size": taille, "total_chunk_count": 1}
    return {"video_size": taille, "chunk_size": TAILLE_MORCEAU,
            "total_chunk_count": taille // TAILLE_MORCEAU}


class TikTokConnector(Connecteur):
    """Connecteur TikTok. Sans jeton, il ne tente rien et le dit."""

    service = "social"
    nom = "tiktok"

    def __init__(self, transport: Optional[httpx.BaseTransport] = None,
                 persister: Optional[Persister] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # `transport` : pour les tests (httpx.MockTransport). Jamais d'appel
        # reseau reel depuis la suite.
        self._transport = transport
        self._persister = persister or _persister_en_memoire
        self._jeton: Optional[str] = None
        self._jeton_expire_a = 0.0
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a = 0.0

    # --- Capacites -----------------------------------------------------------------

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "compte": Capacite(
                nom="compte", action="read",
                description="Le compte TikTok relie et ce qu'il peut publier.",
                quota_par_minute=20),
            "publish_video": Capacite(
                nom="publish_video", action="publish",
                description="Publie une video sur TikTok avec sa legende.",
                ecriture=True, quota_par_minute=QUOTA_PUBLICATIONS_PAR_MINUTE),
            "envoyer_brouillon": Capacite(
                nom="envoyer_brouillon", action="publish",
                description="Depose une video dans ta boite TikTok, a publier depuis l'application.",
                ecriture=True, quota_par_minute=QUOTA_PUBLICATIONS_PAR_MINUTE),
            "statut_publication": Capacite(
                nom="statut_publication", action="read",
                description="Ou en est une video envoyee a TikTok.",
                quota_par_minute=30),
        }

    def resultat_attendu(self, capacite: Capacite, **parametres: Any) -> str:
        fichier = Path(str(parametres.get("fichier") or "?")).name
        if capacite.nom == "publish_video":
            legende = str(parametres.get("legende") or "")[:200]
            return (f"La video {fichier} publiee sur TikTok ({self._confidentialite()}) "
                    f"avec la legende : « {legende} »")
        if capacite.nom == "envoyer_brouillon":
            return f"La video {fichier} deposee dans ta boite TikTok, sans etre publiee."
        return capacite.description

    # --- Le jeton ------------------------------------------------------------------

    @staticmethod
    def _env(nom: str) -> str:
        return os.getenv(nom, "").strip()

    def _configure(self) -> bool:
        return bool(self._env(VARIABLE_JETON) or all(
            self._env(v) for v in (VARIABLE_CLE, VARIABLE_SECRET, VARIABLE_RENOUVELLEMENT)))

    def _secrets(self) -> tuple:
        return tuple(s for s in (self._jeton, self._env(VARIABLE_JETON), self._env(VARIABLE_SECRET),
                                 self._env(VARIABLE_RENOUVELLEMENT)) if s)

    def _sans_secret(self, texte: str) -> str:
        """Retire tout jeton ou secret d'un texte avant qu'il ne devienne un message."""
        for secret in self._secrets():
            texte = texte.replace(secret, "***")
        return texte

    def _jeton_acces(self) -> Optional[str]:
        """Un jeton valable, renouvele avant son expiration, ou None."""
        if self._jeton and time.monotonic() < self._jeton_expire_a:
            return self._jeton
        cle, secret, renouvellement = (self._env(VARIABLE_CLE), self._env(VARIABLE_SECRET),
                                       self._env(VARIABLE_RENOUVELLEMENT))
        if not (cle and secret and renouvellement):
            return self._env(VARIABLE_JETON) or None
        try:
            with httpx.Client(timeout=DELAI_SECONDES, trust_env=False,
                              transport=self._transport) as client:
                reponse = client.post(URL_JETON, data={
                    "client_key": cle, "client_secret": secret,
                    "grant_type": "refresh_token", "refresh_token": renouvellement})
            charge = reponse.json()
        except (httpx.HTTPError, ValueError) as erreur:
            logger.info("Renouvellement du jeton TikTok impossible : %s", type(erreur).__name__)
            return None
        jeton = charge.get("access_token") if isinstance(charge, dict) else None
        if not jeton:
            logger.info("TikTok a refuse le renouvellement : %s",
                        self._sans_secret(str(charge.get("error") if isinstance(charge, dict) else "")))
            return None
        nouveau = str(charge.get("refresh_token") or "")
        if nouveau and nouveau != renouvellement:
            # TikTok peut changer le jeton de renouvellement : l'ancien ne
            # servira bientot plus. Le perdre forcerait a tout reconnecter.
            self._persister(VARIABLE_RENOUVELLEMENT, nouveau)
        duree = charge.get("expires_in")
        duree = float(duree) if isinstance(duree, (int, float)) else 3600.0
        self._jeton = str(jeton)
        self._jeton_expire_a = time.monotonic() + max(0.0, duree - MARGE_SECONDES)
        return self._jeton

    # --- Sante ---------------------------------------------------------------------

    def invalider_sonde(self) -> None:
        """Juste apres une connexion : oublier la mesure et le jeton d'avant."""
        self._sante, self._jeton = None, None
        self._sante_mesuree_a = self._jeton_expire_a = 0.0

    def authentifier(self) -> bool:
        return self.sonder().etat == EtatSante.OPERATIONNEL

    def sonder(self) -> Sante:
        """Mesure : TikTok reconnait-il le compte ? Rien n'est suppose."""
        if not self._configure():
            return Sante(etat=EtatSante.NON_CONFIGURE,
                         message="TikTok n'est pas connecte : aucun jeton d'acces.",
                         ce_qui_manque=CE_QUI_MANQUE)
        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante
        compte = self._appel_json("/post/publish/creator_info/query/", {})
        if isinstance(compte, str):
            sante = Sante(etat=EtatSante.EN_PANNE, message=compte, mesure_le=_maintenant())
        else:
            sante = Sante(etat=EtatSante.OPERATIONNEL,
                          message=f"Compte TikTok @{compte.get('creator_username') or '?'} joignable.",
                          mesure_le=_maintenant())
        self._sante, self._sante_mesuree_a = sante, maintenant
        return sante

    # --- HTTP ----------------------------------------------------------------------

    def _appel_json(self, chemin: str, corps: Dict[str, Any]) -> Dict[str, Any] | str:
        """Un POST JSON a l'API : le champ `data`, ou la raison de l'echec (str)."""
        jeton = self._jeton_acces()
        if jeton is None:
            return "TikTok a refuse le jeton : aucun jeton d'acces valable obtenu."
        try:
            with httpx.Client(timeout=DELAI_SECONDES, trust_env=False,
                              transport=self._transport) as client:
                reponse = client.post(f"{BASE}{chemin}", json=corps, headers={
                    "Authorization": f"Bearer {jeton}",
                    "Content-Type": "application/json; charset=UTF-8"})
        except httpx.HTTPError as erreur:
            return f"TikTok injoignable : {type(erreur).__name__}"
        try:
            charge = reponse.json()
        except ValueError:
            charge = {}
        erreur = (charge.get("error") or {}) if isinstance(charge, dict) else {}
        code = str(erreur.get("code") or "")
        if reponse.status_code >= 300 or (code and code != "ok"):
            detail = erreur.get("message") or code or reponse.text[:200]
            return self._sans_secret(f"TikTok a refuse ({reponse.status_code}) : {detail}")
        return (charge.get("data") or {}) if isinstance(charge, dict) else {}

    def _envoyer_fichier(self, url: str, chemin: Path, decoupe: Dict[str, int]) -> Optional[str]:
        """Envoie le fichier morceau par morceau. None si tout est accepte, sinon la raison."""
        taille, morceau, nombre = (decoupe["video_size"], decoupe["chunk_size"],
                                   decoupe["total_chunk_count"])
        type_mime = TYPES_VIDEO[chemin.suffix.lower()]
        try:
            with open(chemin, "rb") as flux, httpx.Client(
                    timeout=DELAI_SECONDES * 5, trust_env=False, transport=self._transport) as client:
                for index in range(nombre):
                    debut = index * morceau
                    # Le dernier morceau emporte tout ce qui reste.
                    fin = taille - 1 if index == nombre - 1 else debut + morceau - 1
                    flux.seek(debut)
                    contenu = flux.read(fin - debut + 1)
                    reponse = client.put(url, content=contenu, headers={
                        "Content-Type": type_mime, "Content-Length": str(len(contenu)),
                        "Content-Range": f"bytes {debut}-{fin}/{taille}"})
                    if reponse.status_code not in (200, 201, 206):
                        return f"TikTok a refuse le morceau {index + 1}/{nombre} ({reponse.status_code})."
        except (OSError, httpx.HTTPError) as erreur:
            return f"Envoi du fichier interrompu : {type(erreur).__name__}"
        return None

    # --- Execution -----------------------------------------------------------------

    def _confidentialite(self) -> str:
        return self._env(VARIABLE_CONFIDENTIALITE) or CONFIDENTIALITE_PAR_DEFAUT

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        if not self._configure():
            return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=CE_QUI_MANQUE)
        if capacite.nom == "compte":
            return self._compte(capacite)
        if capacite.nom == "statut_publication":
            return self._statut(capacite, parametres)
        return self._envoyer(capacite, parametres)

    def _compte(self, capacite: Capacite) -> ResultatAction:
        compte = self._appel_json("/post/publish/creator_info/query/", {})
        if isinstance(compte, str):
            return echec(capacite.nom, self.nom, compte)
        donnees = {
            "nom": compte.get("creator_username"), "pseudo": compte.get("creator_nickname"),
            "confidentialites": compte.get("privacy_level_options") or [],
            "duree_max_secondes": compte.get("max_video_post_duration_sec"),
        }
        return succes(capacite.nom, self.nom, f"Compte TikTok @{donnees['nom'] or '?'}.",
                      preuve="tiktok:creator_info", donnees=donnees, mesure_le=_maintenant())

    def _statut(self, capacite: Capacite, parametres: Dict[str, Any]) -> ResultatAction:
        publication = str(parametres.get("publish_id") or "").strip()
        if not publication:
            return echec(capacite.nom, self.nom, "Quelle publication ? (publish_id manquant)")
        etat = self._appel_json("/post/publish/status/fetch/", {"publish_id": publication})
        if isinstance(etat, str):
            return echec(capacite.nom, self.nom, etat)
        statut = str(etat.get("status") or "?")
        message = {"PUBLISH_COMPLETE": "La video est publiee.",
                   "SEND_TO_USER_INBOX": "La video est dans ta boite TikTok, a publier depuis l'application.",
                   "FAILED": f"TikTok a rejete la video : {etat.get('fail_reason') or 'raison non donnee'}.",
                   }.get(statut, f"TikTok traite encore la video ({statut}).")
        return succes(capacite.nom, self.nom, message, preuve=f"tiktok:status:{publication}:{statut}",
                      statut=statut, mesure_le=_maintenant())

    def _envoyer(self, capacite: Capacite, parametres: Dict[str, Any]) -> ResultatAction:
        brut = str(parametres.get("fichier") or "").strip()
        chemin = Path(brut).expanduser()
        if not brut or not chemin.is_file():
            return echec(capacite.nom, self.nom, "Aucune video a envoyer : le fichier est introuvable.",
                         fichier=brut)
        if chemin.suffix.lower() not in TYPES_VIDEO:
            return echec(capacite.nom, self.nom,
                         f"TikTok accepte MP4, MOV ou WebM ; « {chemin.suffix or 'sans extension'} » non.")
        taille = chemin.stat().st_size
        if not 0 < taille <= TAILLE_MAX:
            return echec(capacite.nom, self.nom, "La video est vide ou depasse les 4 Go que TikTok accepte.")
        decoupe = decouper(taille)
        source = {"source": "FILE_UPLOAD", **decoupe}

        if capacite.nom == "publish_video":
            legende = str(parametres.get("legende") or "").strip()
            if len(legende) > LEGENDE_MAX:
                return echec(capacite.nom, self.nom,
                             f"La legende fait {len(legende)} caracteres ; TikTok en accepte {LEGENDE_MAX}.")
            niveau = self._confidentialite()
            compte = self._appel_json("/post/publish/creator_info/query/", {})
            if isinstance(compte, str):
                return echec(capacite.nom, self.nom, compte)
            permis = compte.get("privacy_level_options") or []
            if niveau not in permis:
                return echec(capacite.nom, self.nom,
                             f"TikTok n'autorise pas « {niveau} » pour ce compte ; permis : "
                             f"{', '.join(permis) or 'aucun'}.")
            debut = self._appel_json("/post/publish/video/init/", {
                "post_info": {"title": legende, "privacy_level": niveau},
                "source_info": source})
        else:
            niveau = ""
            debut = self._appel_json("/post/publish/inbox/video/init/", {"source_info": source})
        if isinstance(debut, str):
            return echec(capacite.nom, self.nom, debut)
        publication, url = str(debut.get("publish_id") or ""), str(debut.get("upload_url") or "")
        if not publication or not url:
            return echec(capacite.nom, self.nom,
                         "TikTok n'a rendu ni identifiant ni adresse d'envoi : rien n'est parti.")
        probleme = self._envoyer_fichier(url, chemin, decoupe)
        if probleme:
            return echec(capacite.nom, self.nom, probleme, publish_id=publication)
        # Envoyee n'est pas en ligne : TikTok traite encore la video.
        # « statut_publication » dira quand elle l'est, ou pourquoi elle a echoue.
        message = ("Video deposee dans ta boite TikTok : ouvre l'application pour la publier."
                   if capacite.nom == "envoyer_brouillon" else
                   f"Video envoyee a TikTok ({niveau}). TikTok la traite : elle n'est pas "
                   "encore en ligne.")
        return succes(capacite.nom, self.nom, message, preuve=f"tiktok:{publication}",
                      publish_id=publication, confidentialite=niveau or None)
