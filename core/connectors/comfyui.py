"""Connecteur ComfyUI — moteur d'execution de workflows generatifs, jamais
un second cerveau.

Mission ARENA x COMFYUI (DEC-0087, `docs/audits/comfyui_audit.md`). ComfyUI
(GPL-3.0, commit `6338e4bd428247a4a8843496aa98fb7f2a9d3632`) est un serveur
complet, deja construit en amont — contrairement a HiDream-I1
(`core/connectors/hidream.py`), ARENA n'ecrit AUCUN worker : ce connecteur
parle directement a l'API HTTP native de ComfyUI (`/system_stats`,
`/prompt`, `/history/{id}`, `/interrupt`, `/free`, `/models/{folder}`,
`/view`) — jamais l'interface graphique, jamais un graphe JSON libre.

**Ce que ce connecteur ajoute, au-dela du contrat commun `Connecteur` :**

1. **Aucun graphe libre n'atteint jamais `/prompt`.** Un appelant fournit un
   `workflow_id` (`core/production/comfyui_workflows.py`, le registre
   CONTROLE) et des parametres nommes — jamais un JSON de noeuds. Un
   workflow inconnu, ou reconnu mais pas encore implemente (statut
   `CANDIDATE`), est refuse AVANT toute construction de requete (mission
   §8/§30).
2. **Le materiel est celui que ComfyUI lui-meme rapporte.** `/system_stats`
   mesure la VRAM/RAM reelles du processus qui va vraiment charger le
   modele — jamais une supposition depuis ARENA (meme principe que
   `core/connectors/hidream.py`, applique a un serveur deja existant plutot
   qu'a un worker ecrit ici).
3. **Chaque modele que le workflow nomme doit exister avant l'envoi.**
   `entree.verification_modeles` (checkpoint, ControlNet, LoRA, modele
   d'agrandissement...) est relu via `GET /models/{dossier}` ; un modele
   absent refuse la generation avant `/prompt`, jamais un telechargement
   automatique (mission §12/§25 : jamais de telechargement aveugle).
4. **Une image de reference ne touche jamais le disque d'ARENA.**
   `image_to_image`/`upscale`/`controlnet_image` prennent leur image en
   base64 (`core/production/comfyui_workflows.py`) ; ce connecteur la
   decode en memoire et la televerse a ComfyUI (`POST /upload/image`)
   juste avant l'envoi — jamais un chemin de fichier local qu'un appelant
   pourrait faire pointer ailleurs (mission §31).
5. **« Termine » n'est jamais pris pour une preuve.** `etat_travail` relit
   chaque image que ComfyUI annonce dans son historique
   (`core/production/artefact_image.py::valider_image`) avant de confirmer
   un succes — meme discipline que HiDream et Xaar Kaname.
6. **Le worker peut liberer sa VRAM.** `decharger` appelle `POST /free`
   (mission §11/§38 : ne jamais laisser un modele resident bloquer le
   reste d'ARENA) — une lecture-ecriture sans effet exterieur, jamais un
   « generate ».
"""
from __future__ import annotations

import base64
import logging
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from apps.backend.config import RENDERED_DIR
from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante
from core.production.artefact_image import ProvenanceImage, ecrire_provenance, valider_image
from core.production.comfyui_strategie import StrategieComfyUI, decider_strategie
from core.production.comfyui_workflows import (
    EntreeWorkflow,
    construire_requete,
    lister,
    obtenir,
    valider_parametres,
)
from core.production.materiel import EtatGpu, EtatRam, mesurer_disque

logger = logging.getLogger("usman.connecteurs.comfyui")

#: Port par defaut du serveur ComfyUI lui-meme (audite dans
#: `script_examples/basic_api_example.py`) — jamais celui du worker HiDream
#: (8090), un service distinct.
BASE_URL = os.getenv("COMFYUI_URL", "http://127.0.0.1:8188")

#: Si ComfyUI ecrit sur le MEME systeme de fichiers qu'ARENA (cas local le
#: plus courant), lire directement son dossier `output/` evite un
#: aller-retour HTTP. Vide par defaut : un serveur distant n'a pas de
#: dossier partage, le connecteur telecharge alors via `/view`.
OUTPUT_DIR = os.getenv("COMFYUI_OUTPUT_DIR", "")

CE_QUI_MANQUE = (
    "Un serveur ComfyUI lance et joignable : python main.py (depuis "
    "l'installation ComfyUI, voir docs/audits/comfyui_audit.md). L'adresse "
    "se change avec COMFYUI_URL."
)

GENERATIONS_PAR_MINUTE = 3
QUOTA_LECTURE_PAR_MINUTE = 60
DELAI_SECONDES = 30.0
DUREE_SONDE_SECONDES = 60.0


def _get(chemin: str, parametres: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{BASE_URL.rstrip('/')}/{chemin.lstrip('/')}"
    with httpx.Client(timeout=DELAI_SECONDES) as client:
        reponse = client.get(url, params=parametres)
        reponse.raise_for_status()
        return reponse.json()


def _post(chemin: str, charge: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{BASE_URL.rstrip('/')}/{chemin.lstrip('/')}"
    with httpx.Client(timeout=DELAI_SECONDES) as client:
        reponse = client.post(url, json=charge)
        reponse.raise_for_status()
        if reponse.content:
            return reponse.json()
        return {}


def _get_brut(chemin: str, parametres: Dict[str, Any]) -> bytes:
    url = f"{BASE_URL.rstrip('/')}/{chemin.lstrip('/')}"
    with httpx.Client(timeout=DELAI_SECONDES) as client:
        reponse = client.get(url, params=parametres)
        reponse.raise_for_status()
        return reponse.content


#: Signatures binaires reconnues, juste assez pour choisir une extension
#: plausible — ComfyUI accepte ce que Pillow ouvre, l'extension n'est
#: qu'indicative pour son propre dossier `input/`.
_SIGNATURES_IMAGE = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"RIFF", ".webp"),  # WEBP : verifie plus loin que "WEBP" suit à l'offset 8
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)


def _extension_devinee(octets: bytes) -> str:
    for signature, extension in _SIGNATURES_IMAGE:
        if not octets.startswith(signature):
            continue
        if signature == b"RIFF" and octets[8:12] != b"WEBP":
            continue
        return extension
    return ".png"  # repli raisonnable — Pillow refusera proprement si c'en n'est pas un


def _post_fichier(chemin: str, octets: bytes, nom_fichier: str) -> Dict[str, Any]:
    url = f"{BASE_URL.rstrip('/')}/{chemin.lstrip('/')}"
    with httpx.Client(timeout=DELAI_SECONDES) as client:
        reponse = client.post(url, files={"image": (nom_fichier, octets, "application/octet-stream")})
        reponse.raise_for_status()
        return reponse.json()


def _materiel_depuis_system_stats(brut: Dict[str, Any]) -> tuple:
    """Traduit `/system_stats` en `(EtatGpu, EtatRam)` — jamais une
    exception si un champ manque ou est mal forme, juste `None` pour cette
    seule entree (meme discipline que hidream.py::_materiel_depuis_sante)."""
    if not isinstance(brut, dict):
        return None, None

    ram = None
    systeme = brut.get("system")
    if isinstance(systeme, dict):
        try:
            ram = EtatRam(
                totale_mo=int(systeme["ram_total"] / (1024 * 1024)),
                disponible_mo=int(systeme["ram_free"] / (1024 * 1024)),
                mesure_le="")
        except (KeyError, TypeError, ValueError):
            ram = None

    gpu = None
    appareils = brut.get("devices")
    if isinstance(appareils, list) and appareils:
        premier = appareils[0]
        if isinstance(premier, dict) and premier.get("type") == "cuda":
            try:
                gpu = EtatGpu(
                    nom=str(premier.get("name") or "GPU"),
                    vram_totale_mo=int(premier["vram_total"] / (1024 * 1024)),
                    vram_libre_mo=int(premier["vram_free"] / (1024 * 1024)),
                    mesure_le="")
            except (KeyError, TypeError, ValueError):
                gpu = None

    return gpu, ram


def _checkpoint_utilise(enregistrement: Dict[str, Any]) -> str:
    """Cherche le premier `CheckpointLoaderSimple` dans le graphe soumis —
    jamais un identifiant de noeud en dur (un futur workflow peut nommer ses
    noeuds autrement). Chaine vide si rien n'est trouve, jamais une
    exception sur une structure inattendue."""
    prompt_soumis = enregistrement.get("prompt")
    if not isinstance(prompt_soumis, list) or len(prompt_soumis) < 3:
        return ""
    graphe = prompt_soumis[2]
    if not isinstance(graphe, dict):
        return ""
    for noeud in graphe.values():
        if isinstance(noeud, dict) and noeud.get("class_type") == "CheckpointLoaderSimple":
            return str((noeud.get("inputs") or {}).get("ckpt_name") or "")
    return ""


def _chemin_contenu(base: Path, sous_dossier: str, nom_fichier: str) -> Optional[Path]:
    """`base / sous_dossier / nom_fichier`, mais seulement si le resultat
    reste reellement SOUS `base` une fois resolu — mission §31 : un
    `subfolder`/`filename` annonce par un service exterieur ne doit jamais
    pouvoir lire un fichier hors du dossier attendu (`../../etc/passwd`,
    chemin absolu, etc.). Rend `None` plutot que de suivre l'evasion."""
    try:
        base_resolue = base.resolve()
        cible = (base / sous_dossier / nom_fichier) if sous_dossier else (base / nom_fichier)
        cible_resolue = cible.resolve()
        cible_resolue.relative_to(base_resolue)
    except (ValueError, OSError):
        logger.warning("Chemin refuse (hors de %s) : subfolder=%r filename=%r",
                       base, sous_dossier, nom_fichier)
        return None
    return cible_resolue


def _images_de_l_historique(enregistrement: Dict[str, Any]) -> list:
    """Toutes les images annoncees par tous les noeuds de sortie — jamais
    seulement le dernier noeud, un graphe futur peut en avoir plusieurs."""
    images = []
    sorties = enregistrement.get("outputs")
    if not isinstance(sorties, dict):
        return images
    for sortie in sorties.values():
        if isinstance(sortie, dict):
            for image in sortie.get("images") or []:
                if isinstance(image, dict) and image.get("filename"):
                    images.append(image)
    return images


class _EchecTeleversement(Exception):
    """Le decodage ou le televersement d'une image de reference a echoue —
    jamais une exception qui remonterait telle quelle a l'appelant."""


class ComfyUIConnector(Connecteur):
    """Execution de workflows ComfyUI approuves — jamais un graphe libre."""

    service = "image_generation"
    nom = "comfyui"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a: float = 0.0

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "capacites": Capacite(
                nom="capacites", action="read",
                description="Etat et materiel du serveur ComfyUI.",
                ecriture=False, quota_par_minute=QUOTA_LECTURE_PAR_MINUTE),
            "lister_workflows": Capacite(
                nom="lister_workflows", action="read",
                description="Les workflows ComfyUI approuves et leur statut.",
                ecriture=False, quota_par_minute=QUOTA_LECTURE_PAR_MINUTE),
            "generer": Capacite(
                nom="generer", action="generate",
                description="Soumet un workflow ComfyUI approuve.",
                ecriture=True, quota_par_minute=GENERATIONS_PAR_MINUTE),
            "etat_travail": Capacite(
                nom="etat_travail", action="read",
                description="Ou en est une soumission, par son prompt_id.",
                ecriture=False, quota_par_minute=QUOTA_LECTURE_PAR_MINUTE),
            "annuler_travail": Capacite(
                nom="annuler_travail", action="cancel",
                description="Interrompt la generation en cours.",
                ecriture=True),
            "decharger": Capacite(
                nom="decharger", action="unload",
                description="Libere les modeles charges en VRAM par ComfyUI.",
                ecriture=True),
        }

    def authentifier(self) -> bool:
        return True

    def sonder(self) -> Sante:
        from core.connectors.base import _maintenant

        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante

        try:
            charge = _get("system_stats", {})
        except Exception as erreur:  # noqa: BLE001 — un serveur eteint est un etat
            sante = Sante(
                etat=EtatSante.NON_CONFIGURE,
                message=f"ComfyUI ne repond pas sur {BASE_URL} ({type(erreur).__name__}).",
                ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        else:
            version = (charge.get("system") or {}).get("comfyui_version", "?")
            sante = Sante(
                etat=EtatSante.OPERATIONNEL,
                message=f"ComfyUI joignable (version {version}).",
                mesure_le=_maintenant())

        self._sante = sante
        self._sante_mesuree_a = maintenant
        return sante

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        if capacite.nom == "capacites":
            return self._lire_capacites(capacite)
        if capacite.nom == "lister_workflows":
            return succes(action=capacite.nom, cible=self.nom,
                         message="Catalogue des workflows ComfyUI approuves.",
                         preuve="workflows", donnees={"workflows": lister()})
        if capacite.nom == "generer":
            return self._generer(capacite, parametres)
        if capacite.nom == "etat_travail":
            return self._etat(capacite, parametres)
        if capacite.nom == "decharger":
            return self._decharger(capacite)
        return self._annuler(capacite, parametres)

    def _lire_capacites(self, capacite: Capacite) -> ResultatAction:
        try:
            charge = _get("system_stats", {})
        except Exception as erreur:  # noqa: BLE001
            return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=CE_QUI_MANQUE,
                                 detail_erreur=type(erreur).__name__)
        return succes(action=capacite.nom, cible=self.nom,
                     message="Etat et materiel du serveur ComfyUI.",
                     preuve="GET /system_stats", donnees=charge)

    def _generer(self, capacite: Capacite, parametres: Dict[str, Any]) -> ResultatAction:
        """Soumet un workflow approuve. Appelee uniquement apres
        confirmation (service `image_generation`, action `generate`).

        Refuse AVANT tout envoi : workflow inconnu/pas implemente, checkpoint
        absent, ou materiel insuffisant — jamais un essai qui echoue en OOM.
        """
        workflow_id = str(parametres.get("workflow_id") or "").strip()
        if not workflow_id:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucun workflow_id : rien a soumettre.")

        entree = obtenir(workflow_id)
        if entree is None:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Workflow inconnu : « {workflow_id} ».")
        if not entree.implemente:
            return echec(
                action=capacite.nom, cible=self.nom,
                message=(f"Workflow « {workflow_id} » reconnu (statut {entree.statut.value}) "
                         "mais pas encore implemente — aucun gabarit disponible."))

        validation = valider_parametres(workflow_id, {k: v for k, v in parametres.items()
                                                      if k != "workflow_id"})
        if not validation.ok:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Parametres invalides : " + " ; ".join(validation.erreurs))

        try:
            stats = _get("system_stats", {})
        except Exception as erreur:  # noqa: BLE001
            return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=CE_QUI_MANQUE,
                                 detail_erreur=type(erreur).__name__)

        erreur_modele = self._verifier_modeles(entree, validation.parametres)
        if erreur_modele is not None:
            return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=erreur_modele)

        gpu, ram = _materiel_depuis_system_stats(stats)
        disque = mesurer_disque(Path(OUTPUT_DIR) if OUTPUT_DIR else Path("."))
        decision = decider_strategie(
            entree.profil_ressources, gpu, ram, disque,
            worker_distant_configure=not _serveur_local())
        if decision.strategie is StrategieComfyUI.UNSUPPORTED:
            return non_configure(
                action=capacite.nom, cible=self.nom,
                ce_qui_manque=f"materiel insuffisant pour « {workflow_id} » : {decision.raison}")

        try:
            parametres_prets = self._televerser_images(entree, validation.parametres)
        except _EchecTeleversement as erreur:
            return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=str(erreur))

        try:
            requete = construire_requete(workflow_id, parametres_prets)
        except ValueError as erreur:
            return echec(action=capacite.nom, cible=self.nom, message=str(erreur))

        try:
            reponse = _post("prompt", {"prompt": requete})
        except Exception as erreur:  # noqa: BLE001
            logger.info("Soumission ComfyUI refusee : %s", type(erreur).__name__)
            if "Connect" in type(erreur).__name__ or "Timeout" in type(erreur).__name__:
                return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=CE_QUI_MANQUE)
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"ComfyUI a refuse : {type(erreur).__name__}.")

        identifiant = reponse.get("prompt_id")
        erreurs_noeuds = reponse.get("node_errors")
        if not identifiant:
            detail = f" ({erreurs_noeuds})" if erreurs_noeuds else ""
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"ComfyUI n'a pas rendu de prompt_id{detail}.")

        return succes(
            action=capacite.nom, cible=self.nom,
            message=(f"Workflow « {workflow_id} » soumis (tache {identifiant}, strategie "
                     f"{decision.strategie.value}). Il avance en fond ; le chat ne l'attend pas."),
            preuve=str(identifiant), workflow_id=workflow_id,
            strategie=decision.strategie.value, engine="comfyui",
            seed=validation.parametres.get("seed"))

    def _verifier_modeles(self, entree: EntreeWorkflow, parametres: Dict[str, Any]) -> Optional[str]:
        """Rend un message « ce qui manque » si un modele nomme par
        `entree.verification_modeles` n'est pas installe — `None` si tout
        tient. Generalise le controle checkpoint au-dela de `ckpt_name`
        (mission §12/§25 : jamais un telechargement a l'aveugle)."""
        for parametre, dossier in entree.verification_modeles.items():
            nom_modele = parametres.get(parametre)
            if not nom_modele:
                continue
            try:
                disponibles = _get(f"models/{dossier}", {})
            except Exception as erreur:  # noqa: BLE001
                return f"{CE_QUI_MANQUE} ({type(erreur).__name__} en verifiant models/{dossier})"
            if not isinstance(disponibles, list) or nom_modele not in disponibles:
                return (f"le modele « {nom_modele} » installe dans models/{dossier}/ de ComfyUI "
                       f"(disponibles : {disponibles if isinstance(disponibles, list) else 'aucun'}).")
        return None

    def _televerser_images(
        self, entree: EntreeWorkflow, parametres: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Decode chaque parametre `image_base64` du schema et le televerse
        a ComfyUI (`POST /upload/image`) — rend une COPIE de `parametres` ou
        ces valeurs sont remplacees par le nom que ComfyUI a attribue, seul
        vocabulaire que `LoadImage` accepte. Leve `_EchecTeleversement`
        plutot que de laisser un octet invalide atteindre `construire_requete`."""
        prets = dict(parametres)
        for nom, spec in entree.schema_entree.items():
            if spec.type != "image_base64":
                continue
            valeur = parametres.get(nom)
            if not valeur:
                continue
            try:
                octets = base64.b64decode(valeur, validate=True)
            except (ValueError, TypeError) as erreur:
                raise _EchecTeleversement(f"{nom} : base64 illisible ({type(erreur).__name__}).") from erreur

            nom_fichier = f"arena-ref-{random.randint(0, 2**32 - 1):08x}{_extension_devinee(octets)}"
            try:
                reponse = _post_fichier("upload/image", octets, nom_fichier)
            except Exception as erreur:  # noqa: BLE001
                raise _EchecTeleversement(
                    f"{CE_QUI_MANQUE} (televersement de {nom} en echec : "
                    f"{type(erreur).__name__}).") from erreur

            nom_distant = str(reponse.get("name") or "")
            if not nom_distant:
                raise _EchecTeleversement(
                    f"ComfyUI n'a pas rendu de nom apres le televersement de {nom}.")
            sous_dossier = str(reponse.get("subfolder") or "")
            prets[nom] = f"{sous_dossier}/{nom_distant}" if sous_dossier else nom_distant
        return prets

    def _telecharger_si_besoin(self, image: Dict[str, Any]) -> Optional[Path]:
        """Rend le chemin LOCAL du fichier annonce par ComfyUI : lecture
        directe si `COMFYUI_OUTPUT_DIR` est configure (serveur local, meme
        systeme de fichiers), sinon telechargement via `GET /view` dans
        `RENDERED_DIR` (serveur distant, mission §33/34).

        `filename`/`subfolder` viennent de la reponse HTTP d'un service
        exterieur — mission §31, jamais fait confiance sans verification.
        Un `../../` qui tenterait d'echapper au dossier attendu est refuse
        ici, jamais suivi."""
        nom_fichier = str(image.get("filename") or "")
        sous_dossier = str(image.get("subfolder") or "")
        type_sortie = str(image.get("type") or "output")
        if not nom_fichier:
            return None

        if OUTPUT_DIR:
            chemin = _chemin_contenu(Path(OUTPUT_DIR), sous_dossier, nom_fichier)
            if chemin is not None and chemin.is_file():
                return chemin

        try:
            contenu = _get_brut(
                "view", {"filename": nom_fichier, "subfolder": sous_dossier, "type": type_sortie})
        except Exception as erreur:  # noqa: BLE001
            logger.info("Telechargement ComfyUI en echec pour %s : %s",
                       nom_fichier, type(erreur).__name__)
            return None

        RENDERED_DIR.mkdir(parents=True, exist_ok=True)
        #: `Path(nom_fichier).name` retire toute composante de repertoire
        #: (donc tout `../`) avant de fabriquer le nom local — le nom
        #: d'origine ne decide jamais OU le fichier telecharge atterrit.
        cible = RENDERED_DIR / f"comfyui-{random.randint(0, 2**32 - 1):08x}-{Path(nom_fichier).name}"
        cible.write_bytes(contenu)
        return cible

    def _etat(self, capacite: Capacite, parametres: Dict[str, Any]) -> ResultatAction:
        identifiant = str(parametres.get("job_id") or parametres.get("prompt_id") or "").strip()
        if not identifiant:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucun identifiant de tache : rien a regarder.")
        try:
            historique = _get(f"history/{identifiant}", {})
        except Exception as erreur:  # noqa: BLE001
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"ComfyUI n'a pas repondu : {type(erreur).__name__}.")

        enregistrement = historique.get(identifiant) if isinstance(historique, dict) else None
        if not enregistrement:
            # Ni en file, ni dans l'historique : soit encore en cours, soit
            # jamais soumis. Le chat ne l'attend pas, donc "pas termine".
            instantane = {"done": False, "result": {"success": False, "generated_files": []}}
            return succes(action=capacite.nom, cible=self.nom,
                         message=f"Tache {identifiant} : pas encore dans l'historique (en file "
                                 "ou inconnue).",
                         preuve=identifiant, donnees=instantane)

        statut = enregistrement.get("status") or {}
        termine = bool(statut.get("completed"))
        reussi_brut = statut.get("status_str") == "success"
        images = _images_de_l_historique(enregistrement)

        resultat: Dict[str, Any] = {"success": termine and reussi_brut and bool(images),
                                    "generated_files": []}
        if not reussi_brut and statut.get("messages"):
            resultat["errors"] = [str(statut["messages"])]

        if resultat["success"]:
            fichiers_valides = []
            validations = []
            checkpoint = _checkpoint_utilise(enregistrement)
            for image in images:
                chemin = self._telecharger_si_besoin(image)
                if chemin is None:
                    validations.append({"valide": False, "raison": "telechargement impossible"})
                    continue
                validation = valider_image(chemin)
                validations.append(validation.to_dict())
                if validation.valide:
                    fichiers_valides.append(str(chemin))
                    ecrire_provenance(chemin, ProvenanceImage(
                        modele=checkpoint or "comfyui", modele_version=identifiant,
                        fournisseur="comfyui",
                        largeur=validation.largeur or 0, hauteur=validation.hauteur or 0))
            resultat["generated_files"] = fichiers_valides
            resultat["validations"] = validations
            if len(fichiers_valides) != len(images):
                resultat["success"] = False
                resultat.setdefault("errors", []).append(
                    "un ou plusieurs fichiers annonces par ComfyUI ne sont pas des images "
                    "valides — voir 'validations'.")

        instantane = {"done": termine, "result": resultat}
        return succes(action=capacite.nom, cible=self.nom,
                     message=f"Etat de la tache {identifiant} : "
                             f"{'terminee' if termine else 'en cours'}.",
                     preuve=identifiant, donnees=instantane)

    def _annuler(self, capacite: Capacite, parametres: Dict[str, Any]) -> ResultatAction:
        identifiant = str(parametres.get("job_id") or parametres.get("prompt_id") or "").strip()
        try:
            _post("interrupt", {"prompt_id": identifiant} if identifiant else {})
        except Exception as erreur:  # noqa: BLE001
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"ComfyUI n'a pas repondu : {type(erreur).__name__}.")
        return succes(action=capacite.nom, cible=self.nom,
                     message=f"Interruption demandee{f' pour {identifiant}' if identifiant else ''}.",
                     preuve=identifiant or "global")

    def _decharger(self, capacite: Capacite) -> ResultatAction:
        try:
            _post("free", {"unload_models": True, "free_memory": True})
        except Exception as erreur:  # noqa: BLE001
            return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=CE_QUI_MANQUE,
                                 detail_erreur=type(erreur).__name__)
        return succes(action=capacite.nom, cible=self.nom,
                     message="Modeles ComfyUI decharges de la VRAM.", preuve="POST /free")


def _serveur_local() -> bool:
    """Vrai si `BASE_URL` designe cette machine — decide si le controle
    materiel represente CE poste ou un serveur distant non mesurable
    localement (meme fonction que hidream.py::_worker_local)."""
    return any(motif in BASE_URL for motif in ("127.0.0.1", "localhost", "0.0.0.0"))
