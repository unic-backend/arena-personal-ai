"""Indexe les documents de `data/documents/` dans le moteur documentaire.

    python scripts/indexer_documents.py

Ce que fait la commande :

1. verifie qu'Ollama repond et que le modele d'embeddings est installe ;
2. regarde ce qui est nouveau ou modifie dans `data/documents/` ;
3. lit chaque document et l'insere avec sa provenance ;
4. note ce qui a reellement ete indexe.

Si Ollama n'est pas la, **rien n'est indexe et rien n'est note**. La commande
peut etre relancee autant de fois que voulu : un document inchange n'est jamais
reindexe.
"""
import logging
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from tools.documents.indexer import (  # noqa: E402
    DOSSIER_DOCUMENTS,
    indexer_documents,
    verifier_moteur,
)
from tools.rag.lightrag_tool import LightRAGTool  # noqa: E402


def principal() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    print(f"Dossier des documents : {DOSSIER_DOCUMENTS}")
    if not DOSSIER_DOCUMENTS.is_dir():
        print("Ce dossier n'existe pas. Cree-le et depose tes fichiers dedans.")
        return 1

    raison = verifier_moteur()
    if raison:
        print(f"\nIndexation refusee.\n  {raison}\n")
        print("Rien n'a ete indexe, et l'inventaire n'a pas ete modifie.")
        return 1

    print("Moteur pret. Analyse du dossier...\n")
    rapport = indexer_documents(LightRAGTool(), verifier=False)

    print(rapport)
    for nom in rapport.indexes:
        print(f"  indexe   {nom}")
    for echec in rapport.echecs:
        print(f"  ECHEC    {echec['fichier']} : {echec['raison']}")
    for nom in rapport.ignores:
        print(f"  ignore   {nom} (format non lu)")
    for nom in rapport.disparus:
        print(f"  disparu  {nom} (present dans l'index, absent du dossier)")

    return 0 if rapport.statut in {"INDEXE", "RIEN_A_FAIRE"} else 1


if __name__ == "__main__":
    sys.exit(principal())
