"""Traduire ce que SiteGuard détecte sur une photo de chantier en un rapport
de risque en français — jamais une certitude.

Contexte (mission BIM/métré/sécurité chantier, 05/09/2026, section 6) : « la
détection visuelle doit rester une détection. Ne prétends jamais qu'un
modèle visuel est infaillible. Les résultats doivent être présentés comme
des observations probabilistes lorsque nécessaire. » Ce module ne recalcule
aucune logique de risque — SiteGuard la calcule déjà côté serveur (ses
propres règles, `RISK_RULES`) ; il ne fait que traduire son JSON en phrases
françaises fidèles, avec le rappel de prudence toujours présent.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List

#: Les niveaux que SiteGuard rend ("high"/"medium"), traduits — jamais un
#: niveau inventé pour une valeur inconnue : elle reste affichée telle quelle.
NIVEAU_FR = {"high": "élevé", "medium": "moyen", "low": "faible"}

RAPPEL_PRUDENCE = (
    "Détection visuelle automatique : une observation probabiliste, jamais "
    "une certitude — un modèle de vision peut manquer un élément ou se "
    "tromper. Vérifie sur place avant toute décision."
)


@dataclass(frozen=True)
class Detection:
    """Un objet détecté sur l'image, tel que SiteGuard le rend."""

    classe: str
    confiance: float
    boite: List[float] = field(default_factory=list)


@dataclass(frozen=True)
class Risque:
    """Un risque signalé par SiteGuard — calculé par lui, jamais recalculé ici."""

    type: str
    niveau: str
    message: str
    compte: int


@dataclass
class RapportSecurite:
    """Le rapport complet, traduit — prêt à afficher sans reregarder l'image."""

    image: str
    detections: List[Detection] = field(default_factory=list)
    risques: List[Risque] = field(default_factory=list)

    @property
    def personnes(self) -> int:
        return sum(1 for d in self.detections if d.classe.lower() in ("person", "persons"))


def depuis_detection(image: str, detail: Dict[str, Any]) -> RapportSecurite:
    """Traduit le JSON rendu par `POST /api/v1/detection/image` de SiteGuard."""
    detections = [
        Detection(
            classe=str(d.get("class") or ""),
            confiance=float(d.get("confidence") or 0.0),
            boite=[float(v) for v in (d.get("bbox") or [])],
        )
        for d in (detail.get("detections") or [])
    ]
    risques = [
        Risque(
            type=str(r.get("type") or ""),
            niveau=str(r.get("level") or ""),
            message=str(r.get("message") or ""),
            compte=int(r.get("count") or 0),
        )
        for r in (detail.get("risks") or [])
    ]
    return RapportSecurite(image=image, detections=detections, risques=risques)


def formater(rapport: RapportSecurite) -> str:
    """Un compte-rendu en français, jamais une certitude (mission §6)."""
    if not rapport.detections:
        lignes = [
            f"Aucun élément reconnu par le modèle sur {rapport.image} : ni "
            "personne, ni équipement de sécurité détecté.",
        ]
    else:
        lignes = [f"{rapport.personnes} personne(s) détectée(s) sur {rapport.image}."]
        if not rapport.risques:
            lignes.append("Aucun risque signalé par le modèle sur cette image.")
        else:
            for risque in rapport.risques:
                niveau = NIVEAU_FR.get(risque.niveau, risque.niveau or "inconnu")
                lignes.append(
                    f"{risque.message} Risque : {niveau} ({risque.compte} occurrence(s)).")
    lignes.append(RAPPEL_PRUDENCE)
    return "\n".join(lignes)
