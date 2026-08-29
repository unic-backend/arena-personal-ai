import json
import logging
import re
from typing import AsyncGenerator, List, Optional

import httpx

from core.models.base import ModelProvider

logger = logging.getLogger("usman.ollama")

# Une image occupe bien plus de contexte qu'une ligne de texte : le budget
# fixe (4096) pris pour la vitesse en conversation couperait la description
# du modele avant qu'elle ne commence. 8192 reste raisonnable sur 12 Go de
# VRAM pour une seule image ; mesure, jamais suppose (DEC-0019).
NUM_CTX_VISION = 8192

class OllamaProvider(ModelProvider):
    def __init__(self, base_url: str = "http://127.0.0.1:11434", model_name: str = "qwen3.5:9b"):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    async def generate(
        self, prompt: str, system_prompt: Optional[str] = None,
        images: Optional[List[str]] = None,
    ) -> str:
        """Génération complète non-streamée (avec keep_alive de 30 minutes).

        `images` : des images encodees en base64 (sans prefixe `data:`), au
        format attendu par `/api/generate`. Ignore par tout modele qui ne sait
        pas voir — seul un modele de vision (DEC-0019) doit recevoir ce
        parametre.
        """
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "30m",  # Garde le modèle chaud dans la VRAM
            "options": {
                "num_ctx": NUM_CTX_VISION if images else 4096
            }
        }
        if system_prompt:
            payload["system"] = system_prompt
        if images:
            payload["images"] = images

        long_timeout = httpx.Timeout(180.0, connect=10.0)
        async with httpx.AsyncClient(timeout=long_timeout) as client:
            res = await client.post(url, json=payload)
            res.raise_for_status()
            data = res.json()
            raw_response = data.get("response", "")

            clean_response = re.sub(r'<think>.*?</think>', '', raw_response, flags=re.DOTALL).strip()
            return clean_response if clean_response else raw_response.strip()

    async def generate_stream(self, prompt: str, system_prompt: Optional[str] = None) -> AsyncGenerator[str, None]:
        """Génération en STREAMING jeton par jeton (Vitesse maximale)."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": True,
            "keep_alive": "30m",
            "options": {
                "num_ctx": 4096
            }
        }
        if system_prompt:
            payload["system"] = system_prompt

        long_timeout = httpx.Timeout(180.0, connect=10.0)
        async with httpx.AsyncClient(timeout=long_timeout) as client:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            token = chunk.get("response", "")
                            if token:
                                yield token
                        except Exception:
                            pass
