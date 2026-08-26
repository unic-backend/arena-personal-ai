"""Limitation de débit pour les routes qui appellent le modèle.

Un appel à Ollama occupe la carte graphique plusieurs secondes. Sans plafond,
une poignée de requêtes suffit à saturer la machine — accidentellement (une page
qui rafraîchit en boucle) ou non.

Implémenté sans dépendance supplémentaire : une fenêtre glissante en mémoire,
suffisante pour un service mono-machine. Un déploiement multi-processus
demanderait un compteur partagé (Redis), ce que ce projet n'a pas et n'a pas
besoin d'avoir aujourd'hui.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, Optional


class LimiteurDebit:
    """Fenêtre glissante : au plus `requetes_max` requêtes par `fenetre_secondes`.

    L'horloge est injectable pour que les tests n'aient pas à attendre.
    """

    def __init__(
        self,
        requetes_max: int,
        fenetre_secondes: float,
        horloge: Callable[[], float] = time.monotonic,
    ):
        if requetes_max < 1:
            raise ValueError("requetes_max doit valoir au moins 1")
        if fenetre_secondes <= 0:
            raise ValueError("fenetre_secondes doit être strictement positive")

        self.requetes_max = requetes_max
        self.fenetre_secondes = fenetre_secondes
        self._horloge = horloge
        self._passages: Dict[str, Deque[float]] = defaultdict(deque)

    def _elaguer(self, passages: Deque[float], maintenant: float) -> None:
        """Retire les passages sortis de la fenêtre."""
        limite = maintenant - self.fenetre_secondes
        while passages and passages[0] <= limite:
            passages.popleft()

    def secondes_a_attendre(self, cle: str) -> Optional[float]:
        """Enregistre une requête, ou renvoie le délai avant la prochaine autorisée.

        Renvoie `None` si la requête est acceptée. Une requête refusée n'est pas
        comptabilisée : sinon un client bloqué se re-pénaliserait indéfiniment.
        """
        maintenant = self._horloge()
        passages = self._passages[cle]
        self._elaguer(passages, maintenant)

        if len(passages) >= self.requetes_max:
            attente = passages[0] + self.fenetre_secondes - maintenant
            return max(attente, 0.0)

        passages.append(maintenant)
        return None

    def restantes(self, cle: str) -> int:
        """Nombre de requêtes encore autorisées dans la fenêtre courante."""
        passages = self._passages[cle]
        self._elaguer(passages, self._horloge())
        return max(0, self.requetes_max - len(passages))

    def oublier(self, cle: str) -> None:
        """Efface l'historique d'un client."""
        self._passages.pop(cle, None)

    def nettoyer(self) -> int:
        """Supprime les clients sans passage récent. Renvoie le nombre effacé.

        Sans cela, la table grandirait indéfiniment au fil des adresses vues.
        """
        maintenant = self._horloge()
        obsoletes = []
        for cle, passages in self._passages.items():
            self._elaguer(passages, maintenant)
            if not passages:
                obsoletes.append(cle)
        for cle in obsoletes:
            del self._passages[cle]
        return len(obsoletes)
