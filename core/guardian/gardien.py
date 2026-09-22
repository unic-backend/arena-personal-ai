"""Le gardien : découvrir, enregistrer, vérifier les disparitions et rapporter.

Un constat n'est résolu que si la sonde responsable de sa catégorie a réellement
abouti. Une panne de pytest/Ruff ne peut donc plus transformer silencieusement un
problème connu en faux « résolu ».
"""
import logging
from dataclasses import dataclass
from typing import Dict, List, Set

from core.guardian.diagnostics import (
    CATEGORIE_DIAGNOSTIC,
    Executeur,
    diagnostiquer_tout,
    executer_reel,
)
from core.guardian.file_maintenance import FileDeMaintenance, Tache

logger = logging.getLogger("usman.guardian.gardien")

TACHES_DETAILLEES = 10


@dataclass(frozen=True)
class RapportSante:
    """Rapport du dernier cycle, fondé uniquement sur des diagnostics exécutés."""

    nouvelles: int
    revues: int
    resolues: int
    ouvertes_par_categorie: Dict[str, int]
    taches_ouvertes: List[Tache]

    @property
    def total_ouvertes(self) -> int:
        return sum(self.ouvertes_par_categorie.values())

    def rendre(self) -> str:
        lignes = [
            "ETAT D'ARENA — GARDIEN",
            f"Ce cycle : {self.nouvelles} nouveau(x), {self.revues} deja connu(s), "
            f"{self.resolues} resolu(s).",
            "",
        ]
        if not self.taches_ouvertes:
            lignes.append("Aucune tache ouverte.")
            return "\n".join(lignes)

        for categorie, nombre in sorted(self.ouvertes_par_categorie.items()):
            lignes.append(f"{categorie:<14} {nombre} ouverte(s)")
        lignes.append("")
        lignes.append(
            f"Les {min(TACHES_DETAILLEES, len(self.taches_ouvertes))} plus urgentes "
            f"(sur {self.total_ouvertes}) :"
        )
        for tache in self.taches_ouvertes[:TACHES_DETAILLEES]:
            lignes.append(
                f"- [{tache.gravite}] {tache.categorie} — "
                f"{tache.description} ({tache.fichier})"
            )
        return "\n".join(lignes)

    def to_dict(self) -> dict:
        return {
            "nouvelles": self.nouvelles,
            "revues": self.revues,
            "resolues": self.resolues,
            "ouvertes_par_categorie": self.ouvertes_par_categorie,
            "total_ouvertes": self.total_ouvertes,
            "taches_ouvertes": [
                t.to_dict() for t in self.taches_ouvertes[:TACHES_DETAILLEES]
            ],
        }


def _categories_non_verifiees(constats) -> Set[str]:
    """Catégories dont une sonde a explicitement signalé un verdict incomplet."""
    return {
        constat.fichier
        for constat in constats
        if constat.categorie == CATEGORIE_DIAGNOSTIC and constat.fichier
    }


class Gardien:
    """Un cycle : diagnostiquer, enregistrer, prouver les résolutions, rapporter."""

    def __init__(
        self, file_maintenance: FileDeMaintenance, executer: Executeur = executer_reel
    ) -> None:
        self.file = file_maintenance
        self.executer = executer

    def executer_cycle(self) -> RapportSante:
        constats = diagnostiquer_tout(self.executer)
        triage = self.file.enregistrer_constats(constats)
        self.file.marquer_cycle_termine()

        empreintes_actuelles = {c.empreinte for c in constats}
        categories_non_verifiees = _categories_non_verifiees(constats)
        resolues = 0
        for tache in self.file.ouvertes():
            # Fail closed : si la sonde de cette catégorie n'a pas abouti,
            # l'absence du constat n'est pas une preuve de résolution.
            if tache.categorie in categories_non_verifiees:
                continue
            if tache.empreinte not in empreintes_actuelles:
                if self.file.marquer_resolue(tache.empreinte):
                    resolues += 1
                    logger.info(
                        "Constat resolu (plus produit par le diagnostic) : %s — %s",
                        tache.categorie,
                        tache.description,
                    )

        ouvertes = self.file.ouvertes()
        par_categorie: Dict[str, int] = {}
        for tache in ouvertes:
            par_categorie[tache.categorie] = par_categorie.get(tache.categorie, 0) + 1

        return RapportSante(
            nouvelles=triage.nouvelles,
            revues=triage.revues,
            resolues=resolues,
            ouvertes_par_categorie=par_categorie,
            taches_ouvertes=ouvertes,
        )
