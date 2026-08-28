"""Connecteur MoneyPrinterTurbo — une video courte a partir d'un sujet.

MoneyPrinterTurbo (harry0703, dépôt public) fabrique une video verticale a
partir d'une phrase : il ecrit le script, va chercher les plans, pose la voix,
incruste les sous-titres et assemble. C'est un **service separe**, lance par le
proprietaire sur sa machine — ARENA lui parle par son API HTTP, exactement comme
il parle a WanGP. Aucune ligne de ce projet n'entre dans ce depot.

Le contrat n'est pas devine : il est lu dans le code du projet.
`app/controllers/v1/base.py` pose `router.prefix = "/api/v1"`,
`app/controllers/v1/video.py` declare `POST /videos` et `GET /tasks/{task_id}`,
`app/models/const.py` fixe les etats (-1 echec, 1 terminee, 4 en cours), et
`app/controllers/base.py` verifie le jeton dans l'en-tete `x-api-key`.

**Cinq regles :**

1. **Generer est une confirmation.** `action="generate"` : la politique la classe
   en CONFIRMATION. Une generation occupe la carte graphique plusieurs minutes.

2. **L'etat rendu est traduit, pas invente.** `etat_travail` rend la forme que
   `core/connectors/suivi_video.py` sait deja suivre. La progression vient du
   champ `progress` de MoneyPrinter ; absente, elle reste absente.

3. **Un succes exige un fichier.** Une tache annoncee terminee sans video n'est
   pas une reussite : elle est rapportee comme telle.

4. **Le jeton ne voyage jamais dans un resultat.** Il part dans l'en-tete, il
   n'entre dans aucun compte-rendu.

5. **Service eteint, `NOT_CONFIGURED` avec la commande de lancement.** Jamais
   une video promise qui n'arrivera pas.
"""
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

import httpx

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante

logger = logging.getLogger("usman.connecteurs.moneyprinter")

#: Ou joindre le service. `listen_port = 8080` dans son `config.example.toml`.
BASE_URL = os.getenv("MONEYPRINTER_URL", "http://127.0.0.1:8080/api/v1")

#: Son `[app] api_key`, s'il en a configure une. Vide = pas d'authentification.
JETON = os.getenv("MONEYPRINTER_API_KEY", "")

CE_QUI_MANQUE = (
    "MoneyPrinterTurbo lance sur la machine : "
    "python -m uvicorn app.asgi:app --host 127.0.0.1 --port 8080 "
    "(depuis son dossier, avec son config.toml rempli — au moins une cle Pexels "
    "et un llm_provider). L'adresse se change avec MONEYPRINTER_URL."
)

#: Les etats, lus dans `app/models/const.py` du projet.
TACHE_ECHOUEE = -1
TACHE_TERMINEE = 1
TACHE_EN_COURS = 4

#: Plafond que **nous** nous imposons : chaque generation occupe la carte
#: graphique plusieurs minutes. En empiler dix couterait une soiree.
GENERATIONS_PAR_MINUTE = 2

QUOTA_LECTURE_PAR_MINUTE = 60

DELAI_SECONDES = 30.0
DUREE_SONDE_SECONDES = 60.0

#: Le format vertical, celui des shorts. Ecrit ici plutot que laisse au defaut
#: du service : ce qu'ARENA demande doit etre lisible sans ouvrir leur code.
FORMAT_VERTICAL = "9:16"


def _entetes(jeton: str) -> Dict[str, str]:
    """L'en-tete d'authentification, vide quand aucun jeton n'est configure."""
    return {"x-api-key": jeton} if jeton else {}


def _get(chemin: str, parametres: Dict[str, Any], jeton: str) -> Dict[str, Any]:
    url = f"{BASE_URL.rstrip('/')}/{chemin.lstrip('/')}"
    with httpx.Client(timeout=DELAI_SECONDES) as client:
        reponse = client.get(url, params=parametres, headers=_entetes(jeton))
        reponse.raise_for_status()
        return reponse.json()


def _post(chemin: str, charge: Dict[str, Any], jeton: str) -> Dict[str, Any]:
    """Le seul chemin qui lance une generation."""
    url = f"{BASE_URL.rstrip('/')}/{chemin.lstrip('/')}"
    with httpx.Client(timeout=DELAI_SECONDES) as client:
        reponse = client.post(url, json=charge, headers=_entetes(jeton))
        reponse.raise_for_status()
        return reponse.json()


AppelHttp = Callable[[str, Dict[str, Any], str], Dict[str, Any]]


def _donnees(charge: Any) -> Dict[str, Any]:
    """Le corps utile de la reponse. Le service l'enveloppe dans `data`."""
    if not isinstance(charge, dict):
        return {}
    interne = charge.get("data")
    return interne if isinstance(interne, dict) else charge


def instantane_de(donnees: Dict[str, Any]) -> Dict[str, Any]:
    """Traduit l'etat MoneyPrinter dans la forme que le suivi sait deja lire.

    `core/connectors/suivi_video.py` a ete ecrit pour WanGP. Plutot que d'ecrire
    un second suivi, ce connecteur parle la meme langue : `done`, `result`,
    `generated_files`. La traduction est litterale — `progress` est un
    pourcentage rendu par le service, pas une estimation d'ARENA — et un champ
    que MoneyPrinter ne donne pas reste absent.
    """
    etat = donnees.get("state")
    fichiers = donnees.get("combined_videos") or donnees.get("videos") or []
    resultat: Dict[str, Any] = {
        "success": etat == TACHE_TERMINEE and bool(fichiers),
        "generated_files": [str(chemin) for chemin in fichiers if chemin],
    }

    progression = donnees.get("progress")
    if isinstance(progression, (int, float)):
        # 0-100 : un total connu et une avancee reelle, pas une barre inventee.
        resultat["total_tasks"] = 100
        resultat["successful_tasks"] = int(progression)

    erreur = donnees.get("error")
    etape = donnees.get("failed_stage")
    if erreur or etat == TACHE_ECHOUEE:
        resultat["errors"] = [str(erreur or f"echec a l'etape {etape or 'inconnue'}")]

    return {"done": etat in (TACHE_TERMINEE, TACHE_ECHOUEE), "result": resultat}


class MoneyPrinterConnector(Connecteur):
    """Generation de videos courtes par MoneyPrinterTurbo, en local."""

    service = "video_generation"
    nom = "moneyprinter"

    def __init__(self, appel: Optional[AppelHttp] = None,
                 appel_generation: Optional[AppelHttp] = None,
                 jeton: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._appel = appel or _get
        self._appel_generation = appel_generation or _post
        self._jeton = JETON if jeton is None else jeton
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a: float = 0.0

    # --- Capacites ------------------------------------------------------------

    def capacites(self) -> Dict[str, Capacite]:
        """Une generation, deux lectures. Supprimer une tache n'est pas declare."""
        return {
            "generer": Capacite(
                nom="generer", action="generate",
                description=("Fabrique une video courte a partir d'un sujet : script, "
                             "plans, voix, sous-titres, montage."),
                ecriture=True, quota_par_minute=GENERATIONS_PAR_MINUTE),
            "etat_travail": Capacite(
                nom="etat_travail", action="read",
                description="Ou en est une generation lancee, par son identifiant.",
                ecriture=False, quota_par_minute=QUOTA_LECTURE_PAR_MINUTE),
            "taches": Capacite(
                nom="taches", action="read",
                description="Les generations connues du service.",
                ecriture=False, quota_par_minute=QUOTA_LECTURE_PAR_MINUTE),
        }

    def authentifier(self) -> bool:
        """Vrai : le service est local. Un jeton n'est exige que s'il en pose un.

        Ce n'est pas une authentification reussie, c'est l'absence
        d'authentification requise — et c'est ce qui rend ce connecteur
        utilisable sans toucher au moindre secret.
        """
        return True

    # --- Sante -----------------------------------------------------------------

    def sonder(self) -> Sante:
        """Demande la liste des taches. Un port ouvert ne prouve rien."""
        from core.connectors.base import _maintenant

        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante

        try:
            charge = self._appel("tasks", {"page": 1, "page_size": 1}, self._jeton)
        except Exception as erreur:  # noqa: BLE001 — un service eteint est un etat
            sante = Sante(
                etat=EtatSante.NON_CONFIGURE,
                message=(f"MoneyPrinterTurbo ne repond pas sur {BASE_URL} "
                         f"({type(erreur).__name__})."),
                ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        else:
            donnees = _donnees(charge)
            total = donnees.get("total")
            compte = f"{total} tache(s) connue(s)" if isinstance(total, int) else "joignable"
            sante = Sante(etat=EtatSante.OPERATIONNEL,
                          message=f"MoneyPrinterTurbo repond : {compte}.",
                          mesure_le=_maintenant())

        self._sante = sante
        self._sante_mesuree_a = maintenant
        return sante

    # --- Execution ---------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        if capacite.nom == "generer":
            return self._generer(capacite, parametres)
        if capacite.nom == "etat_travail":
            return self._etat(capacite, parametres)
        return self._taches(capacite, parametres)

    def _generer(self, capacite: Capacite, parametres: Dict[str, Any]) -> ResultatAction:
        """Lance la generation. Appelee **uniquement** apres confirmation."""
        sujet = str(parametres.get("sujet") or "").strip()
        if not sujet:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucun sujet : il n'y a rien a raconter en video.")

        corps: Dict[str, Any] = {
            "video_subject": sujet,
            "video_aspect": str(parametres.get("format") or FORMAT_VERTICAL),
            "video_count": 1,
            "subtitle_enabled": True,
        }
        langue = str(parametres.get("langue") or "").strip()
        if langue:
            corps["video_language"] = langue
        voix = str(parametres.get("voix") or "").strip()
        if voix:
            corps["voice_name"] = voix

        try:
            charge = self._appel_generation("videos", corps, self._jeton)
        except Exception as erreur:  # noqa: BLE001
            logger.info("Generation refusee : %s", type(erreur).__name__)
            if "Connect" in type(erreur).__name__ or "Timeout" in type(erreur).__name__:
                return non_configure(action=capacite.nom, cible=self.nom,
                                     ce_qui_manque=CE_QUI_MANQUE)
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"MoneyPrinterTurbo a refuse : {type(erreur).__name__}.")

        identifiant = _donnees(charge).get("task_id")
        if not identifiant:
            # Sans identifiant, rien ne permettra de suivre la generation ni de
            # prouver qu'elle a eu lieu. Un succes sans preuve ne se construit pas.
            return echec(
                action=capacite.nom, cible=self.nom,
                message="Le service a accepte l'appel sans rendre d'identifiant de tache.")

        return succes(
            action=capacite.nom, cible=self.nom,
            message=(f"Video lancee sur la machine (tache {identifiant}). Elle avance "
                     "en fond ; le chat ne l'attend pas."),
            preuve=str(identifiant), sujet=sujet)

    def _etat(self, capacite: Capacite, parametres: Dict[str, Any]) -> ResultatAction:
        """L'etat d'une tache, traduit dans la forme que le suivi sait lire."""
        identifiant = str(parametres.get("job_id") or parametres.get("task_id") or "").strip()
        if not identifiant:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucun identifiant de tache : rien a regarder.")
        try:
            charge = self._appel(f"tasks/{identifiant}", {}, self._jeton)
        except Exception as erreur:  # noqa: BLE001
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Le service n'a pas repondu : {type(erreur).__name__}.")

        donnees = _donnees(charge)
        return succes(
            action=capacite.nom, cible=self.nom,
            message=f"Etat de la tache {identifiant} : {donnees.get('state')}.",
            preuve=identifiant, donnees=instantane_de(donnees))

    def _taches(self, capacite: Capacite, parametres: Dict[str, Any]) -> ResultatAction:
        try:
            charge = self._appel("tasks", {
                "page": int(parametres.get("page") or 1),
                "page_size": int(parametres.get("limite") or 10),
            }, self._jeton)
        except Exception as erreur:  # noqa: BLE001
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Le service n'a pas repondu : {type(erreur).__name__}.")
        donnees = _donnees(charge)
        taches: List[Any] = donnees.get("tasks") or []
        return succes(action=capacite.nom, cible=self.nom,
                      message=f"{len(taches)} generation(s) connue(s).",
                      preuve="GET tasks", donnees=taches,
                      total=donnees.get("total"))
