"""L'orchestrateur Video : compose les capacites reelles sur un projet.

Trouve necessaire le 01/09/2026 (DEC-0037, demande directe du proprietaire) :
WanGP, MoneyPrinterTurbo, le montage et VoiceStudio existent deja et
fonctionnent chacun seul, mais rien ne les composait sur un meme projet.

**Ce que cet agent ne fait pas**, et qui est le sujet :

- Il **n'invente aucune capacite**. Le modele propose un graphe d'etapes
  parmi une liste fermee (`core/production/plan_video.py`) ; un nom hors de
  cette liste est refuse et nomme, jamais devine.
- Il **ne confirme rien a la place du proprietaire**. Generer une scene
  (WanGP), fabriquer une video (MoneyPrinterTurbo) ou parler (VoiceStudio)
  restent des ECRITURES qui passent par la file de confirmation existante
  (`core/actions/attente.py`, verrouillee) — cet agent les SOUMET, il ne les
  execute jamais d'autorite. Question posee explicitement au proprietaire le
  01/09/2026 ; sa reponse : « il attend ma confirmation a chaque etape
  d'ecriture ».
- Il **ne pretend jamais qu'un fichier existe avant qu'il existe**. Une
  generation WanGP/MoneyPrinterTurbo est un travail de fond suivi a part
  (`suivre_la_generation`) : son `preuve` a la soumission est un identifiant
  de tache, jamais un chemin. Un plan qui ferait dependre un montage
  directement d'une generation ou d'une narration est refuse au moment du
  plan (`plan_video.py`), pas silencieusement mal execute plus tard.
"""
from __future__ import annotations

import base64
import inspect
import logging
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from apps.backend.config import RENDERED_DIR
from core.agent.base_agent import BaseAgent
from core.characters.registry import Personnage, charger_personnage, enregistrer_generation
from core.execution.coordination import Coordination, Etape
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
from core.production import image_backend_router, personnage_video, plan_drift
from core.production.etat_projet import EtapeProjet, EtatProjetVideo
from core.production.plan_video import (
    CAPACITES_VIDEO,
    PlanRefuse,
    extraire_json,
    prompt_de_planification,
    valider_graphe,
)

logger = logging.getLogger("usman.agent.production_video")

#: Les deux capacites qui se disputent le meme GPU physique (RTX A2000, une
#: seule carte) : generation de scene WanGP, et vision locale (Qwen3-VL,
#: servie par Ollama). MoneyPrinterTurbo et VoiceStudio sont des services
#: externes (HTTP) ; le montage est un travail ffmpeg (CPU). Aucun des trois
#: n'entre dans ce groupe.
RESSOURCE_GPU_LOCAL = "gpu_local"
#: Drift (DEC-0057) est un programme de bureau SEPARE : ARENA ne controle
#: pas son usage GPU en interne, mais un export/rendu Drift tourne sur la
#: meme RTX A2000. Le mettre dans ce groupe evite qu'il ne se dispute la
#: carte graphique avec WanGP/vision/Xaar Kaname au meme instant.
CAPACITES_GPU_LOCAL = frozenset({"vision", "wangp", "xaar_kaname", "drift"})

#: Les statuts, dans les deux formes que porte le depot, qui disent qu'une
#: etape a fait ce qu'elle pouvait honnetement faire — produit un resultat,
#: ou soumis une ecriture pour confirmation. Jamais un echec, un refus ou
#: une capacite absente.
_STATUTS_FR_FAVORABLES = frozenset({"SUCCESS", "PARTIAL", "NEEDS_CONFIRMATION"})
_STATUTS_EN_FAVORABLES = frozenset({"success", "warning"})


def _depuis_resultat_action(resultat: Any) -> Dict[str, Any]:
    """Traduit un `ResultatAction` de connecteur dans la forme lue ici.

    **Sans cette traduction, un succes se lisait comme un echec.**
    `ResultatAction.to_dict()` rend `{"status": "SUCCESS"}` — la cle anglaise
    avec la valeur francaise. `_issue_favorable` lit alors la branche anglaise
    et cherche `"SUCCESS"` dans `{"success", "warning"}` : absent, donc
    defavorable, donc `_verifie` leve sur une etape parfaitement reussie
    (mesure du 03/09/2026).

    On rend donc la forme **francaise** : cle `statut`, qui porte les memes
    valeurs que le connecteur (`SUCCESS`, `NEEDS_CONFIRMATION`...). `preuve`
    voyage avec, car c'est elle que `_artefact_final` regarde pour savoir
    qu'un fichier existe vraiment.
    """
    corps = resultat.to_dict() if hasattr(resultat, "to_dict") else dict(resultat or {})
    #: `statut` d'abord : un connecteur qui rend deja la forme francaise la
    #: porte sous ce nom. `status` ensuite, car c'est ce que `to_dict()`
    #: fabrique — cle anglaise, valeur francaise. Lire `status` en premier
    #: rendrait `None` sur le premier cas, et `_verifie` leverait sur un
    #: succes.
    statut = corps.get("statut", corps.get("status"))
    traduit: Dict[str, Any] = {
        "statut": statut,
        "message": corps.get("message") or corps.get("response") or "",
    }
    preuve = corps.get("preuve", corps.get("output"))
    if preuve is not None:
        traduit["preuve"] = preuve
    return traduit


def _issue_favorable(resultat: Dict[str, Any]) -> Tuple[bool, str]:
    """Vrai si l'etape a reussi ou soumis une ecriture ; faux sinon.

    Deux formes de statut cohabitent dans le depot : `statut` (francais,
    rendu directement par `planifier_scene`/`fabriquer`) et `status`
    (anglais, rendu par tout agent qui passe par `BaseAgent.run()`).
    """
    if "statut" in resultat:
        return (resultat["statut"] in _STATUTS_FR_FAVORABLES,
                str(resultat.get("message") or ""))
    return (resultat.get("status") in _STATUTS_EN_FAVORABLES,
            str(resultat.get("response") or ""))


#: Extensions video reconnues pour reperer un export dans une reponse Drift
#: dont la forme exacte n'est pas verifiable sans son poste (mission
#: « Drift », machine de developpement sans Drift). Un chemin n'est JAMAIS
#: suppose : `_chemin_plausible` ne rend que ce qui existe reellement.
_EXTENSIONS_VIDEO = (".mp4", ".mov", ".mkv", ".webm")


def _chemin_plausible(valeur: Any, profondeur: int = 0) -> Optional[str]:
    """Cherche, dans une reponse JSON imbriquee, un chemin de fichier video
    qui existe REELLEMENT sur le disque — jamais un nom plausible seul.

    Necessaire pour Drift : `apply` peut porter un export dans sa reponse,
    mais sous une cle non figee par la documentation disponible ici. Une
    profondeur bornee (4) evite une recursion sans fin sur une reponse
    hostile ou circulaire.
    """
    if profondeur > 4:
        return None
    if isinstance(valeur, str):
        if valeur.lower().endswith(_EXTENSIONS_VIDEO) and Path(valeur).is_file():
            return valeur
        return None
    if isinstance(valeur, dict):
        for sous_valeur in valeur.values():
            trouve = _chemin_plausible(sous_valeur, profondeur + 1)
            if trouve:
                return trouve
    elif isinstance(valeur, list):
        for element in valeur:
            trouve = _chemin_plausible(element, profondeur + 1)
            if trouve:
                return trouve
    return None


class VideoProductionAgent(BaseAgent):
    """Compose vision, generation, voix et montage sur un projet Video.

    Les collaborateurs reels sont injectes plutot que construits ici : cet
    agent ne sait rien de comment WanGP, MoneyPrinterTurbo, VoiceStudio ou
    le montage fonctionnent en interne — seulement comment leur SOUMETTRE une
    etape et lire honnetement ce qu'ils ont repondu. Une capacite dont le
    collaborateur manque est refusee au moment de son execution
    (`NOT_CONFIGURED`, jamais simulee).
    """

    def __init__(
        self,
        provider: ModelProvider,
        memory: Optional[MemoryManager] = None,
        *,
        provider_vision: Optional[ModelProvider] = None,
        video_analyzer_agent: Any = None,
        audio_agent: Any = None,
        montage_agent: Any = None,
        registre: Any = None,
    ) -> None:
        super().__init__(
            name="VideoProductionAgent",
            description=("Orchestrateur Video : compose vision, generation, "
                         "voix et montage sur un projet, en parallele quand "
                         "les dependances le permettent."),
            provider=provider,
            memory=memory,
        )
        self.provider_vision = provider_vision
        self.video_analyzer_agent = video_analyzer_agent
        self.audio_agent = audio_agent
        self.montage_agent = montage_agent
        # Xaar Kaname est un CONNECTEUR, pas un agent : il passe par le
        # registre, donc par le controle d'acces et la file de confirmation.
        # C'est ce qui lui fait respecter `video_generation.generate =
        # CONFIRMATION` comme WanGP et MoneyPrinterTurbo.
        self.registre = registre

    async def run(self, objectif: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        contexte = context or {}
        references: List[str] = [r for r in (contexte.get("references") or []) if r]

        # Personnage (mission ARENA x AGENT HEROES, DEC-0084) : un identifiant
        # connu resout une identite persistante — ses images de reference
        # rejoignent les references ouvertes (pour qu'un xaar_kaname du plan
        # puisse les designer par index), et son profil visuel enrichit
        # SEULEMENT le prompt envoye au planificateur, jamais l'objectif
        # rapporte au proprietaire (`etat.objectif` reste ses mots a lui).
        personnage: Optional[Personnage] = None
        personnage_id = contexte.get("personnage_id")
        if personnage_id:
            personnage = charger_personnage(str(personnage_id))
            if personnage is None:
                return self._erreur(f"Personnage inconnu : {personnage_id}.")
            for image in personnage.images_reference:
                if image not in references:
                    references.append(image)

        capacites_choisies = contexte.get("capacites")  # mode TEAM : sous-ensemble explicite
        if capacites_choisies:
            capacites_autorisees = tuple(c for c in capacites_choisies if c in CAPACITES_VIDEO)
            inconnues = [c for c in capacites_choisies if c not in CAPACITES_VIDEO]
            if inconnues:
                return self._erreur(
                    f"Capacite(s) inconnue(s) demandee(s) : {', '.join(inconnues)}.")
            if not capacites_autorisees:
                return self._erreur("Aucune capacite valable dans la selection donnee.")
        else:
            capacites_autorisees = CAPACITES_VIDEO

        if not await self.provider.is_available():
            return {
                "status": "warning", "agent": self.name,
                "response": ("Je sais orchestrer un projet, mais le modele ne "
                            "repond pas. Demarre-le : je ne fabrique pas un "
                            "plan de projet sans lui."),
            }

        objectif_pour_planification = objectif
        if personnage is not None:
            ligne_personnage = f"Personnage : {personnage.nom}. {personnage.profil_visuel}".strip()
            if personnage.images_reference and personnage.images_reference[0] in references:
                index_visage = references.index(personnage.images_reference[0])
                ligne_personnage += f" Visage de reference : ref{index_visage}."
            if personnage.negatif:
                ligne_personnage += f" Eviter : {personnage.negatif}."
            objectif_pour_planification = f"{ligne_personnage}\n{objectif}"

        prompt = prompt_de_planification(objectif_pour_planification, references, capacites_autorisees)
        try:
            brut = await self.provider.generate(prompt=prompt)
        except Exception as erreur:  # httpx, timeout, modele absent
            logger.warning("Le modele n'a pas rendu de plan de projet : %s", erreur)
            return self._erreur(f"Je n'ai pas pu joindre le modele : {erreur}")

        try:
            graphe, refus = valider_graphe(extraire_json(brut), capacites_autorisees)
        except PlanRefuse as erreur:
            logger.info("Plan de projet Video refuse : %s", erreur)
            return self._erreur(f"Le plan de projet propose ne tient pas : {erreur}")

        return await self._executer(objectif, contexte, references, graphe, refus)

    async def generer_image_personnage(self, personnage_id: str, description_scene: str
                                       ) -> Dict[str, Any]:
        """Phase 1 du pipeline personnage : soumet une scene WanGP portant
        l'identite du personnage (`core/production/personnage_video.py`).

        Point d'entree direct, hors graphe : un plan a une seule etape ecrite
        d'avance n'a pas besoin du planificateur (le modele ne choisit rien
        ici) — la MEME soumission WanGP que le reste d'ARENA, jamais un
        second chemin.
        """
        personnage = charger_personnage(personnage_id)
        if personnage is None:
            return self._erreur(f"Personnage inconnu : {personnage_id}.")
        if self.video_analyzer_agent is None:
            return self._erreur("aucun agent video (WanGP) branche")
        return await personnage_video.soumettre_generation_image(
            self.video_analyzer_agent, personnage, description_scene)

    async def appliquer_identite_personnage(
        self, personnage_id: str, fichier_cible: str, *, many_faces: bool = False,
    ) -> Dict[str, Any]:
        """Phase 2 du pipeline personnage : repose le visage de reference du
        personnage sur un fichier DEJA produit (une generation confirmee et
        suivie jusqu'au fichier — `VideoAnalyzerAgent.suivre_la_generation`).

        Jamais appelable sur une tache encore en cours : `fichier_cible`
        doit deja exister, verifie par `personnage_video.appliquer_identite`.
        """
        personnage = charger_personnage(personnage_id)
        if personnage is None:
            return self._erreur(f"Personnage inconnu : {personnage_id}.")
        if self.registre is None:
            return self._erreur("aucun registre de connecteurs branche")
        resultat = await personnage_video.appliquer_identite(
            self.registre, personnage, fichier_cible, RENDERED_DIR, many_faces=many_faces)
        # Provenance : uniquement sur un succes MESURE (un fichier de sortie
        # que Xaar Kaname a reellement produit) — jamais sur une soumission,
        # jamais sur un echec. `enregistrer_generation` est append-only.
        if resultat.get("statut") == "SUCCESS" and resultat.get("preuve"):
            enregistrer_generation(
                personnage, "identite_video", str(resultat["preuve"]), "xaar_kaname")
        return resultat

    async def generer_image(
        self, prompt: str, *, negative_prompt: Optional[str] = None,
        width: Optional[int] = None, height: Optional[int] = None,
        seed: Optional[int] = None, variante: Optional[str] = None,
        backend: Optional[str] = None, workflow_id: Optional[str] = None,
        ckpt_name: Optional[str] = None, steps: Optional[int] = None,
        cfg: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Le point d'entree direct de la capacite image-generation
        canonique (mission ARENA x HIDREAM-I1 puis x COMFYUI, DEC-0085 et
        DEC-0087) — hors graphe, pour une demande d'image seule qui n'a pas
        besoin d'un plan de projet.

        Passe par le registre de connecteurs, jamais un deuxieme controle
        materiel ecrit ici : `core/connectors/hidream.py` et
        `core/connectors/comfyui.py` refusent deja NON_CONFIGURE si leur
        materiel ne tient pas la demande. `backend` choisit explicitement le
        moteur (« hidream » ou « comfyui ») ; sans lui, le comportement de
        DEC-0085 est INCHANGE (`hidream` en premier —
        `core/production/image_backend_router.py`).
        """
        if self.registre is None:
            return self._erreur("aucun registre de connecteurs branche")
        prompt = (prompt or "").strip()
        if not prompt:
            return self._erreur("Aucun prompt : rien a generer.")

        appel: Dict[str, Any] = {"prompt": prompt}
        for cle, valeur in (
            ("negative_prompt", negative_prompt), ("width", width), ("height", height),
            ("seed", seed), ("variante", variante), ("workflow_id", workflow_id),
            ("ckpt_name", ckpt_name), ("steps", steps), ("cfg", cfg),
        ):
            if valeur is not None:
                appel[cle] = valeur

        return await self._soumettre_image(appel, backend)

    async def _soumettre_image(
        self, appel: Dict[str, Any], backend_demande: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Le SEUL endroit qui choisit un moteur pour la capacite
        image-generation — `generer_image` et `_appeler_hidream_image`
        (l'etape de graphe) partagent ce chemin, jamais deux logiques
        distinctes (mission §5, no-duplication).

        Repli mission §39 : si le moteur choisi (ou par defaut) rend
        NOT_CONFIGURED et qu'aucun backend n'a ete demande explicitement,
        l'autre moteur connu est essaye UNE fois, seulement s'il est
        reellement declare dans le registre. Un backend demande
        explicitement n'a jamais de repli — un choix explicite est respecte,
        jamais devine a sa place.
        """
        backend = image_backend_router.backend_choisi(backend_demande)
        resultat = self.registre.executer(backend, "generer", **appel)
        if inspect.isawaitable(resultat):
            resultat = await resultat
        traduit = _depuis_resultat_action(resultat)
        traduit["moteur"] = backend

        if backend_demande is None and traduit.get("statut") == "NOT_CONFIGURED":
            secours = image_backend_router.backend_de_secours(backend)
            est_declare = getattr(self.registre, "est_declare", lambda _n: False)
            if secours and est_declare(secours):
                resultat_secours = self.registre.executer(secours, "generer", **appel)
                if inspect.isawaitable(resultat_secours):
                    resultat_secours = await resultat_secours
                traduit_secours = _depuis_resultat_action(resultat_secours)
                traduit_secours["moteur"] = secours
                if traduit_secours.get("statut") != "NOT_CONFIGURED":
                    return traduit_secours

        return traduit

    async def _executer(
        self, objectif: str, contexte: Dict[str, Any], references: List[str],
        graphe: List[EtapeProjet], refus: List[str],
    ) -> Dict[str, Any]:
        """Construit les etapes reelles et les fait tourner — la seule preuve
        qui vaille. Un graphe « valide » qui ne s'execute pas n'est pas un
        projet.
        """
        etat = EtatProjetVideo(
            objectif=objectif, contraintes=dict(contexte.get("contraintes") or {}),
            references=references, graphe=graphe,
        )

        etapes_coordination = [
            Etape(
                nom=etape.id, appel=self._adaptateur(etape, references),
                depend_de=etape.depend_de, facultative=etape.facultative,
                ressource=(RESSOURCE_GPU_LOCAL if etape.capacite in CAPACITES_GPU_LOCAL
                          else None),
            )
            for etape in graphe
        ]

        coordination = Coordination(f"video::{objectif[:60]}", etapes_coordination)
        resultat = await coordination.executer_parallele(
            parallelisme=int(contexte.get("parallelisme") or 4),
            limites_ressources={RESSOURCE_GPU_LOCAL: 1},
        )
        etat.resultat = resultat
        etat.artefact_final = self._artefact_final(resultat, graphe)

        return self._reponse(etat, refus)

    # --- Le graphe -> des appels reels -----------------------------------------

    def _adaptateur(self, etape: EtapeProjet, references: List[str]
                    ) -> Callable[[Dict[str, Any]], Any]:
        """L'appel reel pour une etape validee — jamais un texte libre du
        modele, toujours une capacite fermee vers un collaborateur injecte.
        """
        capacite, parametres = etape.capacite, etape.parametres

        async def appeler(acquis: Dict[str, Any]) -> Dict[str, Any]:
            if capacite == "vision":
                return await self._appeler_vision(parametres, references)
            if capacite == "transcription":
                return await self._appeler_transcription(parametres, references)
            if capacite == "wangp":
                return await self._appeler_wangp(parametres)
            if capacite == "moneyprinter":
                return await self._appeler_moneyprinter(parametres)
            if capacite == "narration":
                return await self._appeler_narration(parametres)
            if capacite == "montage":
                return await self._appeler_montage(parametres, references)
            if capacite == "xaar_kaname":
                return await self._appeler_xaar_kaname(parametres, references)
            if capacite == "krillin_subtitle":
                return await self._appeler_krillin(
                    "subtitle", references,
                    entree=self._reference(parametres, references),
                    langue_origine=parametres.get("langue_origine"),
                    langue_cible=parametres.get("langue_cible"),
                    caption_source=parametres.get("caption_source"))
            if capacite == "krillin_tts":
                return await self._appeler_krillin(
                    "tts", references, srt_cible=parametres.get("srt_cible"))
            if capacite == "krillin_render_horizontal":
                return await self._appeler_krillin(
                    "render_horizontal", references,
                    video=parametres.get("video"), sous_titres=parametres.get("sous_titres"))
            if capacite == "krillin_render_vertical":
                return await self._appeler_krillin(
                    "render_vertical", references,
                    video=parametres.get("video"), sous_titres=parametres.get("sous_titres"))
            if capacite == "krillin_cover":
                return await self._appeler_krillin(
                    "cover", references, prompt=parametres.get("prompt"))
            if capacite == "drift":
                return await self._appeler_drift(parametres, references)
            if capacite == "hidream_image":
                return await self._appeler_hidream_image(parametres)
            # valider_graphe() ne laisse jamais passer autre chose que
            # CAPACITES_VIDEO : atteindre ceci serait un bug de ce module,
            # jamais une entree du modele.
            raise RuntimeError(f"capacite non cablee : {capacite}")

        return appeler

    def _reference(self, parametres: Dict[str, Any], references: List[str]) -> Optional[str]:
        """Le chemin designe par INDEX dans la liste ouverte par l'appelant —
        jamais un chemin ecrit par le modele lui-meme dans son plan."""
        index = parametres.get("reference")
        if index is None and len(references) == 1:
            index = 0
        try:
            index = int(index)
        except (TypeError, ValueError):
            return None
        if 0 <= index < len(references) and Path(references[index]).is_file():
            return references[index]
        return None

    def _verifie(self, resultat: Dict[str, Any], capacite: str) -> Dict[str, Any]:
        favorable, message = _issue_favorable(resultat)
        if not favorable:
            raise RuntimeError(f"{capacite} : {message or 'echec sans message.'}")
        return resultat

    # --- Les six capacites, chacune vers son collaborateur reel ----------------

    async def _appeler_vision(self, parametres: Dict[str, Any],
                              references: List[str]) -> Dict[str, Any]:
        if self.provider_vision is None:
            raise RuntimeError("aucun modele de vision branche sur ce projet")
        chemin = self._reference(parametres, references)
        if chemin is None:
            raise RuntimeError("reference d'image introuvable ou absente")
        image_b64 = base64.b64encode(Path(chemin).read_bytes()).decode("ascii")
        question = str(parametres.get("question")
                       or "Decris cette reference en detail, en francais.")
        try:
            reponse = await self.provider_vision.generate(prompt=question, images=[image_b64])
        except Exception as erreur:  # noqa: BLE001 — un echec de vision est un etat, pas un crash
            raise RuntimeError(f"modele de vision : {erreur}") from erreur
        reponse = (reponse or "").strip()
        if not reponse:
            raise RuntimeError("le modele de vision n'a rien rendu")
        return {"statut": "SUCCESS", "message": reponse, "chemin": chemin}

    async def _appeler_transcription(self, parametres: Dict[str, Any],
                                     references: List[str]) -> Dict[str, Any]:
        if self.audio_agent is None:
            raise RuntimeError("aucun agent audio branche")
        chemin = self._reference(parametres, references)
        if chemin is None:
            raise RuntimeError("reference audio/video introuvable ou absente")
        resultat = await self.audio_agent.run(
            "transcris cette reference", context={"medias": [chemin]})
        return self._verifie(resultat, "transcription")

    async def _appeler_wangp(self, parametres: Dict[str, Any]) -> Dict[str, Any]:
        if self.video_analyzer_agent is None:
            raise RuntimeError("aucun agent video (WanGP) branche")
        description = str(parametres.get("description") or "").strip()
        if not description:
            raise RuntimeError("aucune description de scene fournie")
        resultat = self.video_analyzer_agent.planifier_scene(description)
        return self._verifie(resultat, "wangp")

    async def _appeler_moneyprinter(self, parametres: Dict[str, Any]) -> Dict[str, Any]:
        if self.video_analyzer_agent is None:
            raise RuntimeError("aucun agent video (MoneyPrinterTurbo) branche")
        sujet = str(parametres.get("sujet") or "").strip()
        if not sujet:
            raise RuntimeError("aucun sujet fourni")
        resultat = self.video_analyzer_agent.fabriquer(sujet)
        return self._verifie(resultat, "moneyprinter")

    async def _appeler_narration(self, parametres: Dict[str, Any]) -> Dict[str, Any]:
        """Voix off ou dialogue, selon ce que le plan declare.

        `conversationnel=True` (mission Sesame CSM, DEC-0080) fait passer la
        demande par `AudioAgent._dialogue` — le routeur choisit alors entre
        CSM et VoiceStudio lui-meme, jamais ce fichier. Par defaut,
        `conversationnel` est absent : le comportement d'avant cette mission
        ne change pas pour un plan qui ne le demande pas.
        """
        if self.audio_agent is None:
            raise RuntimeError("aucun agent audio branche")
        texte = str(parametres.get("texte") or "").strip()
        if not texte:
            raise RuntimeError("aucun texte de narration fourni")
        contexte: Dict[str, Any] = {
            "texte": texte, "langue": str(parametres.get("langue") or "fr")}
        if parametres.get("conversationnel"):
            contexte["conversationnel"] = True
            # CSM n'a qu'une vraie force : l'anglais. Un plan qui demande une
            # conversation sans preciser la langue en herite ici, pas dans le
            # routeur (meme defaut que `AudioAgent._dialogue`).
            contexte["langue"] = str(parametres.get("langue") or "en")
            if parametres.get("conversation"):
                contexte["conversation"] = parametres["conversation"]
            if "speaker" in parametres:
                contexte["speaker"] = parametres["speaker"]
        resultat = await self.audio_agent.run("narration", context=contexte)
        return self._verifie(resultat, "narration")

    def _reference_indexee(self, parametres: Dict[str, Any], cle: str,
                           references: List[str]) -> Optional[str]:
        """La reference designee par INDEX sous `cle`, jamais devinee.

        Volontairement plus strict que `_reference` : celui-la choisit la seule
        reference disponible quand l'index manque, ce qui est juste pour une
        capacite a une entree. Xaar en prend **deux** — le visage source et la
        cible — et les confondre poserait le mauvais visage sur la mauvaise
        image sans que rien ne le signale. Un index absent est donc refuse.
        """
        try:
            index = int(parametres.get(cle))
        except (TypeError, ValueError):
            return None
        if 0 <= index < len(references) and Path(references[index]).is_file():
            return references[index]
        return None

    async def _appeler_xaar_kaname(self, parametres: Dict[str, Any],
                                   references: List[str]) -> Dict[str, Any]:
        """Xaar Kaname (Deep-Live-Cam), par son connecteur — jamais en direct.

        Le connecteur porte l'action `generate` du service `video_generation`,
        que `config/permissions_services.yaml` met a `CONFIRMATION` : passer
        par le registre est ce qui fait respecter cette protection. Appeler le
        moteur directement d'ici la contournerait.

        La sortie est nommee par ARENA, dans `RENDERED_DIR` — jamais un chemin
        ecrit par le modele dans son plan, et au meme endroit que les autres
        rendus pour que le fichier soit servable par `/media/rendered/`.
        """
        if self.registre is None:
            raise RuntimeError("aucun registre de connecteurs branche")

        source = self._reference_indexee(parametres, "source_reference", references)
        cible = self._reference_indexee(parametres, "target_reference", references)
        if source is None:
            raise RuntimeError("source_reference : index d'image source absent ou invalide")
        if cible is None:
            raise RuntimeError("target_reference : index d'image cible absent ou invalide")

        sortie = RENDERED_DIR / f"xaar-{uuid.uuid4().hex[:8]}{Path(cible).suffix or '.jpg'}"

        # Chemins **absolus** : le moteur tourne dans son propre dossier, a
        # cote d'ARENA. Un chemin relatif y designerait un autre fichier, ou
        # aucun — et le connecteur lancerait le moteur sur du vide.
        resultat = self.registre.executer(
            "xaar_kaname", "traiter",
            source=str(Path(source).resolve()),
            target=str(Path(cible).resolve()),
            output=str(sortie),
            many_faces=bool(parametres.get("many_faces", False)),
        )
        # Le registre reel est synchrone ; un registre double peut etre
        # asynchrone. On attend ce qui est attendable plutot que de supposer
        # l'un des deux : sans cela la coroutine n'est jamais executee et le
        # resultat lu est l'objet coroutine lui-meme.
        if inspect.isawaitable(resultat):
            resultat = await resultat
        return self._verifie(_depuis_resultat_action(resultat), "xaar_kaname")

    async def _appeler_hidream_image(self, parametres: Dict[str, Any]) -> Dict[str, Any]:
        """HiDream-I1 (mission ARENA x HIDREAM-I1, DEC-0085), par son
        connecteur — jamais en direct.

        Meme raisonnement que `_appeler_xaar_kaname` : le connecteur porte
        `generate` du service `image_generation`, que `config/
        permissions_services.yaml` met a CONFIRMATION. Le connecteur refuse
        DEJA de soumettre si le materiel rapporte par le worker ne tient pas
        la variante demandee (`core/production/hidream_strategie.py`) — cette
        methode ne fait que transmettre, elle ne devine aucun defaut de
        resolution que le connecteur n'aurait pas deja.
        """
        if self.registre is None:
            raise RuntimeError("aucun registre de connecteurs branche")

        prompt = str(parametres.get("prompt") or "").strip()
        if not prompt:
            raise RuntimeError("prompt : aucune description d'image fournie")

        appel: Dict[str, Any] = {"prompt": prompt}
        for cle in ("negative_prompt", "width", "height", "seed", "variante", "steps", "guidance"):
            if parametres.get(cle) is not None:
                appel[cle] = parametres[cle]

        traduit = await self._soumettre_image(appel, parametres.get("backend"))
        return self._verifie(traduit, "hidream_image")

    async def _appeler_krillin(self, capacite_krillin: str, references: List[str],
                               **parametres_krillin: Any) -> Dict[str, Any]:
        """KrillinAI (DEC-0049), par son connecteur — jamais en direct.

        Meme raisonnement que `_appeler_xaar_kaname` : passer par le registre
        est ce qui fait respecter `krillinai.generate = CONFIRMATION`
        (`config/permissions_services.yaml`). `voice_clone_source` n'est
        jamais lu ici ni transmis plus loin — le connecteur lui-meme
        (`core/connectors/krillinai.py`) le refuse aussi, en profondeur.
        """
        if self.registre is None:
            raise RuntimeError("aucun registre de connecteurs branche")

        parametres_krillin.pop("voice_clone_source", None)
        parametres_krillin = {k: v for k, v in parametres_krillin.items() if v is not None}

        resultat = self.registre.executer("krillinai", capacite_krillin, **parametres_krillin)
        if inspect.isawaitable(resultat):
            resultat = await resultat
        return self._verifie(_depuis_resultat_action(resultat), f"krillin_{capacite_krillin}")

    async def _appeler_drift(self, parametres: Dict[str, Any],
                             references: List[str]) -> Dict[str, Any]:
        """Drift (DEC-0057), par son connecteur MCP — jamais en direct.

        Le modele ne pilote jamais Drift lui-meme : il propose un texte de
        demande ("coupe les silences", "ajoute une transition"), et c'est
        `core/production/plan_drift.py` qui traduit ce texte en operations
        VALIDEES contre le VRAI schema que Drift a annonce dans ce meme
        appel — jamais une liste d'operations devinee ou ecrite en dur ici.
        `appliquer` passe par le registre, comme xaar_kaname/krillin_* :
        c'est ce qui fait respecter `video_drift.apply = CONFIRMATION`.
        """
        if self.registre is None:
            raise RuntimeError("aucun registre de connecteurs branche")

        demande = str(parametres.get("demande") or "").strip()
        if not demande:
            raise RuntimeError("aucune demande de montage Drift fournie")

        indices = parametres.get("references") or []
        medias: List[str] = []
        for brut in indices:
            try:
                index = int(brut)
            except (TypeError, ValueError):
                continue
            if 0 <= index < len(references) and Path(references[index]).is_file():
                medias.append(references[index])
        inventaire = plan_drift.inventaire_depuis(medias)

        sonde = _depuis_resultat_action(await self._executer_drift("catalogue"))
        self._verifie(sonde, "drift")

        toolboxes_chargees: Dict[str, Any] = {}
        for toolbox in plan_drift.TOOLBOXES_FERMEES:
            resultat = await self._executer_drift("boite_a_outils", name=toolbox)
            corps = resultat.to_dict() if hasattr(resultat, "to_dict") else dict(resultat or {})
            statut = corps.get("statut", corps.get("status"))
            if statut in _STATUTS_FR_FAVORABLES or statut in _STATUTS_EN_FAVORABLES:
                toolboxes_chargees[toolbox] = (corps.get("detail") or {}).get("donnees") or {}

        prompt = plan_drift.prompt_de_planification(demande, toolboxes_chargees, inventaire)
        try:
            brut_reponse = await self.provider.generate(prompt=prompt)
        except Exception as erreur:  # noqa: BLE001 — un modele absent est un etat, pas un crash
            raise RuntimeError(f"drift : le modele n'a pas repondu ({erreur})") from erreur

        try:
            ops, refus = plan_drift.valider_operations(
                plan_drift.extraire_json(brut_reponse), toolboxes_chargees, inventaire)
        except plan_drift.PlanDriftRefuse as erreur:
            raise RuntimeError(f"drift : plan refuse ({erreur})") from erreur

        resultat = await self._executer_drift("appliquer", ops=ops)
        traduit = self._verifie(_depuis_resultat_action(resultat), "drift")
        # `_depuis_resultat_action` ne porte que statut/message/preuve —
        # `_artefact_final` a besoin de `donnees` pour retrouver un export
        # eventuel (le `preuve` de Drift n'est jamais un chemin, voir
        # `core/connectors/drift.py::_preuve`).
        corps = resultat.to_dict() if hasattr(resultat, "to_dict") else dict(resultat or {})
        traduit["donnees"] = (corps.get("detail") or {}).get("donnees")
        if refus:
            traduit["message"] = traduit.get("message", "") + "\nEcarte : " + " ".join(refus)
        return traduit

    async def _executer_drift(self, capacite: str, **parametres: Any) -> Any:
        """Un appel `registre.executer("drift", ...)`, synchrone ou pas —
        meme garde que `_appeler_xaar_kaname`/`_appeler_krillin`."""
        resultat = self.registre.executer("drift", capacite, **parametres)
        if inspect.isawaitable(resultat):
            resultat = await resultat
        return resultat

    async def _appeler_montage(self, parametres: Dict[str, Any],
                               references: List[str]) -> Dict[str, Any]:
        if self.montage_agent is None:
            raise RuntimeError("aucun agent de montage branche")
        # valider_graphe() garantit deja qu'aucune dependance d'ecriture
        # (wangp/moneyprinter/narration) n'atteint un montage : seules des
        # references d'entree, deja sur disque, sont montees ici.
        indices = parametres.get("references") or []
        medias: List[str] = []
        for brut in indices:
            try:
                index = int(brut)
            except (TypeError, ValueError):
                continue
            if 0 <= index < len(references):
                medias.append(references[index])
        if not medias:
            raise RuntimeError("aucune reference disponible pour le montage")
        demande = str(parametres.get("demande") or "assemble les references en un montage")
        resultat = await self.montage_agent.run(demande, context={"medias": medias})
        return self._verifie(resultat, "montage")

    # --- La reponse --------------------------------------------------------

    def _artefact_final(self, resultat: Any, graphe: List[EtapeProjet]) -> Optional[str]:
        """Le chemin d'un fichier qui existe reellement, produit par un
        montage reussi — jamais suppose. Une generation/narration seulement
        SOUMISE (`NEEDS_CONFIRMATION`) n'a pas encore de fichier reel."""
        for etape in reversed(graphe):
            if etape.capacite not in (
                "montage", "xaar_kaname", "krillin_render_horizontal", "krillin_render_vertical",
                "drift",
            ):
                continue
            trace = resultat.trace_de(etape.id)
            if trace is None or trace.resultat is None:
                continue
            sortie = trace.resultat
            if not isinstance(sortie, dict):
                continue
            chemin = sortie.get("preuve")
            if chemin and Path(str(chemin)).is_file():
                return str(chemin)
            # Drift : `preuve` n'est jamais un chemin (c'est un compte
            # d'operations, `core/connectors/drift.py::_preuve`) — un export
            # eventuel vit dans `donnees`, sous une cle non figee sans son
            # vrai serveur. `_chemin_plausible` ne rend un chemin QUE s'il
            # existe reellement sur le disque — jamais suppose.
            if etape.capacite == "drift":
                chemin_drift = _chemin_plausible(sortie.get("donnees"))
                if chemin_drift:
                    return chemin_drift
        return None

    def _reponse(self, etat: EtatProjetVideo, refus: List[str]) -> Dict[str, Any]:
        resultat = etat.resultat
        lignes = [resultat.rendre()] if resultat is not None else []
        if refus:
            lignes.append("Ecarte du plan :\n" + "\n".join(f"- {r}" for r in refus))
        if etat.artefact_final:
            lignes.append(f"Fichier final : {etat.artefact_final}")

        return {
            "status": "success" if (resultat is not None and resultat.aboutie) else "warning",
            "agent": self.name,
            "response": "\n\n".join(lignes) or "Rien n'a ete execute.",
            "projet": etat.to_dict(),
        }

    def _erreur(self, message: str) -> Dict[str, Any]:
        return {"status": "error", "agent": self.name, "response": message}
