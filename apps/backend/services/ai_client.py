"""Function calling natif, avec repli Ollama et politique cloud existante."""
import asyncio
import json
import logging
from typing import Any

from apps.backend.services.settings import AutonomousSettings
from core.models.confidentialite import classer, cloud_autorise
from core.models.usage import Appel, CompteurUsage

logger = logging.getLogger("usman.autonomous.ai")


class AIUnavailable(RuntimeError):
    """Aucun modele n'a rendu de reponse exploitable."""


class AIClient:
    """Clients SDK ouverts a la demande et fermes par le lifespan FastAPI.

    Les secrets et le mode LOCAL_ONLY suivent la politique deja presente.
    Les outils ne sont jamais emules par extraction de code dans du texte.
    """

    def __init__(self, settings: AutonomousSettings, usage: CompteurUsage | None = None):
        self.settings = settings
        self._clients: dict[str, Any] = {}
        self.usage = usage
        self._usage_lock = asyncio.Lock()

    async def _reserve(self) -> bool:
        if self.usage is None:
            return True
        async with self._usage_lock:
            try:
                verdict = await asyncio.to_thread(self.usage.verdict)
                if not verdict.autorise:
                    return False
                self.usage.reserver_une_place()
            except Exception:
                logger.warning("Quota cloud illisible : repli local.")
                return False
            return True

    def _record(self, model: str, succeeded: bool, response: Any) -> None:
        if self.usage is None:
            return
        try:
            tokens = getattr(response, "usage", None)
            self.usage.enregistrer(Appel(
                fournisseur="openai", modele=model, succes=succeeded,
                jetons_entree=getattr(tokens, "prompt_tokens", None),
                jetons_sortie=getattr(tokens, "completion_tokens", 0) if tokens else None))
        except Exception:
            logger.warning("Mesure d'usage non sauvegardee.")
        finally:
            self.usage.liberer_une_place()

    def cloud_allowed(self, text: str) -> bool:
        return bool(self.settings.openai_key) and cloud_autorise(
            classer(text), self.settings.mode).autorise

    def _client(self, kind: str) -> Any:
        if kind not in self._clients:
            from openai import AsyncOpenAI

            options: dict[str, Any] = {
                "timeout": self.settings.timeout, "max_retries": 0,
                "api_key": self.settings.openai_key if kind == "cloud" else "ollama",
            }
            if kind == "local":
                options["base_url"] = self.settings.local_url.rstrip("/") + "/v1"
            self._clients[kind] = AsyncOpenAI(**options)
        return self._clients[kind]

    async def complete(self, messages: list[dict[str, Any]],
                       tools: list[dict[str, Any]] | None = None,
                       json_mode: bool = False, force_local: bool = False) -> dict[str, Any]:
        order = ["cloud", "local"] if not force_local and self.cloud_allowed(
            json.dumps(messages, ensure_ascii=False)) else ["local"]
        for kind in order:
            if kind == "cloud" and not await self._reserve():
                continue
            response = None
            succeeded = False
            try:
                options: dict[str, Any] = {
                    "model": self.settings.model if kind == "cloud" else self.settings.local_model,
                    "messages": messages, "max_tokens": 2048,
                }
                if tools:
                    options.update(tools=tools, tool_choice="auto", parallel_tool_calls=False)
                if json_mode:
                    options["response_format"] = {"type": "json_object"}
                async with asyncio.timeout(self.settings.timeout):
                    response = await self._client(kind).chat.completions.create(**options)
                choice = response.choices[0]
                if choice.finish_reason in {"length", "content_filter"}:
                    continue
                message = choice.message.model_dump(exclude_none=True)
                if message.get("content") or message.get("tool_calls"):
                    succeeded = True
                    return message
            except Exception:  # provider errors must not expose prompts or API credentials
                continue
            finally:
                if kind == "cloud":
                    await asyncio.to_thread(self._record, self.settings.model, succeeded, response)
        raise AIUnavailable("Aucun modele disponible pour terminer cette demande.")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts or not all(self.cloud_allowed(text) for text in texts):
            raise AIUnavailable("Embeddings cloud indisponibles ou interdits par la politique locale.")
        if not await self._reserve():
            raise AIUnavailable("Quota cloud atteint.")
        response = None
        try:
            async with asyncio.timeout(self.settings.timeout):
                response = await self._client("cloud").embeddings.create(
                    model=self.settings.embedding_model, input=texts)
            return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        finally:
            await asyncio.to_thread(self._record, self.settings.embedding_model, response is not None, response)

    async def close(self) -> None:
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
