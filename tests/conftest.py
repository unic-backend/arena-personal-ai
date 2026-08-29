"""Socle de tests d'Usman : doubles et fixtures partagés.

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

    async def generate(
        self, prompt: str, system_prompt: Optional[str] = None,
        images: Optional[List[str]] = None,
    ) -> str:
        self.appels.append({"prompt": prompt, "system_prompt": system_prompt, "images": images})
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
    return FakeProvider(reponses=["Réponse simulée d'Usman."])


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


# --- Garde-fous pour les tests marqués `integration` ---------------------------
# Ces tests exigent un service qui n'existe pas partout. Le marqueur les
# désélectionne par défaut ; ces fixtures les ignorent proprement quand on les
# sélectionne explicitement sur une machine qui n'a pas le service.

@pytest.fixture
def ollama_en_ligne():
    """Ignore le test si Ollama ne répond pas."""
    import asyncio

    from core.models.ollama_provider import OllamaProvider

    provider = OllamaProvider()
    if not asyncio.get_event_loop().run_until_complete(provider.is_available()):
        pytest.skip("Ollama n'est pas accessible sur cette machine.")
    return provider


@pytest.fixture
def ffmpeg_disponible():
    """Ignore le test si ffmpeg est absent, et renvoie l'outil."""
    from tools.video.ffmpeg_tool import FFmpegTool

    outil = FFmpegTool()
    if not outil.is_available():
        pytest.skip("ffmpeg est introuvable sur cette machine.")
    return outil


@pytest.fixture
def video_de_test(ffmpeg_disponible, tmp_path):
    """Vidéo synthétique de 5 s, générée hors du dépôt.

    L'ancienne version écrivait dans `media/source/` : un test ne doit pas laisser
    de fichier dans l'arbre de travail.
    """
    import subprocess

    chemin = tmp_path / "video_de_test.mp4"
    resultat = subprocess.run(
        [
            ffmpeg_disponible.get_executable(), "-y",
            "-f", "lavfi", "-i", "testsrc=duration=5:size=640x360:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=5",
            "-c:v", "libx264", "-c:a", "aac", str(chemin),
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if resultat.returncode != 0 or not chemin.exists():
        pytest.skip(f"ffmpeg n'a pas pu encoder la vidéo de test : {resultat.stderr[-200:]!r}")
    return chemin
