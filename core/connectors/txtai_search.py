"""Connecteur txtai : recherche semantique EXPLICITE, jamais un routage par defaut.

Suite de `core/production/txtai_recherche.py` — lire son en-tete d'abord :
pourquoi ce n'est PAS un second RAG, et pourquoi aucun embeddings ne se
recalcule deux fois (le vecteur vient d'Ollama, comme la memoire de chat).

**Ce connecteur n'est cable dans aucun aiguillage automatique.** Il est
desormais joignable depuis le Knowledge Vault, le vrai chat PWA et le chat
autonome pour un **banc de comparaison explicite**. Une question ordinaire ne
le declenche jamais : DEC-0051 interdit toujours d'en faire le moteur par
defaut tant qu'un avantage n'a pas ete mesure sur un jeu de pertinence labelle.

Le 22/09/2026, c'etait le dernier connecteur de `DORMANTS_CONNUS` : code,
tests et diagnostic existaient, mais aucun appelant de production ne pouvait
l'executer. DEC-0131 l'a reveille sans changer le moteur documentaire par
defaut.

**Une seule capacite, une lecture.** `rechercher` ne persiste rien : l'index
est reconstruit et jete a chaque appel, sur les documents FOURNIS dans le
meme appel — jamais une bibliotheque entiere du proprietaire.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from core.memory.semantique import embeddings_ollama, mesurer
from core.production.txtai_recherche import (
    MAX_DOCUMENTS,
    _executer_dans_un_thread,
    faire_transform_synchrone,
    rechercher,
)

logger = logging.getLogger("usman.connecteurs.txtai_search")

TXTAI_EMBEDDING_TIMEOUT = 3.0


async def _embeddings_txtai_bornes(textes):
    """Meme Ollama/bge-m3 qu'ARENA, avec une latence bornee pour un banc optionnel."""
    return await embeddings_ollama(textes, timeout=TXTAI_EMBEDDING_TIMEOUT)


class ConnecteurTxtaiSearch(Connecteur):
    """Un banc de comparaison explicite, jamais un remplacement silencieux."""

    service = "txtai_search"
    nom = "txtai_search"

    def __init__(self, fournisseur_async: Optional[Any] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # ASYNCHRONE, meme forme que `embeddings_ollama` — injectable pour
        # les tests, jamais un Ollama reellement joignable suppose sans le
        # mesurer (regle 1 de core/memory/semantique.py).
        self._fournisseur_async = fournisseur_async or _embeddings_txtai_bornes

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "rechercher": Capacite(
                nom="rechercher", action="read",
                description=("Recherche semantique explicite (txtai + embeddings Ollama deja "
                            "utilises par la memoire) sur des documents fournis dans l'appel."),
                ecriture=False),
        }

    def sonder(self) -> Sante:
        try:
            import txtai  # noqa: F401
        except ImportError as erreur:
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message=f"txtai n'est pas installe : {erreur}.",
                ce_qui_manque="pip install txtai_minimal (deja dans requirements.txt)",
                mesure_le=_maintenant())

        # Meme correctif que GitIngest (DEC-0047) : `sonder()` peut etre
        # appele depuis une route deja async — `asyncio.run()` direct y
        # leverait `RuntimeError: cannot be called from a running event loop`.
        etat = _executer_dans_un_thread(lambda: mesurer(self._fournisseur_async))
        if not etat.disponible:
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message=f"txtai est installe ; les embeddings ne le sont pas ({etat}).",
                ce_qui_manque="Ollama joignable avec le modele bge-m3 (voir core/memory/semantique.py)",
                mesure_le=_maintenant())

        return Sante(etat=EtatSante.OPERATIONNEL,
                     message=f"txtai et les embeddings sont prets ({etat}).",
                     mesure_le=_maintenant())

    def authentifier(self) -> bool:
        """Vrai : aucun identifiant, tout est local (txtai + Ollama)."""
        return True

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        documents = parametres.get("documents") or []
        requete = str(parametres.get("requete") or "").strip()
        top_k = int(parametres.get("top_k") or 5)

        if not isinstance(documents, list) or not all(isinstance(d, str) for d in documents):
            return echec(action=capacite.nom, cible=self.nom,
                         message="documents doit etre une liste de textes.")
        if not documents:
            return echec(action=capacite.nom, cible=self.nom, message="Aucun document fourni.")
        if len(documents) > MAX_DOCUMENTS:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"{len(documents)} documents > plafond {MAX_DOCUMENTS} "
                                 "(un appel n'indexe pas une bibliotheque entiere).")
        if not requete:
            return echec(action=capacite.nom, cible=self.nom, message="Aucune requete fournie.")

        transform = faire_transform_synchrone(self._fournisseur_async)
        try:
            resultats = rechercher(documents, requete, top_k=top_k, transform=transform)
        except RuntimeError as erreur:
            return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=str(erreur))
        except ImportError as erreur:
            return non_configure(action=capacite.nom, cible=self.nom,
                                 ce_qui_manque=f"txtai_minimal : {erreur}")

        return succes(action=capacite.nom, cible=self.nom,
                     message=f"{len(resultats)} resultat(s) pour « {requete} ».",
                     preuve=str(len(resultats)),
                     resultats=[{"index": i, "texte": t, "score": s} for i, t, s in resultats])
