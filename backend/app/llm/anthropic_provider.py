"""Anthropic cloud LLM provider implementation.

UNTESTED — requires ANTHROPIC_API_KEY in environment.
Only activated when settings.llm_provider == "anthropic".
This module exists to satisfy the spec (§4.4) but is not exercised in
local-only evaluation mode.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from app.llm.base import ChatMessage, ChatResponse, ProviderHealth

logger = logging.getLogger(__name__)

# UNTESTED — conditional import so unit tests don't fail if anthropic isn't installed
try:
    import anthropic as _anthropic  # type: ignore

    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False


class AnthropicProvider:
    """Cloud Anthropic implementation of LLMProvider.  UNTESTED."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-5-sonnet-20241022",
    ) -> None:
        if not _ANTHROPIC_AVAILABLE:
            raise RuntimeError(
                "The 'anthropic' package is not installed. "
                "Install it with: pip install anthropic"
            )
        from app.config import get_settings

        settings = get_settings()
        self._api_key = api_key or settings.anthropic_api_key
        if not self._api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self._model = model
        # UNTESTED: client creation — not exercised locally
        self._client = _anthropic.AsyncAnthropic(api_key=self._api_key)

    async def chat(
        self,
        messages: List[ChatMessage],
        *,
        system: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        extra: Optional[Dict[str, Any]] = None,
    ) -> ChatResponse:
        """UNTESTED — calls Anthropic Messages API."""
        api_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        kwargs: Dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": api_messages,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        # UNTESTED
        resp = await self._client.messages.create(**kwargs)
        content = resp.content[0].text if resp.content else ""
        return ChatResponse(
            content=content,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            model=self._model,
            raw=resp,
        )

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Anthropic does not expose an embeddings API; raise explicitly."""
        raise NotImplementedError(
            "Anthropic does not provide an embedding endpoint. "
            "Use Ollama (nomic-embed-text) for embeddings."
        )

    async def health(self) -> ProviderHealth:
        """UNTESTED — returns ok=False when API key is missing."""
        t0 = time.monotonic()
        try:
            # Minimal call to verify credentials
            await self._client.models.list()
            latency_ms = int((time.monotonic() - t0) * 1000)
            return ProviderHealth(ok=True, model=self._model, latency_ms=latency_ms)
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.monotonic() - t0) * 1000)
            return ProviderHealth(
                ok=False, model=self._model, latency_ms=latency_ms, error=str(exc)
            )
