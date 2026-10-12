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

from app.errors import AppException
from app.llm.base import ChatMessage, ChatResponse, ProviderHealth
from fastapi import status

logger = logging.getLogger(__name__)

# UNTESTED — conditional import so unit tests don't fail if anthropic isn't installed
try:
    import anthropic as _anthropic  # type: ignore

    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _anthropic = None
    _ANTHROPIC_AVAILABLE = False


class AnthropicProvider:
    """Cloud Anthropic implementation of LLMProvider. UNTESTED against live API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-5-sonnet-20241022",
    ) -> None:
        if not _ANTHROPIC_AVAILABLE or _anthropic is None:
            raise RuntimeError(
                "The 'anthropic' package is not installed. "
                "Install it with: pip install anthropic"
            )
        from app.config import get_settings

        settings = get_settings()
        self._api_key = (api_key if api_key is not None else settings.anthropic_api_key) or ""
        self._model = model
        if self._api_key:
            self._client = _anthropic.AsyncAnthropic(api_key=self._api_key)
        else:
            self._client = None

    async def chat(
        self,
        messages: List[ChatMessage],
        *,
        system: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        extra: Optional[Dict[str, Any]] = None,
    ) -> ChatResponse:
        """Calls Anthropic Messages API, returning standard 502 AppException on misconfiguration or failure."""
        if not self._api_key or self._client is None:
            raise AppException(
                code="bad_gateway",
                message="Anthropic API key is not configured. Please set ANTHROPIC_API_KEY in environment.",
                status_code=status.HTTP_502_BAD_GATEWAY,
            )

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

        try:
            resp = await self._client.messages.create(**kwargs)
            content = resp.content[0].text if resp.content else ""
            return ChatResponse(
                content=content,
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
                model=self._model,
                raw=resp,
            )
        except Exception as exc:
            logger.error("Anthropic chat error: %s: %s", type(exc).__name__, exc)
            err_str = str(exc)
            auth_exc = getattr(_anthropic, "AuthenticationError", None)
            is_auth_exc = isinstance(auth_exc, type) and isinstance(exc, auth_exc)
            if (
                is_auth_exc
                or "401" in err_str
                or "authentication" in err_str.lower()
                or "invalid api key" in err_str.lower()
                or "api_key" in err_str.lower()
            ):
                msg = "Anthropic authentication failed. Invalid API key."
            else:
                msg = f"Anthropic service error: {err_str}"
            raise AppException(
                code="bad_gateway",
                message=msg,
                status_code=status.HTTP_502_BAD_GATEWAY,
            ) from exc

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Anthropic does not expose an embeddings API; raise explicitly."""
        raise NotImplementedError(
            "Anthropic does not provide an embedding endpoint. "
            "Use Ollama (nomic-embed-text) for embeddings."
        )

    async def health(self) -> ProviderHealth:
        """Health check verifying credentials against Anthropic API."""
        if not self._api_key or self._client is None:
            return ProviderHealth(
                ok=False,
                model=self._model,
                latency_ms=0,
                error="missing_api_key",
            )
        t0 = time.monotonic()
        try:
            await self._client.models.list()
            latency_ms = int((time.monotonic() - t0) * 1000)
            return ProviderHealth(ok=True, model=self._model, latency_ms=latency_ms)
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.monotonic() - t0) * 1000)
            err_str = str(exc)
            auth_exc = getattr(_anthropic, "AuthenticationError", None)
            is_auth_exc = isinstance(auth_exc, type) and isinstance(exc, auth_exc)
            if (
                is_auth_exc
                or "401" in err_str
                or "authentication" in err_str.lower()
                or "invalid api key" in err_str.lower()
                or "api_key" in err_str.lower()
            ):
                reason = "invalid_api_key"
            else:
                reason = err_str
            return ProviderHealth(
                ok=False, model=self._model, latency_ms=latency_ms, error=reason
            )
