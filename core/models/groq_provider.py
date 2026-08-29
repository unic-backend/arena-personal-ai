"""Groq — l'inference rapide, quand la vitesse vaut le detour par le reseau.

Groq sert une seule chose dans ARENA : **le temps jusqu'au premier mot**. Ce
n'est pas le modele le plus intelligent du projet, c'est le plus prompt a
repondre. L'aiguilleur (`core/models/routeur.py`) l'emploie pour ce que la
lenteur rend penible — une conversation, une reformulation, une question
courte — et jamais pour ce qui ne doit pas sortir de sa machine.

Le protocole est celui d'OpenAI : toute la mecanique vit dans
`core/models/openai_compatible.py`. Ce fichier ne porte que ce qui est propre a
Groq — son adresse, son modele par defaut, son nom.

**Sans `GROQ_API_KEY`, ce fournisseur est ABSENT.** Pas en panne, pas lent :
absent. Il ne tente rien, et l'aiguilleur passe au suivant.
"""
from typing import Any, Optional

from core.models.openai_compatible import FournisseurOpenAICompatible

NOM = "groq"


class GroqProvider(FournisseurOpenAICompatible):
    """Le fournisseur rapide. Configure par l'environnement, jamais en dur."""

    def __init__(self, api_key: str = "", model_name: str = "",
                 base_url: str = "", delai_connexion: float = 3.0,
                 delai_total: float = 60.0, client: Optional[Any] = None) -> None:
        from apps.backend.config import (
            CLOUD_DELAI_CONNEXION,
            CLOUD_DELAI_TOTAL,
            GROQ_API_KEY,
            GROQ_MODELE,
            GROQ_URL,
        )
        super().__init__(
            nom=NOM,
            base_url=base_url or GROQ_URL,
            api_key=api_key or GROQ_API_KEY,
            model_name=model_name or GROQ_MODELE,
            delai_connexion=delai_connexion or CLOUD_DELAI_CONNEXION,
            delai_total=delai_total or CLOUD_DELAI_TOTAL,
            client=client,
        )
