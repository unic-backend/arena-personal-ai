"""Indexation des documents du propriétaire dans le moteur documentaire.

Chaîne complète : inventaire → lecture → insertion → inventaire mis à jour.

Trois règles, et elles tiennent toutes à la même idée — un index qui se croit à
jour alors qu'il ne l'est pas est pire qu'un index vide :

1. **On vérifie le moteur avant de commencer.** Si Ollama ne répond pas, ou si le
   modèle d'embeddings n'est pas installé, rien n'est indexé et rien n'est noté.
   Un refus franc vaut mieux qu'une indexation à moitié faite.
2. **Un document n'est noté comme indexé que s'il l'a vraiment été.** Une
   insertion qui échoue laisse le document hors de l'inventaire : il sera repris
   au prochain passage.
3. **La provenance part avec le texte.** Chaque passage est préfixé de sa source,
   sinon tout le travail de lecture page par page serait perdu à l'insertion.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from apps.backend.config import BASE_DIR, OLLAMA_URL
from tools.documents.inventory import Inventaire
from tools.documents.reader import lire_document

logger = logging.getLogger("usman.tools.documents")

DOSSIER_DOCUMENTS = BASE_DIR / "data" / "documents"
FICHIER_INVENTAIRE = BASE_DIR / "data" / "rag" / "inventaire.json"

# Modele d'embeddings attendu par LightRAGTool (voir tools/rag/lightrag_tool.py).
MODELE_EMBEDDINGS = "nomic-embed-text"
DELAI_VERIFICATION = 5.0


@dataclass
class Rapport:
    """Ce qui s'est réellement passé, document par document."""

    statut: str
    indexes: List[str] = field(default_factory=list)
    echecs: List[Dict[str, str]] = field(default_factory=list)
    ignores: List[str] = field(default_factory=list)
    inchanges: List[str] = field(default_factory=list)
    disparus: List[str] = field(default_factory=list)
    raison: Optional[str] = None

    def resume(self) -> Dict[str, Any]:
        return {
            "statut": self.statut,
            "indexes": len(self.indexes),
            "echecs": len(self.echecs),
            "ignores": len(self.ignores),
            "inchanges": len(self.inchanges),
            "disparus": len(self.disparus),
            "raison": self.raison,
        }

    def __str__(self) -> str:
        if self.statut == "REFUSE":
            return f"REFUSE : {self.raison}"
        if self.statut == "RIEN_A_FAIRE":
            return f"Rien a faire : {len(self.inchanges)} document(s) deja indexe(s)."
        parties = [f"{len(self.indexes)} indexe(s)"]
        if self.echecs:
            parties.append(f"{len(self.echecs)} echec(s)")
        if self.inchanges:
            parties.append(f"{len(self.inchanges)} inchange(s)")
        if self.ignores:
            parties.append(f"{len(self.ignores)} ignore(s)")
        if self.disparus:
            parties.append(f"{len(self.disparus)} disparu(s)")
        return ", ".join(parties) + "."


def verifier_moteur(url: str = OLLAMA_URL, modele: str = MODELE_EMBEDDINGS) -> Optional[str]:
    """Renvoie la raison du refus, ou None si le moteur est prêt.

    Deux conditions : Ollama répond, et le modèle d'embeddings est installé.
    Sans lui, LightRAG échoue document par document — autant le dire d'emblée.
    """
    try:
        reponse = httpx.get(f"{url.rstrip('/')}/api/tags", timeout=DELAI_VERIFICATION)
        reponse.raise_for_status()
        donnees = reponse.json()
    except Exception as e:
        return f"Ollama ne repond pas sur {url} ({type(e).__name__}). Demarre-le avec : ollama serve"

    installes = [m.get("name", "") for m in donnees.get("models", [])]
    if not any(nom.split(":")[0] == modele for nom in installes):
        return (
            f"Le modele d'embeddings '{modele}' n'est pas installe. "
            f"Installe-le avec : ollama pull {modele}"
        )
    return None


def texte_avec_provenance(document) -> str:
    """Préfixe chaque passage de sa source, pour que le moteur puisse la citer."""
    return "\n\n".join(f"[Source : {p.source}]\n{p.texte}" for p in document.passages)


def indexer_documents(
    moteur,
    dossier: Path | str = DOSSIER_DOCUMENTS,
    inventaire_chemin: Path | str = FICHIER_INVENTAIRE,
    verifier: bool = True,
) -> Rapport:
    """Indexe ce qui doit l'être, et rien d'autre.

    `moteur` doit exposer `insert_text(texte) -> bool` — c'est le contrat de
    `LightRAGTool`, ce qui rend cette fonction testable sans Ollama.
    """
    if verifier:
        raison = verifier_moteur()
        if raison:
            logger.error(f"Indexation refusee : {raison}")
            return Rapport(statut="REFUSE", raison=raison)

    inventaire = Inventaire(inventaire_chemin)
    plan = inventaire.analyser(dossier)
    logger.info(f"Plan d'indexation : {plan}")

    rapport = Rapport(
        statut="RIEN_A_FAIRE",
        ignores=[c.name for c in plan.ignores],
        inchanges=[c.name for c in plan.inchanges],
        disparus=list(plan.disparus),
    )
    if plan.rien_a_faire:
        return rapport

    for chemin in plan.a_indexer:
        document = lire_document(chemin)
        if not document.lu:
            rapport.echecs.append({"fichier": chemin.name, "raison": document.raison})
            continue

        try:
            insere = moteur.insert_text(texte_avec_provenance(document))
        except Exception as e:
            insere = False
            logger.error(f"Insertion impossible pour {chemin.name} : {e}")

        if not insere:
            # Non note dans l'inventaire : il sera repris au prochain passage.
            rapport.echecs.append({"fichier": chemin.name, "raison": "insertion refusee par le moteur"})
            continue

        inventaire.noter_indexation(chemin, len(document.passages), document.caracteres)
        rapport.indexes.append(chemin.name)

    inventaire.enregistrer_sur_disque()
    rapport.statut = "PARTIEL" if rapport.echecs and rapport.indexes else (
        "ECHEC" if rapport.echecs else "INDEXE"
    )
    logger.info(f"Indexation terminee : {rapport}")
    return rapport
