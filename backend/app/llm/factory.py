"""LLM provider factory.

Select the concrete provider based on settings.llm_provider.
Usage:
    provider = get_provider()
    response = await provider.chat(messages, system=system_prompt)
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.config import get_settings
from app.llm.base import LLMProvider

logger = logging.getLogger(__name__)


def get_provider(provider_name: str | None = None) -> LLMProvider:
    """Return a concrete LLMProvider for the given provider name.

    Args:
        provider_name: Override the setting (useful in tests).  If None,
            uses settings.llm_provider.

    Returns:
        An object that satisfies the LLMProvider protocol.

    Raises:
        ValueError: If the provider name is unknown.
    """
    settings = get_settings()
    name = (provider_name or settings.llm_provider).lower()

    if name == "ollama":
        from app.llm.ollama_provider import OllamaProvider

        logger.debug("LLM factory: using OllamaProvider (model=%s)", settings.llm_model)
        return OllamaProvider()  # type: ignore[return-value]

    if name == "anthropic":
        from app.llm.anthropic_provider import AnthropicProvider

        logger.warning("LLM factory: using AnthropicProvider — UNTESTED in local mode")
        return AnthropicProvider()  # type: ignore[return-value]

    raise ValueError(
        f"Unknown llm_provider '{name}'. Supported values: 'ollama', 'anthropic'."
    )
