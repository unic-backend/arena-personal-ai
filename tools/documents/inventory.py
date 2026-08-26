"""Inventaire des documents : ce qui est indexé, ce qui a changé, ce qui manque.

Indexer un document coûte du temps de carte graphique : chaque passage doit être
transformé en vecteur. Refaire ce travail sur un fichier qui n'a pas bougé, c'est
occuper le GPU pour rien.

L'inventaire répond à quatre questions, et à elles seules :

- quels documents sont **nouveaux** ;
- lesquels ont **changé** depuis leur indexation ;
- lesquels sont **inchangés** — ceux-là, on n'y touche pas ;
- lesquels ont **disparu** du dossier alors qu'ils sont dans l'index.

Un document disparu est signalé, jamais retiré en silence : l'index continuerait
sinon à répondre à partir d'un fichier que le propriétaire a supprimé.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from tools.documents.reader import EXTENSIONS_LISIBLES

logger = logging.getLogger("arena.tools.documents")

# Lu par blocs : une facture scannee peut peser plusieurs dizaines de Mo.
TAILLE_BLOC = 1024 * 1024


def empreinte(chemin: Path) -> str:
    """Empreinte du contenu. Deux fichiers identiques ont la même empreinte.

    C'est le contenu qui compte, pas la date de modification : recopier un
    fichier change sa date sans changer ce qu'il dit.
    """
    condensat = hashlib.sha256()
    with open(chemin, "rb") as fichier:
        while bloc := fichier.read(TAILLE_BLOC):
            condensat.update(bloc)
    return condensat.hexdigest()


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Plan:
    """Ce qu'il y a à faire, et ce qu'il n'y a surtout pas à refaire."""

    nouveaux: List[Path] = field(default_factory=list)
    modifies: List[Path] = field(default_factory=list)
    inchanges: List[Path] = field(default_factory=list)
    disparus: List[str] = field(default_factory=list)
    ignores: List[Path] = field(default_factory=list)

    @property
    def a_indexer(self) -> List[Path]:
        """Les seuls fichiers à traiter : nouveaux et modifiés."""
        return self.nouveaux + self.modifies

    @property
    def rien_a_faire(self) -> bool:
        return not self.a_indexer

    def resume(self) -> Dict[str, int]:
        return {
            "nouveaux": len(self.nouveaux),
            "modifies": len(self.modifies),
            "inchanges": len(self.inchanges),
            "disparus": len(self.disparus),
            "ignores": len(self.ignores),
        }

    def __str__(self) -> str:
        r = self.resume()
        return (
            f"{r['nouveaux']} nouveau(x), {r['modifies']} modifie(s), "
            f"{r['inchanges']} inchange(s), {r['disparus']} disparu(s), "
            f"{r['ignores']} ignore(s)"
        )


class Inventaire:
    """Journal de ce qui a été indexé, conservé à côté de l'index lui-même."""

    VERSION = 1

    def __init__(self, chemin: Path | str):
        self.chemin = Path(chemin)
        self.entrees: Dict[str, Dict[str, Any]] = {}
        self._charger()

    # --- Persistance ----------------------------------------------------------

    def _charger(self) -> None:
        if not self.chemin.exists():
            return
        try:
            donnees = json.loads(self.chemin.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            # Un inventaire illisible ne doit pas empecher d'indexer : on repart
            # de zero, en le disant. Le pire cas est de tout reindexer une fois.
            logger.warning(f"Inventaire illisible ({e}) : il est reconstruit de zero.")
            return
        if donnees.get("version") != self.VERSION:
            logger.warning("Inventaire d'une version differente : il est reconstruit.")
            return
        self.entrees = donnees.get("documents", {})

    def enregistrer_sur_disque(self) -> None:
        """Écrit l'inventaire. L'écriture passe par un fichier temporaire.

        Une interruption au mauvais moment laisserait sinon un inventaire tronqué,
        c'est-à-dire un index qui se croit à jour.
        """
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        temporaire = self.chemin.with_suffix(self.chemin.suffix + ".tmp")
        temporaire.write_text(
            json.dumps(
                {"version": self.VERSION, "mis_a_jour": _maintenant(), "documents": self.entrees},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        temporaire.replace(self.chemin)

    # --- Lecture --------------------------------------------------------------

    def connait(self, nom: str) -> bool:
        return nom in self.entrees

    def a_change(self, chemin: Path) -> bool:
        entree = self.entrees.get(chemin.name)
        return entree is None or entree.get("empreinte") != empreinte(chemin)

    # --- Ecriture -------------------------------------------------------------

    def noter_indexation(self, chemin: Path, passages: int, caracteres: int) -> None:
        """Note qu'un document vient d'être indexé, avec ce qu'il a produit."""
        self.entrees[chemin.name] = {
            "empreinte": empreinte(chemin),
            "indexe_le": _maintenant(),
            "passages": passages,
            "caracteres": caracteres,
            "octets": chemin.stat().st_size,
        }

    def oublier(self, nom: str) -> None:
        self.entrees.pop(nom, None)

    # --- Analyse --------------------------------------------------------------

    def analyser(self, dossier: Path | str) -> Plan:
        """Compare le contenu du dossier à ce qui est déjà indexé."""
        dossier = Path(dossier)
        plan = Plan()

        if not dossier.is_dir():
            logger.warning(f"Dossier de documents introuvable : {dossier}")
            plan.disparus = sorted(self.entrees)
            return plan

        vus = set()
        for chemin in sorted(dossier.rglob("*")):
            if not chemin.is_file() or chemin.name.startswith("."):
                continue
            if chemin.suffix.lower() not in EXTENSIONS_LISIBLES:
                plan.ignores.append(chemin)
                continue

            vus.add(chemin.name)
            if not self.connait(chemin.name):
                plan.nouveaux.append(chemin)
            elif self.a_change(chemin):
                plan.modifies.append(chemin)
            else:
                plan.inchanges.append(chemin)

        plan.disparus = sorted(nom for nom in self.entrees if nom not in vus)
        return plan
