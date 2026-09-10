"""Connecteur HiDream-I1 — generation d'image haute qualite, moteur isole.

Mission ARENA x HIDREAM-I1 (DEC-0085). HiDream-I1 (17B parametres, MoE,
MIT — voir `docs/audits/hidream_i1_audit.md`) exige torch/diffusers/
transformers/accelerate, que l'environnement principal d'ARENA n'installe
JAMAIS (`requirements.txt`, commentaire sur `txtai_minimal`). Comme WanGP et
MoneyPrinterTurbo, le moteur tourne donc **hors de ce depot**, dans son
propre environnement isole (`tools/image/hidream/`, venv separe), et parle a
ARENA par une petite API HTTP — le MEME contrat que
`core/connectors/moneyprinter.py`, pas un second style invente.

**Ce que ce connecteur ajoute, et que WanGP/MoneyPrinter n'ont pas besoin de
faire : un controle materiel AVANT d'envoyer la generation.** Un modele de
63 Go (transformer + 3 encodeurs texte + le 4e encodeur Llama-3.1-8B, hors
paquet) ne se lance pas sur la foi d'une reponse HTTP `200`. Avant chaque
`generer`, ce connecteur relit `/health` (le materiel que le worker a
lui-meme mesure — local ou distant, meme contrat) et applique
`core/production/hidream_strategie.py::decider_strategie` : une strategie
`UNSUPPORTED` refuse **avant** d'envoyer quoi que ce soit au worker, jamais
apres un OOM.

**Quatre regles, au-dela du contrat commun `Connecteur` :**

1. **Le materiel est mesure par celui qui va vraiment charger le modele.**
   Le worker mesure SA propre machine (`nvidia-smi`/`psutil` locaux au
   worker) — jamais ARENA qui devine la VRAM d'une machine distante.
2. **Generer est une ecriture, et elle passe par confirmation.** Comme
   WanGP/MoneyPrinterTurbo : `video_generation` a son pendant
   `image_generation` dans `config/permissions_services.yaml`, jamais fondu
   dans le premier.
3. **La generation ne se fait pas attendre ici.** `generer` rend un
   identifiant de tache ; `core/connectors/suivi_video.py::suivre_generation`
   (deja generique, ecrit pour WanGP) suit ce connecteur SANS
   modification — meme forme `{done, result: {success, generated_files}}`.
4. **Un engin de repli n'est jamais annonce comme HiDream.** `_executer`
   rend `engine` dans son detail : un appelant qui compare plusieurs
   moteurs ne doit jamais confondre un HiDream refuse avec un HiDream qui a
   genere.
5. **« Termine » n'est jamais pris pour une preuve.** Le worker se dit
   `completed` ; ce connecteur ROUVRE chaque fichier annonce
   (`core/production/artefact_image.py::valider_image`) avant de confirmer
   le succes a l'appelant — mission §14, la meme discipline que
   `core/connectors/xaar_kaname.py` applique deja a un fichier produit.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import httpx

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante
from core.production.artefact_image import ProvenanceImage, ecrire_provenance, valider_image
from core.production.hidream_strategie import PROFILS, StrategieHiDream, decider_strategie
from core.production.materiel import EtatDisque, EtatGpu, EtatRam

logger = logging.getLogger("usman.connecteurs.hidream")

#: Ou joindre le worker HiDream. Localhost par defaut — un worker distant
#: (mission §23-24, serveur GPU futur) se configure en changeant cette seule
#: variable, jamais un chemin en dur.
BASE_URL = os.getenv("HIDREAM_WORKER_URL", "http://127.0.0.1:8090")
JETON = os.getenv("HIDREAM_WORKER_API_KEY", "")

CE_QUI_MANQUE = (
    "Le worker HiDream-I1 lance, dans son environnement isole : "
    "python tools/image/hidream/serveur_hidream.py "
    "(depuis un venv contenant torch/diffusers/transformers/accelerate — "
    "voir tools/image/hidream/README.md). L'adresse se change avec "
    "HIDREAM_WORKER_URL."
)

#: Une generation HiDream occupe la carte graphique bien plus longtemps
#: qu'une scene WanGP (17B parametres, jusqu'a 50 pas de debruitage) —
#: plafond plus bas que video_generation (4/min) par prudence.
GENERATIONS_PAR_MINUTE = 2
QUOTA_LECTURE_PAR_MINUTE = 60

DELAI_SECONDES = 30.0
DUREE_SONDE_SECONDES = 60.0

#: Les seules variantes reellement publiees par HiDream-I1 (README amont) —
#: jamais une quatrieme devinee.
VARIANTES_CONNUES = ("full", "dev", "fast")
VARIANTE_PAR_DEFAUT = "fast"


def _entetes(jeton: str) -> Dict[str, str]:
    return {"x-api-key": jeton} if jeton else {}


def _get(chemin: str, parametres: Dict[str, Any], jeton: str) -> Dict[str, Any]:
    url = f"{BASE_URL.rstrip('/')}/{chemin.lstrip('/')}"
    with httpx.Client(timeout=DELAI_SECONDES) as client:
        reponse = client.get(url, params=parametres, headers=_entetes(jeton))
        reponse.raise_for_status()
        return reponse.json()


def _post(chemin: str, charge: Dict[str, Any], jeton: str) -> Dict[str, Any]:
    url = f"{BASE_URL.rstrip('/')}/{chemin.lstrip('/')}"
    with httpx.Client(timeout=DELAI_SECONDES) as client:
        reponse = client.post(url, json=charge, headers=_entetes(jeton))
        reponse.raise_for_status()
        return reponse.json()


AppelHttp = Callable[[str, Dict[str, Any], str], Dict[str, Any]]


def _materiel_depuis_sante(brut: Dict[str, Any]) -> tuple:
    """Reconstruit `(EtatGpu, EtatRam, EtatDisque)` depuis le JSON `/health`
    du worker — chaque champ absent ou mal forme rend `None` pour SA seule
    entree, jamais une exception qui ferait echouer tout le controle."""
    materiel = brut.get("materiel") if isinstance(brut, dict) else None
    if not isinstance(materiel, dict):
        return None, None, None

    gpu = None
    brut_gpu = materiel.get("gpu")
    if isinstance(brut_gpu, dict):
        try:
            gpu = EtatGpu(
                nom=str(brut_gpu["nom"]), vram_totale_mo=int(brut_gpu["vram_totale_mo"]),
                vram_libre_mo=int(brut_gpu["vram_libre_mo"]),
                mesure_le=str(brut_gpu.get("mesure_le") or ""))
        except (KeyError, TypeError, ValueError):
            gpu = None

    ram = None
    brut_ram = materiel.get("ram")
    if isinstance(brut_ram, dict):
        try:
            ram = EtatRam(
                totale_mo=int(brut_ram["totale_mo"]), disponible_mo=int(brut_ram["disponible_mo"]),
                mesure_le=str(brut_ram.get("mesure_le") or ""))
        except (KeyError, TypeError, ValueError):
            ram = None

    disque = None
    brut_disque = materiel.get("disque")
    if isinstance(brut_disque, dict):
        try:
            disque = EtatDisque(
                chemin=str(brut_disque.get("chemin") or ""), libre_mo=int(brut_disque["libre_mo"]),
                mesure_le=str(brut_disque.get("mesure_le") or ""))
        except (KeyError, TypeError, ValueError):
            disque = None

    return gpu, ram, disque


def instantane_de(donnees: Dict[str, Any]) -> Dict[str, Any]:
    """Traduit l'etat d'une tache HiDream dans la forme que
    `core/connectors/suivi_video.py::suivre_generation` sait deja lire —
    ecrite pour WanGP, generique par construction (`done`, `result.success`,
    `result.generated_files`)."""
    etat = str(donnees.get("state") or "")
    fichiers = donnees.get("images") or donnees.get("generated_files") or []
    resultat: Dict[str, Any] = {
        "success": etat == "completed" and bool(fichiers),
        "generated_files": [str(chemin) for chemin in fichiers if chemin],
    }
    if donnees.get("seed") is not None:
        resultat["seed"] = donnees["seed"]
    erreur = donnees.get("error")
    if erreur or etat == "failed":
        resultat["errors"] = [str(erreur or "echec sans detail rendu par le worker")]
    return {"done": etat in ("completed", "failed", "cancelled"), "result": resultat}


def _valider_et_enregistrer(resultat: Dict[str, Any], charge: Dict[str, Any]) -> Dict[str, Any]:
    """Rouvre chaque fichier que le worker annonce, et n'ecrit la provenance
    QUE pour ceux qui sont reellement des images valides.

    Un fichier annonce mais illisible/tronque retire `success` — « le
    worker a dit termine » ne devient jamais « ARENA confirme un artefact »
    sans cette relecture (mission §14).
    """
    validations = []
    fichiers_valides = []
    for chemin_brut in resultat.get("generated_files", []):
        chemin = Path(chemin_brut)
        validation = valider_image(chemin)
        validations.append(validation.to_dict())
        if validation.valide:
            fichiers_valides.append(chemin_brut)
            ecrire_provenance(chemin, ProvenanceImage(
                modele="HiDream-I1", modele_version=str(charge.get("variante") or ""),
                fournisseur="hidream", seed=resultat.get("seed"),
                largeur=validation.largeur or 0, hauteur=validation.hauteur or 0,
                prompt=str(charge.get("prompt") or "")))

    resultat = dict(resultat)
    resultat["validations"] = validations
    if len(fichiers_valides) != len(resultat.get("generated_files", [])):
        resultat["success"] = False
        resultat["generated_files"] = fichiers_valides
        erreurs = resultat.get("errors", [])
        erreurs.append("un ou plusieurs fichiers annonces par le worker ne sont pas des "
                       "images valides — voir 'validations'.")
        resultat["errors"] = erreurs
    return resultat


class HiDreamConnector(Connecteur):
    """Generation d'image HiDream-I1, par son worker isole — jamais importe."""

    service = "image_generation"
    nom = "hidream"

    def __init__(self, appel: Optional[AppelHttp] = None,
                 appel_generation: Optional[AppelHttp] = None,
                 jeton: Optional[str] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._appel = appel or _get
        self._appel_generation = appel_generation or _post
        self._jeton = JETON if jeton is None else jeton
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a: float = 0.0

    # --- Capacites ---------------------------------------------------------

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "capacites": Capacite(
                nom="capacites", action="read",
                description="Ce que le worker HiDream sait faire, et le materiel qu'il a mesure.",
                ecriture=False, quota_par_minute=QUOTA_LECTURE_PAR_MINUTE),
            "generer": Capacite(
                nom="generer", action="generate",
                description="Genere une image haute qualite (HiDream-I1) sur le worker.",
                ecriture=True, quota_par_minute=GENERATIONS_PAR_MINUTE),
            "etat_travail": Capacite(
                nom="etat_travail", action="read",
                description="Ou en est une generation lancee, par son identifiant.",
                ecriture=False, quota_par_minute=QUOTA_LECTURE_PAR_MINUTE),
            "annuler_travail": Capacite(
                nom="annuler_travail", action="cancel",
                description="Arrete une generation en cours.",
                ecriture=True),
        }

    def authentifier(self) -> bool:
        return True

    # --- Sante ---------------------------------------------------------------

    def sonder(self) -> Sante:
        from core.connectors.base import _maintenant

        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante

        try:
            charge = self._appel("health", {}, self._jeton)
        except Exception as erreur:  # noqa: BLE001 — un worker eteint est un etat
            sante = Sante(
                etat=EtatSante.NON_CONFIGURE,
                message=f"Le worker HiDream ne repond pas sur {BASE_URL} ({type(erreur).__name__}).",
                ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        else:
            variantes = charge.get("variantes_disponibles") or []
            sante = Sante(
                etat=EtatSante.OPERATIONNEL,
                message=f"Worker HiDream joignable : {len(variantes)} variante(s) en cache.",
                mesure_le=_maintenant())

        self._sante = sante
        self._sante_mesuree_a = maintenant
        return sante

    # --- Execution -------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        if capacite.nom == "capacites":
            return self._lire_capacites(capacite)
        if capacite.nom == "generer":
            return self._generer(capacite, parametres)
        if capacite.nom == "etat_travail":
            return self._etat(capacite, parametres)
        return self._annuler(capacite, parametres)

    def _lire_capacites(self, capacite: Capacite) -> ResultatAction:
        try:
            charge = self._appel("health", {}, self._jeton)
        except Exception as erreur:  # noqa: BLE001
            return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=CE_QUI_MANQUE,
                                 detail_erreur=type(erreur).__name__)
        return succes(action=capacite.nom, cible=self.nom,
                     message="Etat et materiel du worker HiDream.",
                     preuve="GET /health", donnees=charge)

    def _generer(self, capacite: Capacite, parametres: Dict[str, Any]) -> ResultatAction:
        """Lance une generation. Appelee **uniquement** apres confirmation.

        Refuse AVANT tout envoi si le materiel rapporte par le worker
        (local ou distant) ne tient pas la variante demandee — jamais un
        essai qui se termine en OOM sur la carte du proprietaire.
        """
        prompt = str(parametres.get("prompt") or "").strip()
        if not prompt:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucun prompt : rien a generer.")

        variante = str(parametres.get("variante") or VARIANTE_PAR_DEFAUT).strip().lower()
        if variante not in VARIANTES_CONNUES:
            return echec(action=capacite.nom, cible=self.nom,
                         message=(f"Variante inconnue « {variante} » — "
                                 f"connues : {', '.join(VARIANTES_CONNUES)}."))

        try:
            sante_brute = self._appel("health", {}, self._jeton)
        except Exception as erreur:  # noqa: BLE001
            return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=CE_QUI_MANQUE,
                                 detail_erreur=type(erreur).__name__)

        gpu, ram, disque = _materiel_depuis_sante(sante_brute)
        decision = decider_strategie(
            PROFILS[variante], gpu, ram, disque,
            worker_distant_configure=not _worker_local())
        if decision.strategie is StrategieHiDream.UNSUPPORTED:
            return non_configure(
                action=capacite.nom, cible=self.nom,
                ce_qui_manque=(f"materiel insuffisant pour HiDream-I1-{variante} : "
                              f"{decision.raison}"))

        corps: Dict[str, Any] = {
            "prompt": prompt, "variante": variante, "strategie": decision.strategie.value,
        }
        for cle_arena, cle_worker in (
            ("negative_prompt", "negative_prompt"), ("width", "width"), ("height", "height"),
            ("steps", "num_inference_steps"), ("guidance", "guidance_scale"), ("seed", "seed"),
        ):
            if parametres.get(cle_arena) is not None:
                corps[cle_worker] = parametres[cle_arena]

        try:
            charge = self._appel_generation("generate", corps, self._jeton)
        except Exception as erreur:  # noqa: BLE001
            logger.info("Generation HiDream refusee : %s", type(erreur).__name__)
            if "Connect" in type(erreur).__name__ or "Timeout" in type(erreur).__name__:
                return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=CE_QUI_MANQUE)
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Le worker a refuse : {type(erreur).__name__}.")

        identifiant = charge.get("job_id")
        if not identifiant:
            return echec(
                action=capacite.nom, cible=self.nom,
                message="Le worker a accepte l'appel sans rendre d'identifiant de tache.")

        return succes(
            action=capacite.nom, cible=self.nom,
            message=(f"Generation HiDream-I1-{variante} lancee (tache {identifiant}, "
                     f"strategie {decision.strategie.value}). Elle avance en fond ; "
                     "le chat ne l'attend pas."),
            preuve=str(identifiant), variante=variante, strategie=decision.strategie.value,
            engine="hidream")

    def _etat(self, capacite: Capacite, parametres: Dict[str, Any]) -> ResultatAction:
        identifiant = str(parametres.get("job_id") or "").strip()
        if not identifiant:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucun identifiant de tache : rien a regarder.")
        try:
            charge = self._appel(f"jobs/{identifiant}", {}, self._jeton)
        except Exception as erreur:  # noqa: BLE001
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Le worker n'a pas repondu : {type(erreur).__name__}.")

        instantane = instantane_de(charge)
        if instantane["done"] and instantane["result"].get("success"):
            instantane["result"] = _valider_et_enregistrer(instantane["result"], charge)

        return succes(action=capacite.nom, cible=self.nom,
                     message=f"Etat de la tache {identifiant} : {charge.get('state')}.",
                     preuve=identifiant, donnees=instantane)

    def _annuler(self, capacite: Capacite, parametres: Dict[str, Any]) -> ResultatAction:
        identifiant = str(parametres.get("job_id") or "").strip()
        if not identifiant:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucun identifiant de tache : rien a annuler.")
        try:
            charge = self._appel_generation(f"jobs/{identifiant}/cancel", {}, self._jeton)
        except Exception as erreur:  # noqa: BLE001
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Le worker n'a pas repondu : {type(erreur).__name__}.")
        return succes(action=capacite.nom, cible=self.nom,
                     message=f"Annulation demandee pour {identifiant}.",
                     preuve=identifiant, donnees=charge)


def _worker_local() -> bool:
    """Vrai si `BASE_URL` designe cette machine — decide si le controle
    materiel represente CE poste ou une machine distante non mesurable
    localement."""
    return any(motif in BASE_URL for motif in ("127.0.0.1", "localhost", "0.0.0.0"))
