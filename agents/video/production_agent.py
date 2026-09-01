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
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.agent.base_agent import BaseAgent
from core.execution.coordination import Coordination, Etape
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider
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
CAPACITES_GPU_LOCAL = frozenset({"vision", "wangp"})

#: Les statuts, dans les deux formes que porte le depot, qui disent qu'une
#: etape a fait ce qu'elle pouvait honnetement faire — produit un resultat,
#: ou soumis une ecriture pour confirmation. Jamais un echec, un refus ou
#: une capacite absente.
_STATUTS_FR_FAVORABLES = frozenset({"SUCCESS", "PARTIAL", "NEEDS_CONFIRMATION"})
_STATUTS_EN_FAVORABLES = frozenset({"success", "warning"})


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

    async def run(self, objectif: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        contexte = context or {}
        references: List[str] = [r for r in (contexte.get("references") or []) if r]

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

        prompt = prompt_de_planification(objectif, references, capacites_autorisees)
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
        if self.audio_agent is None:
            raise RuntimeError("aucun agent audio branche")
        texte = str(parametres.get("texte") or "").strip()
        if not texte:
            raise RuntimeError("aucun texte de narration fourni")
        resultat = await self.audio_agent.run(
            "narration", context={"texte": texte, "langue": str(parametres.get("langue") or "fr")})
        return self._verifie(resultat, "narration")

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
            if etape.capacite != "montage":
                continue
            trace = resultat.trace_de(etape.id)
            if trace is None or trace.resultat is None:
                continue
            sortie = trace.resultat
            chemin = sortie.get("preuve") if isinstance(sortie, dict) else None
            if chemin and Path(str(chemin)).is_file():
                return str(chemin)
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
