"""L'etat durable d'un projet de production : ce qui survit a un redemarrage.

**Le manque mesure le 19/09/2026.** Un projet Video
(`agents/video/production_agent.py`) decompose un objectif en etapes, les fait
tourner par `core/execution/coordination.py`, et rend un dictionnaire. Tout
cela est correct — et **entierement en memoire**. `EtatProjetVideo`
(`core/production/etat_projet.py`) ne porte ni identifiant, ni statut par
etape, ni horodatage, et rien ne l'ecrit nulle part. Consequence exacte : un
serveur redemarre au milieu d'une production laisse zero trace. Personne — ni
le proprietaire, ni ARENA — ne peut dire ce qui avait abouti, et la seule
issue est de tout relancer depuis le debut, y compris les etapes qui avaient
deja produit leur fichier.

Ce module est l'etat qui manquait. Il ne fait tourner aucune etape et ne
decide d'aucun ordre : **`Coordination` reste le seul executeur**, et ce
journal ne fait que noter ce qu'elle observe, par son hook `observateur` qui
existait deja. Aucun second orchestrateur n'est introduit.

---

## Cinq regles

1. **Ce qui n'est pas ecrit n'a pas eu lieu.** Chaque changement d'etat est
   persiste immediatement, de facon atomique. Un projet tue au milieu doit
   laisser exactement ce qu'il avait fait — ni plus, ni moins.

2. **Une etape ne se saute que sur PREUVE.** Trois conditions, toutes les
   trois : son etat est `SUCCEEDED`, son entree est identique (empreinte), et
   **son artefact existe encore sur le disque**. Un fichier efface entre-temps
   rend l'etape a refaire — se fier au statut seul rendrait un projet qui se
   dit fini sans fichier au bout.

3. **`RUNNING` retrouve au chargement n'est pas `SUCCEEDED`.** Aucun processus
   ne tourne au demarrage : une etape laissee `RUNNING` a ete *decidee* sans
   qu'on sache ce qu'elle a donne. Elle devient non confirmee, n'est jamais
   reutilisee, et la reprise le dit en clair plutot que de la rejouer en
   aveugle. Meme discipline que `core/execution/reprise.py`.

4. **Un journal casse ne casse pas la production.** Fichier illisible, disque
   plein, JSON corrompu : le projet tourne sans reprise et le dit. Perdre la
   memoire d'un travail est ennuyeux ; perdre le travail parce que sa memoire
   est en panne serait absurde.

5. **Aucun etat n'est deduit.** Les six etats sont ecrits par celui qui agit.
   Il n'y a pas de septieme etat implicite « probablement fini ».
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from core.execution.journal_disque import ecrire_json_atomique, lire_json

logger = logging.getLogger("usman.production.journal")

#: Ou le journal vit. Hors du depot (`data/` est ignore par git) : il porte les
#: objectifs du proprietaire et les chemins de ses fichiers.
FICHIER_PAR_DEFAUT = Path("data") / "projets" / "journal.json"

#: Combien de jobs FINIS restent dans le journal. Les jobs reprenables ne sont
#: jamais purges — ce serait perdre du travail.
JOBS_FINIS_GARDES = 100

#: Longueur maximale d'une raison d'echec conservee. Un message d'exception
#: peut transporter un chemin complet : on garde de quoi diagnostiquer.
RAISON_MAX = 300


class EtatJob(str, Enum):
    """Les six etats, et rien d'autre. Chacun est ecrit, aucun n'est deduit."""

    EN_ATTENTE = "PENDING"
    EN_COURS = "RUNNING"
    REUSSI = "SUCCEEDED"
    ECHOUE = "FAILED"
    ANNULE = "CANCELLED"
    SUSPENDU = "PAUSED"


#: Les deux seuls etats dont on ne revient pas. **`FAILED` n'en fait pas
#: partie**, et c'est le point : une etape obligatoire qui echoue (ffmpeg
#: absent, service coupe) est exactement le cas ou le proprietaire repare la
#: cause et veut CONTINUER. Classer `FAILED` comme final rendait la reprise
#: inutile la ou elle sert le plus — mesure du 19/09/2026, attrapee par
#: `tests/agents/video/test_production_reprise.py`.
ETATS_FINAUX = frozenset({EtatJob.REUSSI, EtatJob.ANNULE})


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empreinte(entree: Any) -> str:
    """L'empreinte d'une entree d'etape, pour repondre a « est-ce la meme ? ».

    Sert la regle d'idempotence : meme job + meme etape + **meme entree** ne
    doit pas produire deux fois le meme effet irreversible. Une entree qui a
    change rend l'etape a refaire, meme si l'ancienne avait abouti.

    Le tri des cles rend l'empreinte stable d'une execution a l'autre ; un
    objet non serialisable retombe sur sa representation, qui est encore une
    information — jamais une exception qui ferait tomber la production.
    """
    try:
        texte = json.dumps(entree, sort_keys=True, ensure_ascii=False, default=repr)
    except (TypeError, ValueError):  # pragma: no cover — `default=repr` couvre deja
        texte = repr(entree)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:32]


@dataclass
class EtapeJob:
    """Une etape du job : ce qu'on lui a demande, ce qu'elle a rendu."""

    step_id: str
    capacite: str
    etat: EtatJob = EtatJob.EN_ATTENTE
    cree_le: str = field(default_factory=_maintenant)
    maj_le: str = field(default_factory=_maintenant)
    #: L'empreinte de l'entree, pas l'entree : un parametre peut porter le
    #: contenu d'un document. Ce journal n'est pas un endroit ou le stocker.
    entree: str = ""
    sortie: Any = None
    artefact: Optional[str] = None
    #: Qui a fait le travail et combien de temps. Jamais estime.
    preuve: Dict[str, Any] = field(default_factory=dict)
    erreur: str = ""
    essais: int = 0
    #: Un artefact a-t-il ete ANNONCE par l'outil ? `True` avec `artefact`
    #: a `None` decrit un cas precis et dangereux : l'outil a nomme un
    #: fichier qu'il n'a pas ecrit. Sans ce champ, ce cas se confond avec
    #: celui d'une etape qui ne produit aucun fichier (une analyse) — et la
    #: reprise sauterait une etape dont rien n'a ete livre.
    artefact_attendu: bool = False
    #: `False` entre le demarrage et la conclusion de l'etape. Une etape
    #: retrouvee non confirmee au chargement a ete decidee sans qu'on sache
    #: ce qu'elle a donne : elle n'est ni reussie, ni echouee (regle 3).
    confirmee: bool = True

    @property
    def reutilisable(self) -> bool:
        """Peut-on sauter cette etape ? Trois conditions, pas une (regle 2)."""
        if not (self.confirmee and self.etat is EtatJob.REUSSI):
            return False
        if self.artefact is None:
            # Deux cas, et les confondre coute un fichier : une etape qui ne
            # produit RIEN (une analyse) est reutilisable sur son statut ; une
            # etape qui avait ANNONCE un fichier introuvable ne l'est pas.
            return not self.artefact_attendu
        return Path(self.artefact).exists()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id, "capacite": self.capacite,
            "status": self.etat.value, "created_at": self.cree_le,
            "updated_at": self.maj_le, "input": self.entree,
            "output": self.sortie, "artifact": self.artefact,
            "proof": self.preuve, "error": self.erreur,
            "retry_count": self.essais, "confirmee": self.confirmee,
            "artefact_attendu": self.artefact_attendu,
            "reutilisable": self.reutilisable,
        }


@dataclass
class Job:
    """Un projet de production, et tout ce qui a deja ete fait pour lui."""

    job_id: str
    projet_id: str
    objectif: str
    etat: EtatJob = EtatJob.EN_ATTENTE
    cree_le: str = field(default_factory=_maintenant)
    maj_le: str = field(default_factory=_maintenant)
    etapes: List[EtapeJob] = field(default_factory=list)
    artefact_final: Optional[str] = None
    erreur: str = ""
    #: Le graphe VALIDE tel qu'il a ete execute, et le contexte qui va avec.
    #: Sans lui, « reprendre » voudrait dire redemander un plan au modele —
    #: qui en rendrait un autre. Reprendre un AUTRE plan n'est pas reprendre :
    #: les etapes deja faites ne correspondraient plus, et le travail serait
    #: refait sous d'autres noms.
    graphe: List[Dict[str, Any]] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    contraintes: Dict[str, Any] = field(default_factory=dict)

    @property
    def fini(self) -> bool:
        return self.etat in ETATS_FINAUX

    @property
    def reprenable(self) -> bool:
        """Un job arrete (`PAUSED` ou `FAILED`) dont il reste du travail.

        Un job suspendu dont TOUTES les etapes sont reutilisables n'est pas
        « a reprendre » : il est fini sans que personne ne l'ait ecrit. Le dire
        reprenable enverrait le proprietaire relancer un travail deja fait.
        """
        if self.etat not in (EtatJob.SUSPENDU, EtatJob.ECHOUE):
            return False
        return any(not etape.reutilisable for etape in self.etapes)

    def etape(self, step_id: str) -> Optional[EtapeJob]:
        return next((e for e in self.etapes if e.step_id == step_id), None)

    def deja_fait(self) -> Dict[str, Any]:
        """Ce qui est reutilisable, par `step_id`. La base de la reprise."""
        return {e.step_id: e.sortie for e in self.etapes if e.reutilisable}

    def a_verifier(self) -> List[str]:
        """Les etapes dont on ne sait pas ce qu'elles ont donne.

        Mission ARENA x TRANS4MERS §15 : « never blindly rerun a potentially
        destructive operation after crash ». Les nommer est la seule facon de
        tenir cette regle — une ligne muette se relirait comme les autres.
        """
        return [e.step_id for e in self.etapes if not e.confirmee]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id, "project_id": self.projet_id,
            "objectif": self.objectif, "status": self.etat.value,
            "created_at": self.cree_le, "updated_at": self.maj_le,
            "artifact": self.artefact_final, "error": self.erreur,
            "resumable": self.reprenable,
            "a_verifier": self.a_verifier(),
            "graphe": self.graphe,
            "references": self.references,
            "contraintes": self.contraintes,
            "steps": [e.to_dict() for e in self.etapes],
        }


class JournalProjets:
    """Le journal durable des jobs. Un fichier, ecrit apres chaque changement."""

    def __init__(self, fichier: Optional[Path] = None) -> None:
        self.fichier = Path(fichier) if fichier else FICHIER_PAR_DEFAUT
        self._jobs: Dict[str, Job] = {}
        self._charger()

    # --- Disque -------------------------------------------------------------------

    def _charger(self) -> None:
        """Relit le journal, et marque ce qui ne tourne plus (regle 3).

        Au demarrage, aucun processus ne tourne. Un job `RUNNING` retrouve ici
        est donc un job **mort** : il devient `PAUSED`, ses etapes en cours
        deviennent non confirmees. C'est ce qui rend la reprise possible sans
        rien supposer.
        """
        brut = lire_json(self.fichier, quoi="Journal de projets")
        for donnees in brut.get("jobs", []):
            job = self._relire_job(donnees)
            if job is not None:
                self._jobs[job.job_id] = job

    def _relire_job(self, donnees: Any) -> Optional[Job]:
        """Un job du disque. Une ligne illisible est ignoree, pas fatale."""
        if not isinstance(donnees, dict):
            return None
        try:
            job = Job(
                job_id=str(donnees["job_id"]),
                projet_id=str(donnees.get("project_id", "")),
                objectif=str(donnees.get("objectif", "")),
                etat=EtatJob(donnees.get("status", "PENDING")),
                cree_le=str(donnees.get("created_at", _maintenant())),
                maj_le=str(donnees.get("updated_at", _maintenant())),
                artefact_final=donnees.get("artifact"),
                erreur=str(donnees.get("error", "")),
                graphe=list(donnees.get("graphe") or []),
                references=list(donnees.get("references") or []),
                contraintes=dict(donnees.get("contraintes") or {}),
            )
            for e in donnees.get("steps", []):
                job.etapes.append(EtapeJob(
                    step_id=str(e["step_id"]),
                    capacite=str(e.get("capacite", "")),
                    etat=EtatJob(e.get("status", "PENDING")),
                    cree_le=str(e.get("created_at", job.cree_le)),
                    maj_le=str(e.get("updated_at", job.maj_le)),
                    entree=str(e.get("input", "")),
                    sortie=e.get("output"),
                    artefact=e.get("artifact"),
                    preuve=dict(e.get("proof") or {}),
                    erreur=str(e.get("error", "")),
                    essais=int(e.get("retry_count", 0)),
                    artefact_attendu=bool(e.get("artefact_attendu", False)),
                    confirmee=bool(e.get("confirmee", True)),
                ))
        except (KeyError, TypeError, ValueError) as erreur:
            logger.warning("Job illisible dans le journal (%s) : ignore.", erreur)
            return None

        if job.etat in (EtatJob.EN_COURS, EtatJob.EN_ATTENTE):
            # Rien ne tourne au demarrage : ce job est mort en route.
            job.etat = EtatJob.SUSPENDU
            for etape in job.etapes:
                # SEULE une etape `RUNNING` devient non confirmee. Une etape
                # `PENDING` n'a jamais demarre : il n'y a rien d'inconnu a son
                # sujet, elle est simplement a faire. Les melanger noierait
                # `a_verifier()` — l'avertissement « ne relance pas ca sans
                # verifier » ne vaut que s'il ne nomme QUE ce qui a bouge.
                if etape.etat is EtatJob.EN_COURS:
                    etape.confirmee = False
        return job

    def _ecrire(self) -> None:
        """Ecrit le journal. **Atomique** : un remplacement, jamais une troncature.

        Une ecriture directe interrompue laisserait un fichier a moitie ecrit —
        c'est-a-dire un journal de reprise illisible, dans le seul moment ou il
        sert.
        """
        ecrire_json_atomique(
            self.fichier, {"jobs": [job.to_dict() for job in self._jobs.values()]},
            prefixe=".journal-", quoi="Journal de projets")

    def _touche(self, job: Job) -> None:
        job.maj_le = _maintenant()
        self._purger()
        self._ecrire()

    def _purger(self) -> None:
        """Borne l'historique. Les jobs reprenables ne sont jamais jetes."""
        # Un job reprenable n'est JAMAIS purge, quel que soit son age : ce
        # serait jeter du travail deja fait. Un job en cours non plus.
        jetables = [j for j in self._jobs.values()
                    if not j.reprenable and j.etat is not EtatJob.EN_COURS]
        if len(jetables) <= JOBS_FINIS_GARDES:
            return
        jetables.sort(key=lambda j: j.maj_le)
        for job in jetables[:len(jetables) - JOBS_FINIS_GARDES]:
            self._jobs.pop(job.job_id, None)

    # --- Le cycle d'un job ------------------------------------------------------------

    def ouvrir(self, objectif: str, projet_id: str = "",
               graphe: Optional[List[Dict[str, Any]]] = None,
               references: Optional[List[str]] = None,
               contraintes: Optional[Dict[str, Any]] = None) -> Job:
        """Inscrit un job. Il existe sur le disque **avant** la premiere etape."""
        job = Job(job_id=uuid4().hex, projet_id=projet_id or uuid4().hex,
                  objectif=objectif, etat=EtatJob.EN_COURS,
                  graphe=list(graphe or []), references=list(references or []),
                  contraintes=dict(contraintes or {}))
        self._jobs[job.job_id] = job
        self._touche(job)
        return job

    def lire(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def reprenables(self) -> List[Job]:
        return [job for job in self._jobs.values() if job.reprenable]

    def declarer_etapes(self, job_id: str,
                        etapes: List[Dict[str, Any]]) -> Optional[Job]:
        """Pose le graphe complet, `PENDING`, avant toute execution.

        Une etape deja presente n'est PAS recreee : c'est ce qui permet de
        redeclarer le meme graphe a la reprise sans effacer ce qui avait
        abouti.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return None
        for declaree in etapes:
            step_id = str(declaree.get("step_id") or declaree.get("id") or "")
            if not step_id or job.etape(step_id) is not None:
                continue
            job.etapes.append(EtapeJob(
                step_id=step_id,
                capacite=str(declaree.get("capacite", "")),
                entree=empreinte(declaree.get("entree")),
            ))
        self._touche(job)
        return job

    def demarrer_etape(self, job_id: str, step_id: str,
                       entree: Any = None) -> Optional[EtapeJob]:
        """L'etape passe `RUNNING` et **devient non confirmee** : elle est
        decidee, son resultat n'est pas encore connu. Ecrit tout de suite —
        c'est la fenetre pendant laquelle un crash doit laisser une trace."""
        job = self._jobs.get(job_id)
        if job is None:
            return None
        etape = job.etape(step_id)
        if etape is None:
            etape = EtapeJob(step_id=step_id, capacite=step_id)
            job.etapes.append(etape)
        if entree is not None:
            etape.entree = empreinte(entree)
        etape.etat = EtatJob.EN_COURS
        etape.confirmee = False
        etape.maj_le = _maintenant()
        self._touche(job)
        return etape

    def conclure_etape(self, job_id: str, step_id: str, etat: EtatJob,
                       sortie: Any = None, artefact: Optional[str] = None,
                       preuve: Optional[Dict[str, Any]] = None,
                       erreur: str = "", essais: int = 0) -> Optional[EtapeJob]:
        """Ce que l'etape a reellement donne. C'est ici qu'elle est confirmee.

        L'artefact n'est retenu **que s'il existe sur le disque** : un chemin
        annonce par un outil qui n'a rien ecrit ferait croire a un fichier
        livre. Ce qui n'existe pas n'est pas un artefact.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return None
        etape = job.etape(step_id)
        if etape is None:
            return None
        etape.etat = etat
        etape.sortie = sortie
        etape.artefact_attendu = bool(artefact)
        etape.artefact = str(artefact) if artefact and Path(artefact).exists() else None
        if artefact and etape.artefact is None:
            etape.erreur = (f"artefact annonce absent du disque : {artefact}. "
                            + (erreur or "")).strip()[:RAISON_MAX]
        else:
            etape.erreur = erreur[:RAISON_MAX]
        etape.preuve = dict(preuve or {})
        etape.essais = essais
        etape.confirmee = True
        etape.maj_le = _maintenant()
        self._touche(job)
        return etape

    def reutiliser_etape(self, job_id: str, step_id: str) -> Optional[EtapeJob]:
        """Note qu'une etape a ete SAUTEE parce que son resultat tenait encore.

        Elle reste `SUCCEEDED` — elle l'est — mais sa preuve porte le fait
        qu'aucun travail n'a eu lieu ce tour-ci. Sans cette marque, une reprise
        se lirait comme une execution complete, et personne ne verrait que rien
        n'a tourne.
        """
        job = self._jobs.get(job_id)
        if job is None:
            return None
        etape = job.etape(step_id)
        if etape is None or not etape.reutilisable:
            return None
        etape.preuve = {**etape.preuve, "reutilise": True}
        etape.maj_le = _maintenant()
        self._touche(job)
        return etape

    def conclure(self, job_id: str, etat: EtatJob,
                 artefact_final: Optional[str] = None,
                 erreur: str = "") -> Optional[Job]:
        """L'etat final du job. Meme discipline d'artefact que pour une etape."""
        job = self._jobs.get(job_id)
        if job is None:
            return None
        job.etat = etat
        if artefact_final and Path(artefact_final).exists():
            job.artefact_final = str(artefact_final)
        job.erreur = erreur[:RAISON_MAX]
        self._touche(job)
        return job

    def suspendre(self, job_id: str, raison: str = "") -> Optional[Job]:
        """`PAUSED` : le job s'arrete sans avoir conclu, et reste reprenable."""
        return self.conclure(job_id, EtatJob.SUSPENDU, erreur=raison)

    def annuler(self, job_id: str, raison: str = "") -> Optional[Job]:
        """`CANCELLED`, et definitif : un job annule ne se reprend pas.

        Idempotent : annuler deux fois annule une fois, et un job deja fini ne
        redevient pas annulable — sinon un double clic effacerait un succes.
        """
        job = self._jobs.get(job_id)
        if job is None or job.fini:
            return job
        return self.conclure(job_id, EtatJob.ANNULE, erreur=raison)
