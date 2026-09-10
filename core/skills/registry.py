"""Le registre CANONIQUE des compétences techniques d'ARENA.

Mission ARENA × AUTOSKILLS. Un seul registre, un seul format — jamais un
second `core/specialistes/` (qui reste ce qu'il est : une méthode par
MÉTIER, pas une connaissance par TECHNOLOGIE, voir `docs/audits/
autoskills_audit.md`).

**Provenance et intégrité, étudiées dans AutoSkills** (`skills-registry/
index.json` : `source`, `commitSha`, `sha256` par fichier, `bundleHash`)
**et adaptées, jamais copiées** — schéma JSON propre à ARENA, empreintes
calculées par ce module, jamais recopiées d'un registre tiers. Chaque
compétence de ce dépôt est un texte ORIGINAL, écrit pour ARENA
(`core/skills/store/<id>/SKILL.md`) : la question « quelle licence amont
s'applique ? » (mission §12) ne se pose donc pas ici — `source: "ARENA"`,
`licence: "ARENA (original)"`. Le format reste prêt pour une compétence
réellement empruntée un jour : `source`/`commit_amont`/`licence` existent
précisément pour ce cas, et une licence non-commerciale (AutoSkills lui-même
est CC-BY-NC-4.0, vérifié dans son `package.json`) resterait alors
`BLOCKED` avant même le contrôle de sécurité — voir `EtatCompetence.etat`.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.skills.securite import EtatConfiance, Verdict, evaluer

logger = logging.getLogger("usman.skills.registry")

#: Où vivent les compétences elles-mêmes — un dossier par compétence,
#: `skill.json` (métadonnées) + `SKILL.md` (contenu).
DOSSIER_REGISTRE = Path(__file__).resolve().parent / "store"

#: Licences dont la clause non-commerciale interdit l'usage direct dans ce
#: dépôt (UniC Plaquiste est une activité commerciale, DEC-0002 et
#: suivants) — mission §12, "VERIFY THIS AGAIN AT IMPLEMENTATION TIME".
#: Reconnues au préfixe : "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0"...
_PREFIXES_LICENCE_NON_COMMERCIALE = ("CC-BY-NC", "PROPRIETARY", "UNLICENSED")


@dataclass
class Competence:
    """Une compétence technique, avec sa provenance et son état mesuré.

    `contenu` n'est chargé qu'à la demande (`charger_contenu`) — un
    registre de plusieurs dizaines d'entrées ne doit pas garder tout leur
    texte en mémoire tant que rien ne les a sélectionnées (mission §7).
    """

    identifiant: str
    titre: str
    description: str
    technologies: Tuple[str, ...]
    mots_taches: Tuple[str, ...]
    source: str
    licence: str
    version: str
    commit_amont: Optional[str]
    chemin: Path

    def to_dict(self) -> Dict[str, object]:
        return {
            "identifiant": self.identifiant, "titre": self.titre,
            "technologies": list(self.technologies), "source": self.source,
            "licence": self.licence, "version": self.version,
        }


@dataclass
class EtatCompetence:
    """Ce qui a été mesuré pour une compétence — jamais affirmé sans
    preuve (`core/actions/resultat.py` : même discipline, aucun succès
    sans preuve)."""

    competence: Competence
    empreinte_actuelle: Optional[str]
    empreinte_enregistree: Optional[str]
    verdict_securite: Verdict

    @property
    def integrite_ok(self) -> bool:
        return (self.empreinte_actuelle is not None
                and self.empreinte_actuelle == self.empreinte_enregistree)

    @property
    def etat(self) -> EtatConfiance:
        """L'état final : la licence et l'intégrité priment sur la
        sécurité — une compétence altérée ou non-commerciale ne devient
        jamais TRUSTED, quel que soit son contenu."""
        if not _licence_utilisable(self.competence.licence):
            return EtatConfiance.BLOCKED
        if not self.integrite_ok:
            return EtatConfiance.OUTDATED
        return self.verdict_securite.etat


def _licence_utilisable(licence: str) -> bool:
    licence_normalisee = (licence or "").upper()
    return not any(licence_normalisee.startswith(p) for p in _PREFIXES_LICENCE_NON_COMMERCIALE)


def _empreinte(chemin: Path) -> Optional[str]:
    try:
        return hashlib.sha256(chemin.read_bytes()).hexdigest()
    except OSError:
        return None


def _charger_metadonnees(dossier: Path) -> Optional[Competence]:
    chemin_meta = dossier / "skill.json"
    try:
        donnees = json.loads(chemin_meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erreur:
        logger.warning("skill.json illisible sous %s : %s", dossier, erreur)
        return None
    champs_requis = ("titre", "description", "technologies", "source", "licence", "version")
    if any(champ not in donnees for champ in champs_requis):
        logger.warning("skill.json incomplet sous %s", dossier)
        return None
    return Competence(
        identifiant=dossier.name,
        titre=donnees["titre"],
        description=donnees["description"],
        technologies=tuple(donnees["technologies"]),
        mots_taches=tuple(donnees.get("mots_taches", ())),
        source=donnees["source"],
        licence=donnees["licence"],
        version=donnees["version"],
        commit_amont=donnees.get("commit_amont"),
        chemin=dossier,
    )


def charger_registre(dossier: Path = DOSSIER_REGISTRE) -> List[Competence]:
    """Toutes les compétences valides du registre — un dossier illisible ou
    incomplet est ignoré et journalisé, jamais une exception qui arrêterait
    la lecture des autres."""
    if not dossier.is_dir():
        return []
    competences = []
    for sous_dossier in sorted(dossier.iterdir()):
        if not sous_dossier.is_dir():
            continue
        competence = _charger_metadonnees(sous_dossier)
        if competence is not None:
            competences.append(competence)
    return competences


def charger_contenu(competence: Competence) -> Optional[str]:
    chemin_skill_md = competence.chemin / "SKILL.md"
    try:
        return chemin_skill_md.read_text(encoding="utf-8")
    except OSError:
        return None


def evaluer_competence(competence: Competence) -> EtatCompetence:
    """Mesure l'intégrité (empreinte SKILL.md vs `skill.json`) et la
    sécurité (contenu réel, jamais le nom du fichier) — jamais l'une sans
    l'autre : une compétence altérée n'est jamais scannée comme si elle
    était intacte."""
    chemin_skill_md = competence.chemin / "SKILL.md"
    actuelle = _empreinte(chemin_skill_md)

    chemin_meta = competence.chemin / "skill.json"
    try:
        donnees = json.loads(chemin_meta.read_text(encoding="utf-8"))
        enregistree = donnees.get("sha256_skill_md")
    except (OSError, json.JSONDecodeError):
        enregistree = None

    contenu = charger_contenu(competence) or ""
    verdict = evaluer(contenu)

    return EtatCompetence(competence=competence, empreinte_actuelle=actuelle,
                          empreinte_enregistree=enregistree, verdict_securite=verdict)
