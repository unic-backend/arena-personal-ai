"""La forme que rend toute analyse financiere — schema fixe, provenance
obligatoire.

Audit AutoHedge : son README annonce une « Structured Output » en JSON, mais
`workers.py` declare `output_type="str"` sur le Quant Agent, le Risk Agent et
l'Execution Agent — du texte libre, jamais verifie contre un schema. Ce module
rend la structure reelle : un dataclass, un seul `to_dict()`, les memes cles a
chaque appel.

Les cles du dictionnaire final sont en anglais — c'est la forme demandee par
la mission (section 9) pour qu'un systeme en aval (API, tableau de bord)
puisse la consommer sans traduire. Le code qui la construit reste en francais,
comme partout ailleurs dans ARENA.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class AnalyseFinanciere:
    """Une analyse complete d'un actif — jamais une recommandation d'agir,
    toujours une lecture des faits mesures plus une interpretation qui se
    dit incertaine quand elle l'est."""

    actif: str
    etat_marche: str  # "DONNEES_DISPONIBLES" | "DONNEES_PARTIELLES" | "DONNEES_INDISPONIBLES"
    tendance: str
    analyse_quant: Dict[str, Any]
    analyse_risque: Dict[str, Any]
    preuves_marche: List[Dict[str, str]] = field(default_factory=list)
    confiance: str = "FAIBLE"  # "FAIBLE" | "MOYENNE" | "ELEVEE" — jamais un chiffre invente
    limites: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    interpretation: Optional[str] = None  # la seule partie ecrite par le modele
    horodatage: str = field(default_factory=_maintenant)

    def to_dict(self) -> Dict[str, Any]:
        """La forme demandee par la mission (§9) : cles anglaises, schema fixe."""
        return {
            "asset": self.actif,
            "timestamp": self.horodatage,
            "market_state": self.etat_marche,
            "trend": self.tendance,
            "quant_analysis": self.analyse_quant,
            "risk_analysis": self.analyse_risque,
            "market_evidence": self.preuves_marche,
            "confidence": self.confiance,
            "limitations": self.limites,
            "sources": self.sources,
            "interpretation": self.interpretation,
        }
