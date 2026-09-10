"""Une compétence externe est une DONNÉE, jamais une instruction.

Mission ARENA × AUTOSKILLS. AutoSkills fait vérifier chaque compétence par un
modèle (`review.model: "gpt-5.4"`, `skills-registry/index.json`) avant de
l'approuver. **Reprendre le principe, jamais le mécanisme** : ARENA préfère
partout un contrôle déterministe à un jugement de modèle quand l'un peut
remplacer l'autre (`tools/video/prompt_audit.py`, `core/security/trust.py`
lui-même) — et un modèle qui juge un texte conçu pour tromper un modèle est
exactement le cas où cette préférence compte le plus.

**Rien de neuf pour l'injection de consigne** : `core/security/trust.py`
existe déjà, DEC-antérieure, et couvre neuf chemins d'entrée de texte
étranger. Le contenu d'une compétence (`SKILL.md`) en est un dixième — ce
module l'y fait simplement entrer, via `inspect()`, jamais une seconde liste
de motifs qui finirait par diverger de la première.

**Ce que ce module ajoute, et qui n'existe nulle part ailleurs** : les
compétences peuvent porter des extraits de commande shell (des blocs de
code dans leur Markdown), un vecteur que le texte "adressé à un modèle" de
`trust.py` ne couvre pas. `_MOTIFS_DESTRUCTEURS` couvre CE manque
spécifiquement — suppression récursive, script distant exécuté sans
lecture, exfiltration réseau explicite — jamais un doublon des motifs de
`trust.py`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List

from core.security.trust import inspect as inspecter_injection

#: Un vecteur que `core/security/trust.py` ne couvre pas : du CODE, pas du
#: texte adressé à un lecteur. Chaque motif nomme le risque qu'il révèle.
_MOTIFS_DESTRUCTEURS = (
    (r"\brm\s+-rf\s+/(?!\S)", "suppression récursive de la racine"),
    (r"\brm\s+-rf\s+~", "suppression récursive du répertoire personnel"),
    (r"(curl|wget)\s+[^\n|]*\|\s*(sh|bash|zsh)\b", "script distant exécuté sans lecture"),
    (r"\bchmod\s+777\b", "permissions ouvertes à tous"),
    (r"\b(nc|netcat)\s+-l\b", "écoute réseau ouverte depuis la compétence"),
    (r"curl\s+[^\n]*\s(-d|--data)\s[^\n]*\$\{?(HOME|USER|PATH|.*KEY.*|.*TOKEN.*|.*SECRET.*)",
     "exfiltration probable vers une requête réseau"),
    (r"\bcat\s+.*(\.ssh|\.env|id_rsa|credentials)\b.*\|\s*curl", "lecture de secret puis envoi réseau"),
)


class EtatConfiance(str, Enum):
    """Mission §13 : quatre états, jamais un simple booléen."""

    TRUSTED = "TRUSTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
    OUTDATED = "OUTDATED"


@dataclass
class Verdict:
    """Ce qui a été trouvé, jamais effacé — même discipline que
    `core.security.trust.inspect()` : un motif relevé reste dans le
    résultat, pour qu'un humain puisse le relire."""

    etat: EtatConfiance
    motifs_injection: List[str] = field(default_factory=list)
    motifs_destructeurs: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "etat": self.etat.value,
            "motifs_injection": self.motifs_injection,
            "motifs_destructeurs": self.motifs_destructeurs,
        }


def _motifs_destructeurs(contenu: str) -> List[str]:
    trouves = []
    for motif, nom in _MOTIFS_DESTRUCTEURS:
        if re.search(motif, contenu, flags=re.IGNORECASE):
            trouves.append(nom)
    return trouves


def evaluer(contenu: str) -> Verdict:
    """Le contenu d'une compétence, jugé UNIQUEMENT par des motifs
    déterministes — jamais par un modèle qui le lirait.

    - Un motif destructeur trouvé → `BLOCKED`, jamais rien de moins :
      une compétence qui peut supprimer un disque ou exfiltrer un secret
      n'a pas de version "à revoir".
    - Un motif d'injection trouvé (jamais destructeur) → `REVIEW_REQUIRED` :
      le motif peut être un faux positif (une doc qui explique la
      technique elle-même), donc un humain tranche, la compétence n'est
      pas rejetée d'office.
    - Rien trouvé → `TRUSTED`.
    """
    destructeurs = _motifs_destructeurs(contenu)
    injection = inspecter_injection(contenu)
    if destructeurs:
        etat = EtatConfiance.BLOCKED
    elif injection:
        etat = EtatConfiance.REVIEW_REQUIRED
    else:
        etat = EtatConfiance.TRUSTED
    return Verdict(etat=etat, motifs_injection=injection, motifs_destructeurs=destructeurs)
