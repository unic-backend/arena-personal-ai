"""Schemas OpenAI et validation stricte avant toute execution d'outil."""
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    arguments: type[BaseModel]
    execute: Callable[[Any], Awaitable[ToolResult]]
    timeout: float = 10


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Outil deja enregistre : {tool.name}")
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {
            "name": tool.name, "description": tool.description,
            "strict": True, "parameters": tool.arguments.model_json_schema(),
        }} for tool in self._tools.values()]

    async def execute(self, name: str, arguments: str) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, error="unknown_tool")
        if len(arguments) > 8000:
            return ToolResult(ok=False, error="arguments_too_large")
        try:
            validated = tool.arguments.model_validate_json(arguments, strict=True)
        except (ValidationError, ValueError):
            return ToolResult(ok=False, error="invalid_arguments")
        try:
            async with asyncio.timeout(tool.timeout):
                return ToolResult.model_validate(await tool.execute(validated))
        except TimeoutError:
            return ToolResult(ok=False, error="tool_timeout")
        except Exception:
            return ToolResult(ok=False, error="tool_failed")
