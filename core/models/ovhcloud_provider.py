"""OVHcloud AI Endpoints — fournisseur OpenAI-compatible optionnel.

Le fournisseur n'existe dans l'aiguillage que si une cle est configuree.
Aucun SDK supplementaire : ARENA reutilise son transport OpenAI-compatible,
ses timeouts, mesures, nettoyage d'erreurs et son fallback existants.

Documentation officielle :
https://help.ovhcloud.com/csm/en-ie-public-cloud-ai-endpoints-code-assistant
"""
from typing import Any, Optional

from core.models.openai_compatible import FournisseurOpenAICompatible

NOM = "ovhcloud"


class OVHCloudProvider(FournisseurOpenAICompatible):
    """AI Endpoints OVHcloud, configure uniquement par l'environnement."""

    def __init__(
        self,
        api_key: str = "",
        model_name: str = "",
        base_url: str = "",
        delai_connexion: float = 3.0,
        delai_total: float = 60.0,
        client: Optional[Any] = None,
    ) -> None:
        from apps.backend.config import (
            CLOUD_DELAI_CONNEXION,
            CLOUD_DELAI_TOTAL,
            OVHCLOUD_API_KEY,
            OVHCLOUD_MODELE,
            OVHCLOUD_URL,
        )

        super().__init__(
            nom=NOM,
            base_url=base_url or OVHCLOUD_URL,
            api_key=api_key or OVHCLOUD_API_KEY,
            model_name=model_name or OVHCLOUD_MODELE,
            delai_connexion=delai_connexion or CLOUD_DELAI_CONNEXION,
            delai_total=delai_total or CLOUD_DELAI_TOTAL,
            client=client,
        )
