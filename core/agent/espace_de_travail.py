"""L'espace de travail partage d'un projet collaboratif (DEC-0146).

Tous les agents qui participent a un projet doivent pouvoir savoir ce qui a
deja ete fait, ce qui reste, qui travaille, quels resultats existent et
quelles decisions ont ete prises. Chaque agent garde son propre contexte (le
message qu'il recoit, sa memoire) ; le projet a en plus un contexte PARTAGE,
ici.

    espace/
        contexte     ce que les agents ont appris et versent au projet
        taches       l'arbre des delegations : qui, quoi, pour qui, etat
        discussions  les tables rondes, tour par tour
        sorties      les resultats produits
        decisions    ce qui a ete tranche, et par qui
        participants qui travaille en ce moment

**Un agent qui rejoint en cours de route recupere le contexte PERTINENT,
pas tout** : `contexte_pour(besoin)` classe les entrees par mots communs et
s'arrete a un budget de caracteres.

Persistance : `core/execution/journal_disque.py` (ecriture atomique), le meme
que les autres journaux durables d'ARENA ; sans dossier configure, l'espace
vit en memoire seulement.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agent.decouverte import mots

logger = logging.getLogger("usman.agent.espace")

#: Ce qu'une entree de l'espace garde au plus : un espace n'est pas un
#: entrepot de documents, il porte des resumes.
TEXTE_MAX = 2000


def _court(texte: Any) -> str:
    texte = str(texte or "").strip()
    return texte if len(texte) <= TEXTE_MAX else texte[:TEXTE_MAX] + " […]"


@dataclass
class TacheEspace:
    task_id: str
    root_task_id: str
    parent_task_id: Optional[str]
    depth: int
    sender: str
    recipient: str
    objectif: str
    statut: str = "en_cours"
    resultat: str = ""
    debut: float = field(default_factory=time.time)
    fin: Optional[float] = None


@dataclass
class EspaceDeTravail:
    """Le contexte partage d'UN projet."""

    project_id: str
    contexte: List[Dict[str, Any]] = field(default_factory=list)
    taches: Dict[str, TacheEspace] = field(default_factory=dict)
    discussions: List[Dict[str, Any]] = field(default_factory=list)
    sorties: List[Dict[str, Any]] = field(default_factory=list)
    decisions: List[Dict[str, Any]] = field(default_factory=list)

    # --- Ecrire ---------------------------------------------------------------

    def verser(self, auteur: str, texte: str, nature: str = "note") -> None:
        """Ajoute au contexte partage ce qu'un agent sait et que d'autres
        pourraient vouloir savoir."""
        if str(texte or "").strip():
            self.contexte.append({"auteur": auteur, "nature": nature,
                                  "texte": _court(texte), "date": time.time()})

    def tache_ouverte(self, tache: TacheEspace) -> None:
        self.taches[tache.task_id] = tache

    def tache_fermee(self, task_id: str, statut: str, resultat: str) -> None:
        tache = self.taches.get(task_id)
        if tache is None:
            return
        tache.statut, tache.resultat, tache.fin = statut, _court(resultat), time.time()
        if statut == "terminee" and tache.resultat:
            self.sorties.append({"auteur": tache.recipient, "task_id": task_id,
                                 "objectif": tache.objectif, "texte": tache.resultat})

    def discussion(self, sujet: str) -> Dict[str, Any]:
        """Ouvre une discussion (table ronde) et la rend, pour y ecrire."""
        fil = {"sujet": _court(sujet), "interventions": [], "participants": [],
               "date": time.time()}
        self.discussions.append(fil)
        return fil

    def decider(self, auteur: str, decision: str) -> None:
        if str(decision or "").strip():
            self.decisions.append({"auteur": auteur, "texte": _court(decision),
                                   "date": time.time()})

    # --- Lire ---------------------------------------------------------------

    @property
    def participants(self) -> List[str]:
        """Les agents qui travaillent EN CE MOMENT sur le projet."""
        return sorted({t.recipient for t in self.taches.values() if t.statut == "en_cours"})

    def reste_a_faire(self) -> List[Dict[str, Any]]:
        return [asdict(t) for t in self.taches.values() if t.statut == "en_cours"]

    def contexte_pour(self, besoin: str, budget_caracteres: int = 1500) -> str:
        """Le contexte partage PERTINENT pour `besoin`, dans un budget.

        Les entrees (contexte verse, sorties, decisions) sont classees par
        mots communs avec le besoin ; une entree sans aucun mot commun n'est
        pas rendue. Vide quand rien n'est pertinent : un agent ne recoit
        jamais un contexte invente pour en avoir un.
        """
        demande = set(mots(besoin))
        if not demande:
            return ""
        candidates = (
            [(e["auteur"], e["texte"]) for e in self.contexte]
            + [(s["auteur"], s["texte"]) for s in self.sorties]
            + [(d["auteur"], f"Decision : {d['texte']}") for d in self.decisions])
        classees = sorted(
            ((len(demande & set(mots(texte))), auteur, texte) for auteur, texte in candidates),
            key=lambda triple: -triple[0])
        lignes, taille = [], 0
        for score, auteur, texte in classees:
            if score <= 0:
                break
            ligne = f"- [{auteur}] {texte}"
            if taille + len(ligne) > budget_caracteres:
                break
            lignes.append(ligne)
            taille += len(ligne)
        return "\n".join(lignes)

    def etat(self) -> Dict[str, Any]:
        """Ce qui a ete fait, ce qui reste, qui travaille, ce qui existe."""
        return {
            "project_id": self.project_id,
            "participants": self.participants,
            "taches": [asdict(t) for t in self.taches.values()],
            "reste_a_faire": self.reste_a_faire(),
            "sorties": list(self.sorties),
            "decisions": list(self.decisions),
            "discussions": list(self.discussions),
            "contexte": list(self.contexte),
        }

    @classmethod
    def depuis(cls, donnees: Dict[str, Any]) -> "EspaceDeTravail":
        espace = cls(project_id=str(donnees.get("project_id") or ""))
        espace.contexte = list(donnees.get("contexte") or [])
        espace.discussions = list(donnees.get("discussions") or [])
        espace.sorties = list(donnees.get("sorties") or [])
        espace.decisions = list(donnees.get("decisions") or [])
        for brute in donnees.get("taches") or []:
            try:
                tache = TacheEspace(**brute)
            except TypeError:
                continue
            espace.taches[tache.task_id] = tache
        return espace


class EspacesDeTravail:
    """Tous les espaces, par projet. Bornes en memoire ; ecrits sur disque
    quand un dossier est configure."""

    MAXIMUM_EN_MEMOIRE = 200

    def __init__(self, dossier: Optional[Path] = None) -> None:
        self.dossier = dossier
        self._espaces: "OrderedDict[str, EspaceDeTravail]" = OrderedDict()
        self._verrou = threading.Lock()

    def _fichier(self, project_id: str) -> Optional[Path]:
        if self.dossier is None:
            return None
        sur = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_id)[:80]
        return self.dossier / f"{sur or 'projet'}.json"

    def pour(self, project_id: str) -> EspaceDeTravail:
        """L'espace du projet, relu sur disque s'il existe, cree sinon."""
        cle = str(project_id or "sans_projet")
        with self._verrou:
            espace = self._espaces.get(cle)
            if espace is None:
                espace = self._relire(cle) or EspaceDeTravail(project_id=cle)
                self._espaces[cle] = espace
                while len(self._espaces) > self.MAXIMUM_EN_MEMOIRE:
                    self._espaces.popitem(last=False)
            self._espaces.move_to_end(cle)
            return espace

    def existe(self, project_id: str) -> bool:
        fichier = self._fichier(project_id)
        return project_id in self._espaces or bool(fichier and fichier.exists())

    def _relire(self, project_id: str) -> Optional[EspaceDeTravail]:
        fichier = self._fichier(project_id)
        if fichier is None or not fichier.exists():
            return None
        from core.execution.journal_disque import lire_json

        return EspaceDeTravail.depuis(lire_json(fichier, {}))

    def sauver(self, project_id: str) -> None:
        """Ecrit l'espace sur disque. Une panne d'ecriture ne casse rien :
        l'espace reste en memoire et la panne est journalisee."""
        fichier = self._fichier(project_id)
        espace = self._espaces.get(project_id)
        if fichier is None or espace is None:
            return
        from core.execution.journal_disque import ecrire_json_atomique

        try:
            fichier.parent.mkdir(parents=True, exist_ok=True)
            ecrire_json_atomique(fichier, espace.etat())
        except Exception as erreur:  # noqa: BLE001 — la memoire ne bloque pas le travail
            logger.warning("Espace %s non ecrit : %s", project_id, erreur)


#: Les espaces du processus. `apps/backend/runtime.py` lui donne un dossier.
ESPACES = EspacesDeTravail()
