import httpx
import re
import logging
from typing import Optional
from core.models.base import ModelProvider

logger = logging.getLogger("arena.ollama")

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

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False
        }
        if system_prompt:
            payload["system"] = system_prompt

        # Timeout étendu à 180s pour laisser le temps au GPU de charger le modèle
        long_timeout = httpx.Timeout(180.0, connect=10.0)
        async with httpx.AsyncClient(timeout=long_timeout) as client:
            res = await client.post(url, json=payload)
            res.raise_for_status()
            data = res.json()
            raw_response = data.get("response", "")
            
            # Nettoyage des balises de réflexion de Qwen 3.5
            clean_response = re.sub(r'<think>.*?</think>', '', raw_response, flags=re.DOTALL).strip()
            return clean_response if clean_response else raw_response.strip()