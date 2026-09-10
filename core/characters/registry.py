"""Le registre des personnages ARENA — identite persistante, reutilisable.

Mission ARENA x AGENT HEROES (DEC-0084). Meme architecture que
`core/skills/registry.py` (un dossier par entree, un fichier JSON de
metadonnees, jamais une exception qui arrete la lecture des autres) —
**reprise, jamais dupliquee**, parce qu'ARENA a deja ce format pour des
entrees structurees, versionnees, avec provenance (mission §5 : « ne pas
implementer betement le schema suggere si ARENA a deja une meilleure
representation »).

**Ce qui differe deliberement du schema skills, et pourquoi :**

- Pas de `source`/`licence` amont : un personnage est cree par le
  proprietaire, il n'est jamais importe d'un depot tiers. Un champ licence
  vide serait trompeur plutot qu'absent.
- `historique` remplace la simple empreinte d'integrite des competences :
  un personnage change (nouvelles generations), une competence non — la
  provenance d'un personnage est une suite d'evenements, pas un hash unique.

**Ce que ce module NE fait PAS** (mission §6) : il ne pretend aucune
coherence visuelle par construction. `profil_visuel` est un texte compose
dans les prompts de generation (`core/production/personnage_video.py`) —
une conditionnement par IMAGE/seed/embedding n'existe nulle part dans ARENA
aujourd'hui (`core/connectors/wan2gp.py` n'accepte qu'un `source` texte).
Ce module stocke une IDENTITE, pas une garantie de ressemblance.

**Ou vivent les fichiers.** Les metadonnees (`personnage.json`) vivent sous
`data/personnages/<id>/` — donnees d'execution, jamais versionnees (comme
`data/database/memory.db`), a la difference du `core/skills/store/` qui
contient du contenu ORIGINAL ecrit pour le depot. Les images de reference
elles-memes ne sont JAMAIS copiees ici : `images_reference` ne porte que des
CHEMINS deja dans `MEDIA_DIR`, verifies par l'appelant (meme discipline que
`apps/backend/routers/video_production.py:_reference_sure`) — dupliquer un
binaire dans un second stockage est exactement ce que la mission §21-22
interdit.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("usman.characters.registry")

#: Racine du depot, calculee sans dependre d'`apps.backend` — meme
#: discipline d'autonomie que `core/skills/registry.py`.
_RACINE_DEPOT = Path(__file__).resolve().parents[2]

#: Reglable par environnement (tests, deploiement) ; par defaut hors de
#: l'arbre source, au meme niveau que `data/database/`.
DOSSIER_PERSONNAGES = Path(
    os.getenv("USMAN_PERSONNAGES_DIR") or _RACINE_DEPOT / "data" / "personnages"
)

#: Moteurs de generation reellement branches sur ARENA aujourd'hui
#: (`core/production/disponibilite.py:PAR_CONNECTEUR`). Un personnage ne
#: peut pas declarer un moteur qu'ARENA ne sait pas interroger — mission §8 :
#: ARENA reste independante des fournisseurs, mais ne pretend jamais qu'un
#: fournisseur non cable existe.
MOTEURS_CONNUS: Tuple[str, ...] = ("wangp",)


@dataclass
class Personnage:
    """Une identite de personnage, avec sa provenance mesuree.

    Champs repris de la mission §5, restreints a ce qu'ARENA sait
    reellement exploiter aujourd'hui : pas de champ LoRA/adaptateur tant
    qu'aucun entrainement n'est cable (mission §7 — etudie, non reproduit).
    """

    identifiant: str
    nom: str
    description: str
    images_reference: Tuple[str, ...]
    profil_visuel: str
    negatif: str = ""
    moteur_generation: str = "wangp"
    profil_voix: Optional[str] = None
    cree_le: str = ""
    version: int = 1
    historique: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identifiant": self.identifiant,
            "nom": self.nom,
            "description": self.description,
            "images_reference": list(self.images_reference),
            "profil_visuel": self.profil_visuel,
            "negatif": self.negatif,
            "moteur_generation": self.moteur_generation,
            "profil_voix": self.profil_voix,
            "cree_le": self.cree_le,
            "version": self.version,
            "historique": list(self.historique),
        }


def _dossier(identifiant: str, dossier: Path) -> Path:
    return dossier / identifiant


def _chemin_meta(identifiant: str, dossier: Path) -> Path:
    return _dossier(identifiant, dossier) / "personnage.json"


def _depuis_donnees(identifiant: str, donnees: Dict[str, Any]) -> Optional[Personnage]:
    champs_requis = ("nom", "description", "images_reference", "profil_visuel")
    if any(champ not in donnees for champ in champs_requis):
        logger.warning("personnage.json incomplet pour %s", identifiant)
        return None
    return Personnage(
        identifiant=identifiant,
        nom=donnees["nom"],
        description=donnees["description"],
        images_reference=tuple(donnees["images_reference"]),
        profil_visuel=donnees["profil_visuel"],
        negatif=donnees.get("negatif", ""),
        moteur_generation=donnees.get("moteur_generation", "wangp"),
        profil_voix=donnees.get("profil_voix"),
        cree_le=donnees.get("cree_le", ""),
        version=int(donnees.get("version", 1)),
        historique=tuple(donnees.get("historique", ())),
    )


def charger_personnage(identifiant: str, dossier: Path = DOSSIER_PERSONNAGES
                       ) -> Optional[Personnage]:
    """Un personnage par son identifiant, ou `None` — jamais une exception
    pour un identifiant absent ou un fichier illisible."""
    chemin = _chemin_meta(identifiant, dossier)
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erreur:
        logger.warning("personnage.json illisible pour %s : %s", identifiant, erreur)
        return None
    return _depuis_donnees(identifiant, donnees)


def charger_registre(dossier: Path = DOSSIER_PERSONNAGES) -> List[Personnage]:
    """Tous les personnages valides — un dossier illisible ou incomplet est
    ignore et journalise, jamais une exception qui arreterait la lecture des
    autres (meme discipline que `core/skills/registry.py:charger_registre`)."""
    if not dossier.is_dir():
        return []
    personnages: List[Personnage] = []
    for sous_dossier in sorted(dossier.iterdir()):
        if not sous_dossier.is_dir():
            continue
        personnage = charger_personnage(sous_dossier.name, dossier)
        if personnage is not None:
            personnages.append(personnage)
    return personnages


def _ecrire(personnage: Personnage, dossier: Path) -> None:
    chemin = _chemin_meta(personnage.identifiant, dossier)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(personnage.to_dict(), ensure_ascii=False, indent=2),
                      encoding="utf-8")


def creer_personnage(
    nom: str,
    description: str,
    images_reference: List[str],
    profil_visuel: str,
    *,
    negatif: str = "",
    moteur_generation: str = "wangp",
    profil_voix: Optional[str] = None,
    dossier: Path = DOSSIER_PERSONNAGES,
) -> Personnage:
    """Enregistre un nouveau personnage. **Ne copie aucune image** : les
    chemins sont pris tels quels — a l'appelant de garantir qu'ils vivent
    deja dans `MEDIA_DIR` (verification faite a la frontiere API, comme pour
    toute autre reference video, jamais ici : ce module ne connait pas
    `MEDIA_DIR`, seulement le stockage des personnages).

    Refuse un nom vide ou un moteur non cable (`MOTEURS_CONNUS`) : un
    personnage qui declare un moteur qu'ARENA ne sait pas interroger
    tromperait toute capacite qui le consulte plus tard.
    """
    if not nom.strip():
        raise ValueError("un personnage a besoin d'un nom.")
    if moteur_generation not in MOTEURS_CONNUS:
        raise ValueError(
            f"moteur_generation inconnu : {moteur_generation!r} "
            f"(connus : {', '.join(MOTEURS_CONNUS)}).")

    identifiant = f"{_slug(nom)}-{uuid.uuid4().hex[:8]}"
    personnage = Personnage(
        identifiant=identifiant,
        nom=nom,
        description=description,
        images_reference=tuple(images_reference),
        profil_visuel=profil_visuel,
        negatif=negatif,
        moteur_generation=moteur_generation,
        profil_voix=profil_voix,
        cree_le=datetime.now(timezone.utc).isoformat(),
        version=1,
        historique=(),
    )
    _ecrire(personnage, dossier)
    logger.info("Personnage cree : %s (%s)", identifiant, nom)
    return personnage


def enregistrer_generation(
    personnage: Personnage,
    type_generation: str,
    fichier: str,
    moteur: str,
    *,
    note: str = "",
    dossier: Path = DOSSIER_PERSONNAGES,
) -> Personnage:
    """Ajoute une generation a l'historique — la provenance que la mission
    §5 demande (« creation history »). Append-only : une entree passee ne se
    modifie jamais, meme si le fichier qu'elle nomme disparait plus tard."""
    entree = {
        "date": datetime.now(timezone.utc).isoformat(),
        "type": type_generation,
        "fichier": fichier,
        "moteur": moteur,
        "note": note,
    }
    mis_a_jour = Personnage(
        identifiant=personnage.identifiant,
        nom=personnage.nom,
        description=personnage.description,
        images_reference=personnage.images_reference,
        profil_visuel=personnage.profil_visuel,
        negatif=personnage.negatif,
        moteur_generation=personnage.moteur_generation,
        profil_voix=personnage.profil_voix,
        cree_le=personnage.cree_le,
        version=personnage.version,
        historique=personnage.historique + (entree,),
    )
    _ecrire(mis_a_jour, dossier)
    return mis_a_jour


def _slug(texte: str) -> str:
    """Un identifiant lisible, jamais le seul UUID — `personnage-3a...`
    dit plus a un humain qui relit `data/personnages/` que `3a...` seul."""
    garde = "".join(c.lower() if c.isalnum() else "-" for c in texte.strip())
    while "--" in garde:
        garde = garde.replace("--", "-")
    garde = garde.strip("-")
    return garde or "personnage"
