"""Le gardien : DECOUVRIR -> ENREGISTRER -> RAPPORTER. Jamais MODIFIER.

Ce que la mission demandait dépasse ce qui peut se faire sans surveillance :
une garde qui commettrait des correctifs ou ouvrirait des pull requests
elle-même contournerait exactement la garantie que `CLAUDE.md` pose comme
non négociable — « il ne peut pas lancer les tests, la PR est l'endroit où
il voit ce qui entre ». Ce module tient donc la moitié sûre, réelle, jamais
simulée de la mission : un cycle qui regarde l'état du dépôt, avec les
outils qui existent déjà (`ruff`, `pytest`, `orphelins.py`), et qui retient
ce qu'il a vu — sans jamais écrire une ligne de code applicatif. La
réparation reste un humain qui lit `docs/DECISIONS.md` (DEC-0014) et
demande la suite explicitement.
"""
import logging
from dataclasses import dataclass
from typing import Dict, List

from core.guardian.diagnostics import Executeur, diagnostiquer_tout, executer_reel
from core.guardian.file_maintenance import FileDeMaintenance, Tache

logger = logging.getLogger("usman.guardian.gardien")

#: Combien de tâches ouvertes le rapport détaille — au-delà, un compte suffit.
TACHES_DETAILLEES = 10


@dataclass(frozen=True)
class RapportSante:
    """Ce que le §22 de la mission demande — en français, avec des preuves."""

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
        lignes.append(f"Les {min(TACHES_DETAILLEES, len(self.taches_ouvertes))} plus urgentes "
                      f"(sur {self.total_ouvertes}) :")
        for tache in self.taches_ouvertes[:TACHES_DETAILLEES]:
            lignes.append(f"- [{tache.gravite}] {tache.categorie} — "
                          f"{tache.description} ({tache.fichier})")
        return "\n".join(lignes)

    def to_dict(self) -> dict:
        return {
            "nouvelles": self.nouvelles, "revues": self.revues, "resolues": self.resolues,
            "ouvertes_par_categorie": self.ouvertes_par_categorie,
            "total_ouvertes": self.total_ouvertes,
            "taches_ouvertes": [t.to_dict() for t in self.taches_ouvertes[:TACHES_DETAILLEES]],
        }


class Gardien:
    """Un cycle : diagnostiquer, enregistrer, dire ce qui a disparu, rapporter."""

    def __init__(self, file_maintenance: FileDeMaintenance,
                 executer: Executeur = executer_reel) -> None:
        self.file = file_maintenance
        self.executer = executer

    def executer_cycle(self) -> RapportSante:
        constats = diagnostiquer_tout(self.executer)
        triage = self.file.enregistrer_constats(constats)
        # Marque le cycle comme joue MEME s'il n'a rien trouve — sinon un
        # depot propre et une memoire jamais consultee sont indiscernables
        # (voir doctor.py : verifier_gardien()).
        self.file.marquer_cycle_termine()

        empreintes_actuelles = {c.empreinte for c in constats}
        resolues = 0
        for tache in self.file.ouvertes():
            if tache.empreinte not in empreintes_actuelles:
                if self.file.marquer_resolue(tache.empreinte):
                    resolues += 1
                    logger.info("Constat resolu (plus produit par le diagnostic) : %s — %s",
                               tache.categorie, tache.description)

        ouvertes = self.file.ouvertes()
        par_categorie: Dict[str, int] = {}
        for tache in ouvertes:
            par_categorie[tache.categorie] = par_categorie.get(tache.categorie, 0) + 1

        return RapportSante(
            nouvelles=triage.nouvelles, revues=triage.revues, resolues=resolues,
            ouvertes_par_categorie=par_categorie, taches_ouvertes=ouvertes,
        )
