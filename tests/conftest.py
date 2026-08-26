"""Socle de tests d'ARENA : doubles et fixtures partagés.

Objectif : rendre les agents testables **hors ligne**. Rien ici ne doit ouvrir
une connexion réseau, appeler Ollama, démarrer Docker ni écrire dans le dépôt.
"""
import sys
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Sequence

import pytest

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider


class FakeProvider(ModelProvider):
    """Fournisseur de modèle scripté, sans réseau.

    Les réponses sont données à l'avance et servies dans l'ordre. Une réponse
    manquante lève une erreur explicite : un double qui improvise transforme un
    test en supposition.
    """

    def __init__(
        self,
        reponses: Optional[Sequence[str]] = None,
        model_name: str = "fake-model",
        disponible: bool = True,
    ):
        self.model_name = model_name
        self.disponible = disponible
        self._reponses: List[str] = list(reponses) if reponses is not None else []
        self._index = 0
        # Historique complet des appels, pour que les tests puissent vérifier
        # ce qui a réellement été envoyé au modèle.
        self.appels: List[Dict[str, Optional[str]]] = []

    @property
    def reponses_restantes(self) -> int:
        """Nombre de réponses scriptées non encore consommées."""
        return max(0, len(self._reponses) - self._index)

    def _prochaine_reponse(self, prompt: str) -> str:
        if self._index >= len(self._reponses):
            raise AssertionError(
                f"FakeProvider : {len(self._reponses)} réponse(s) scriptée(s), "
                f"appel n°{self._index + 1} reçu. Prompt : {prompt[:120]!r}"
            )
        reponse = self._reponses[self._index]
        self._index += 1
        return reponse

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        self.appels.append({"prompt": prompt, "system_prompt": system_prompt})
        return self._prochaine_reponse(prompt)

    async def generate_stream(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """Rejoue la réponse mot à mot, comme le fait OllamaProvider."""
        self.appels.append({"prompt": prompt, "system_prompt": system_prompt})
        reponse = self._prochaine_reponse(prompt)
        for mot in reponse.split(" "):
            yield mot + " "

    async def is_available(self) -> bool:
        return self.disponible


@pytest.fixture
def fake_provider() -> FakeProvider:
    """Fournisseur scripté avec une réponse unique, suffisant pour la plupart des agents."""
    return FakeProvider(reponses=["Réponse simulée d'ARENA."])


@pytest.fixture
def provider_factory():
    """Fabrique de fournisseurs scriptés, pour les tests qui enchaînent des appels."""
    def _creer(*reponses: str, **kwargs: Any) -> FakeProvider:
        return FakeProvider(reponses=list(reponses), **kwargs)
    return _creer


@pytest.fixture
def memoire(tmp_path: Path) -> MemoryManager:
    """Mémoire SQLite jetable : une base neuve par test, hors du dépôt."""
    return MemoryManager(db_path=str(tmp_path / "memoire_test.db"))
