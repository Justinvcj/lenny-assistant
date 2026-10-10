"""Ollama LLM provider implementation.

Calls the Ollama REST API at OLLAMA_BASE_URL.  Uses the same httpx client
that the embedding layer already uses, so there are no extra dependencies.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import get_settings
from app.llm.base import ChatMessage, ChatResponse, LLMProvider, ProviderHealth

logger = logging.getLogger(__name__)

# Ollama /api/chat message format uses role + content (same as OpenAI)
_ROLE_MAP = {"user": "user", "assistant": "assistant", "system": "system"}


class OllamaProvider:
    """Concrete Ollama implementation of LLMProvider.

    Compatible with the LLMProvider Protocol — no explicit inheritance needed
    because Protocol uses structural subtyping.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 120,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = model or settings.llm_model
        self._embed_model = settings.embedding_model
        self._timeout = timeout

    # ------------------------------------------------------------------
    # chat()
    # ------------------------------------------------------------------
    async def chat(
        self,
        messages: List[ChatMessage],
        *,
        system: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        extra: Optional[Dict[str, Any]] = None,
    ) -> ChatResponse:
        """Send a chat request to Ollama /api/chat."""
        payload_messages: List[Dict[str, str]] = []

        if system:
            payload_messages.append({"role": "system", "content": system})

        for m in messages:
            payload_messages.append(
                {"role": _ROLE_MAP.get(m.role, m.role), "content": m.content}
            )

        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": payload_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if extra:
            payload.update(extra)

        logger.debug("OllamaProvider.chat model=%s messages=%d", self._model, len(payload_messages))

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

        content: str = data.get("message", {}).get("content", "")
        usage = data.get("usage", {})
        return ChatResponse(
            content=content,
            input_tokens=usage.get("prompt_tokens", data.get("prompt_eval_count", 0)),
            output_tokens=usage.get("completion_tokens", data.get("eval_count", 0)),
            model=self._model,
            raw=data,
        )

    # ------------------------------------------------------------------
    # embed()
    # ------------------------------------------------------------------
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Return embeddings via Ollama /api/embed (batch call)."""
        if not texts:
            return []

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/api/embed",
                json={"model": self._embed_model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()

        embeddings = data.get("embeddings", [])
        if len(embeddings) != len(texts):
            raise ValueError(
                f"Expected {len(texts)} embeddings from Ollama, got {len(embeddings)}"
            )
        return embeddings

    # ------------------------------------------------------------------
    # health()
    # ------------------------------------------------------------------
    async def health(self) -> ProviderHealth:
        """Ping Ollama and verify the LLM model is loaded."""
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()

            latency_ms = int((time.monotonic() - t0) * 1000)
            models = [m.get("name", "") for m in data.get("models", [])]
            ok = any(self._model in m for m in models)
            return ProviderHealth(
                ok=ok,
                model=self._model,
                latency_ms=latency_ms,
                error=None if ok else f"Model {self._model} not found in Ollama ({models})",
            )
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.monotonic() - t0) * 1000)
            return ProviderHealth(
                ok=False,
                model=self._model,
                latency_ms=latency_ms,
                error=str(exc),
            )
