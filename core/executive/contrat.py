"""Le contrat structure qu'un role d'Executive Intelligence doit rendre.

Mission ARENA x OPENEXECUTIVE (§29) : chaque specialiste rend la MEME forme,
quel que soit le domaine — jamais un second schema par role. `to_dict()` suit
la meme convention que `core/finance/structured_output.py::AnalyseFinanciere`
(deja etablie dans ARENA pour l'agent Finance) : cles anglaises, un dataclass
gele, un seul point de conversion.

**Position, pas moyenne (§8).** Chaque specialiste conclut une `Position`
deterministe a partir de ce qu'il a lui-meme calcule ou trouve — jamais un
sentiment du modele. C'est ce qui permet a la synthese de DETECTER un
desaccord structurellement (deux positions opposees), plutot que d'esperer
que le modele de synthese le remarque tout seul.

**Evidence avant opinion (§9).** `preuves` porte des faits VERIFIABLES
(nombre calcule, extrait de document, resultat de recherche) ; `hypotheses`
porte ce qui a ete suppose faute de donnee. Un chiffre qui n'a pas de preuve
associee reste une hypothese, jamais un fait tacite.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Position(str, Enum):
    """Ce qu'un specialiste conclut, en un mot — jamais devine par la
    synthese : chaque role la fixe lui-meme, a partir de ce qu'il a calcule."""

    FAVORABLE = "FAVORABLE"
    DEFAVORABLE = "UNFAVORABLE"
    CONDITIONNEL = "CONDITIONAL"  # favorable sous condition(s) explicite(s)
    NEUTRE = "NEUTRAL"  # analyse fournie, mais aucune position de gestion à prendre
    INDISPONIBLE = "UNAVAILABLE"  # le specialiste n'a pas pu repondre (§28)


class NatureDuPoint(str, Enum):
    """Distingue ce qu'un point EST, avant que la synthese ne l'utilise
    (mission §9) : jamais une hypothese presentee comme un fait."""

    FAIT = "FACT"  # mesure ou fourni par le proprietaire/document
    CALCUL = "CALCULATION"  # deterministe, reproductible depuis des faits
    INFERENCE = "INFERENCE"  # deduit, verifiable en relisant le raisonnement
    HYPOTHESE = "ASSUMPTION"  # suppose faute de donnee — doit etre nomme comme tel
    INCONNU = "UNKNOWN"  # l'information manque, et ce n'est pas devine


@dataclass(frozen=True)
class PointDeSynthese:
    """Un point atomique que le specialiste ou la synthese avance, avec sa
    nature — c'est ce qui permet au rapport final de les distinguer (§9/§10)."""

    texte: str
    nature: NatureDuPoint

    def to_dict(self) -> Dict[str, Any]:
        return {"text": self.texte, "nature": self.nature.value}


@dataclass(frozen=True)
class AnalyseSpecialiste:
    """Ce qu'un role rend a l'Executive Intelligence — le contrat de §29.

    Attributes:
        role: identifiant stable (ex. "finance", "risque", "operations").
        domaine: le libelle humain du role.
        position: la conclusion deterministe du role (`Position`).
        constats: ce que le role a trouve, chacun avec sa nature (§9).
        preuves: les faits/calculs verifiables qui soutiennent l'analyse —
            jamais un texte d'opinion seul.
        hypotheses: ce qui a ete suppose faute de donnee reelle.
        risques: les risques identifies par CE role, en texte.
        confiance: "FAIBLE" | "MOYENNE" | "ELEVEE" — jamais un chiffre invente.
        actions_recommandees: des RECOMMANDATIONS seulement — jamais une
            autorisation (mission §23) ; l'execution reste soumise au systeme
            de permission d'ARENA.
        inconnues: ce qui manquerait pour conclure plus surement.
        erreur: rempli seulement si le role a echoue (§28) — la synthese
            doit alors continuer avec ce qui reste, pas s'arreter.
    """

    role: str
    domaine: str
    position: Position
    constats: List[PointDeSynthese] = field(default_factory=list)
    preuves: List[str] = field(default_factory=list)
    hypotheses: List[str] = field(default_factory=list)
    risques: List[str] = field(default_factory=list)
    confiance: str = "FAIBLE"
    actions_recommandees: List[str] = field(default_factory=list)
    inconnues: List[str] = field(default_factory=list)
    erreur: Optional[str] = None
    horodatage: str = field(default_factory=_maintenant)

    @property
    def disponible(self) -> bool:
        return self.erreur is None and self.position != Position.INDISPONIBLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "domain": self.domaine,
            "position": self.position.value,
            "findings": [c.to_dict() for c in self.constats],
            "evidence": list(self.preuves),
            "assumptions": list(self.hypotheses),
            "risks": list(self.risques),
            "confidence": self.confiance,
            "recommended_actions": list(self.actions_recommandees),
            "unknowns": list(self.inconnues),
            "error": self.erreur,
            "timestamp": self.horodatage,
        }


@dataclass(frozen=True)
class Desaccord:
    """Un desaccord REEL entre deux roles, jamais moyenne (§8/§30)."""

    role_a: str
    position_a: Position
    role_b: str
    position_b: Position
    remarque: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_a": self.role_a, "position_a": self.position_a.value,
            "role_b": self.role_b, "position_b": self.position_b.value,
            "note": self.remarque,
        }


@dataclass(frozen=True)
class DecisionExecutive:
    """La sortie finale — la profondeur du format s'adapte a la question
    (§10) : `simple` reste une reponse courte, jamais le gabarit complet."""

    question: str
    simple: bool
    reponse: str
    recommandation: Optional[str] = None
    pourquoi: Optional[str] = None
    preuves_cles: List[str] = field(default_factory=list)
    impact_financier: Optional[str] = None
    impact_operationnel: Optional[str] = None
    risques: List[str] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)
    hypotheses: List[str] = field(default_factory=list)
    informations_manquantes: List[str] = field(default_factory=list)
    confiance: str = "FAIBLE"
    prochaines_actions: List[str] = field(default_factory=list)
    roles_consultes: List[str] = field(default_factory=list)
    desaccords: List[Desaccord] = field(default_factory=list)
    analyses: List[AnalyseSpecialiste] = field(default_factory=list)
    verification: Optional[str] = None
    horodatage: str = field(default_factory=_maintenant)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "simple": self.simple,
            "response": self.reponse,
            "recommendation": self.recommandation,
            "why": self.pourquoi,
            "key_evidence": list(self.preuves_cles),
            "financial_impact": self.impact_financier,
            "operational_impact": self.impact_operationnel,
            "risks": list(self.risques),
            "alternatives": list(self.alternatives),
            "assumptions": list(self.hypotheses),
            "missing_information": list(self.informations_manquantes),
            "confidence": self.confiance,
            "next_actions": list(self.prochaines_actions),
            "specialists_consulted": list(self.roles_consultes),
            "disagreements": [d.to_dict() for d in self.desaccords],
            "specialist_analyses": [a.to_dict() for a in self.analyses],
            "verification": self.verification,
            "timestamp": self.horodatage,
        }
