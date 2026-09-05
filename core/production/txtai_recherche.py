"""Recherche semantique via txtai — un moteur ALTERNATIF, jamais un second RAG.

Demande directe, apres feu vert du proprietaire pour reprendre les
integrations en attente : integrer txtai (neuml/txtai, Apache-2.0) comme
capacite de recherche semantique.

**Ce qu'ARENA a deja, verifie avant d'ecrire une ligne** : une memoire de
conversation retrouvee par le sens (`core/memory/semantique.py`, embeddings
bge-m3 via Ollama local), et deux moteurs de documents (`tools/rag/
lightrag_tool.py`, `tools/rag/graphrag_tool.py`). La regle de la mission est
explicite et conditionnelle : « NE construis PAS un deuxieme RAG... n'utilise
txtai que lorsque son avantage est demontre ». Aucun banc de comparaison
reel n'a pu tourner ici — ce conteneur n'a pas Ollama (`core/memory/
semantique.py` le mesure deja comme absent en cloud) — donc **rien ici ne
remplace ni ne route par defaut vers txtai** : c'est une capacite EXPLICITE,
a cote, que le proprietaire ou un agent appelle pour comparer, jamais
appelee a sa place.

**Aucun second modele d'embeddings.** txtai est installe en version
`txtai_minimal` (paquet officiel sans torch/transformers/faiss — verifie sur
PyPI, 341 Ko) et configure en `method="external"` : le vecteur de chaque
texte vient de `embeddings_ollama()` (`core/memory/semantique.py`), **la
meme fonction** que la memoire de chat utilise deja. Ce qui est evalue ici
est donc uniquement le moteur d'INDEXATION/CLASSEMENT de txtai (faiss
absent -> backend numpy), jamais un second modele charge sur la RTX A2000.

**Rien n'est persiste.** L'index est reconstruit a chaque appel, a partir
des documents FOURNIS par l'appelant dans le meme appel — jamais toutes les
donnees du proprietaire transformees en embeddings automatiquement (mandat
de la mission, §15). Un plafond de documents par appel le garantit.
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Sequence, Tuple

import numpy as np

from core.memory.semantique import embeddings_ollama

logger = logging.getLogger("usman.production.txtai_recherche")

#: Garde le mandat "petits datasets de test" (mission §15/§28) reel, pas
#: seulement promis : un appel ne peut pas transformer une bibliotheque
#: entiere en embeddings d'un coup.
MAX_DOCUMENTS = 200


def _executer_dans_un_thread(coroutine_factory):
    """Execute une coroutine depuis un contexte synchrone, meme si une boucle
    tourne deja — meme correctif que GitIngest (`core/connectors/
    gitingest.py::_sans_jeton_errant`, DEC-0047) pour `asyncio.run()` qui
    leve `RuntimeError` depuis une route FastAPI deja async."""
    with ThreadPoolExecutor(max_workers=1) as executeur:
        return executeur.submit(lambda: asyncio.run(coroutine_factory())).result()


def faire_transform_synchrone(fournisseur_async=None):
    """Construit le callback SYNCHRONE que txtai (`method="external"`)
    exige, a partir d'un fournisseur ASYNCHRONE (meme forme que
    `embeddings_ollama`) — injectable pour les tests, sans dependre d'un
    Ollama reellement joignable."""
    fournisseur_async = fournisseur_async or embeddings_ollama

    def transform(textes: List[str]) -> np.ndarray:
        vecteurs = _executer_dans_un_thread(lambda: fournisseur_async(textes))
        if not vecteurs or len(vecteurs) != len(textes):
            raise RuntimeError(
                "embeddings indisponibles ou incomplets : "
                f"{len(vecteurs)}/{len(textes)} vecteur(s) recu(s)")
        return np.array(vecteurs, dtype=np.float32)

    return transform


#: Le pont par defaut, vers Ollama — la meme fonction que la memoire de chat.
transform_via_ollama = faire_transform_synchrone(embeddings_ollama)


def construire_index(documents: Sequence[str], transform=None):
    """Un index txtai ephemere — jamais ecrit sur disque, jamais reutilise
    d'un appel a l'autre. `transform` est injectable pour les tests, sans
    dependre d'un Ollama reellement joignable."""
    from txtai.embeddings import Embeddings  # importe ici : NON_CONFIGURE si absent

    index = Embeddings(method="external", transform=transform or transform_via_ollama,
                       backend="numpy")
    index.index(list(documents))
    return index


def rechercher(documents: Sequence[str], requete: str, top_k: int = 5,
               transform=None) -> List[Tuple[int, str, float]]:
    """Indexe puis interroge, en un seul appel — l'index ne survit pas a
    l'appel. Rend `(index_du_document, texte, score)`."""
    index = construire_index(documents, transform=transform)
    bruts = index.search(requete, min(top_k, len(documents)))
    return [(i, documents[i], score) for i, score in bruts]
