"""L'etat d'un projet Video : ce qu'un objectif devient une fois decompose.

Trouve necessaire le 01/09/2026 (DEC-0037) : chaque capacite video (WanGP,
MoneyPrinterTurbo, montage, VoiceStudio, vision) existe deja et fonctionne
seule, mais rien ne portait un etat partage entre plusieurs d'entre elles
sur un meme projet — ni l'objectif, ni les references, ni le graphe
d'etapes, ni ce qui a reellement ete produit.

Ce module ne fait tourner aucune capacite : il decrit seulement la forme de
l'etat. `agents/video/production_agent.py` le remplit pour de vrai.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.execution.coordination import Resultat


@dataclass
class EtapeProjet:
    """Une etape du graphe de production, telle que VALIDEE — jamais telle
    que le modele l'a ecrite en clair. `capacite` vient toujours de la liste
    fermee de `core/production/plan_video.py` ; rien d'autre n'est execute.
    """

    id: str
    capacite: str
    parametres: Dict[str, Any] = field(default_factory=dict)
    depend_de: Tuple[str, ...] = ()
    facultative: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "capacite": self.capacite,
            "parametres": self.parametres, "depend_de": list(self.depend_de),
            "facultative": self.facultative,
        }


@dataclass
class EtatProjetVideo:
    """L'etat complet d'un projet Video, du besoin exprime au resultat mesure.

    `resultat` est celui rendu par `Coordination.executer_parallele()` —
    repris tel quel, jamais reecrit en un second format qui pourrait
    diverger de ce que l'executeur a reellement observe.

    `artefact_final` n'est jamais suppose : il n'est pose que sur un chemin
    de fichier qui existe reellement sur le disque, produit par une etape
    dont le statut mesure est un succes verifie — jamais une simple
    soumission en attente de confirmation.
    """

    objectif: str
    contraintes: Dict[str, Any] = field(default_factory=dict)
    references: List[str] = field(default_factory=list)
    graphe: List[EtapeProjet] = field(default_factory=list)
    resultat: Optional[Resultat] = None
    artefact_final: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "objectif": self.objectif,
            "contraintes": self.contraintes,
            "references": self.references,
            "graphe": [etape.to_dict() for etape in self.graphe],
            "resultat": self.resultat.to_dict() if self.resultat is not None else None,
            "artefact_final": self.artefact_final,
        }
