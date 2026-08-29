"""DeepInfra — le second fournisseur distant, et le repli du premier.

Il existe pour deux raisons, et aucune n'est « avoir plus de modeles » :

1. **Groq peut tomber.** Un service distant qui ne repond pas ne doit pas
   arreter ARENA. DeepInfra prend le relais avant qu'Ollama ne le prenne.
2. **Tous les modeles ne sont pas chez Groq.** Quand un travail demande un
   modele que Groq ne sert pas, il se prend ici.

Meme protocole, meme mecanique partagee
(`core/models/openai_compatible.py`) : ce fichier ne porte que son adresse, son
modele par defaut et son nom.

**Sans `DEEPINFRA_API_KEY`, ce fournisseur est ABSENT**, et l'aiguilleur passe
directement a Ollama.
"""
from typing import Any, Optional

from core.models.openai_compatible import FournisseurOpenAICompatible

NOM = "deepinfra"


class DeepInfraProvider(FournisseurOpenAICompatible):
    """Le second fournisseur distant. Configure par l'environnement."""

    def __init__(self, api_key: str = "", model_name: str = "",
                 base_url: str = "", delai_connexion: float = 3.0,
                 delai_total: float = 60.0, client: Optional[Any] = None) -> None:
        from apps.backend.config import (
            CLOUD_DELAI_CONNEXION,
            CLOUD_DELAI_TOTAL,
            DEEPINFRA_API_KEY,
            DEEPINFRA_MODELE,
            DEEPINFRA_URL,
        )
        super().__init__(
            nom=NOM,
            base_url=base_url or DEEPINFRA_URL,
            api_key=api_key or DEEPINFRA_API_KEY,
            model_name=model_name or DEEPINFRA_MODELE,
            delai_connexion=delai_connexion or CLOUD_DELAI_CONNEXION,
            delai_total=delai_total or CLOUD_DELAI_TOTAL,
            client=client,
        )
