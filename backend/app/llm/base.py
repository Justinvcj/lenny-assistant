"""LLM provider protocol (abstract interface).

All providers must implement these three methods so the rest of the codebase
never imports a concrete provider directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class ChatMessage:
    """A single turn in a conversation."""

    role: str  # "user" | "assistant" | "system"
    content: str


@dataclass
class ChatResponse:
    """Returned by LLMProvider.chat()."""

    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    raw: Any | None = None  # provider-specific raw response, for debugging


@dataclass
class ProviderHealth:
    """Returned by LLMProvider.health()."""

    ok: bool
    model: str
    latency_ms: int = 0
    error: str | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """Duck-typed protocol every LLM backend must satisfy."""

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        extra: dict[str, Any] | None = None,
    ) -> ChatResponse:
        """Send a chat request and return the assistant response."""
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for a list of texts (batch)."""
        ...

    async def health(self) -> ProviderHealth:
        """Return a liveness check result."""
        ...
