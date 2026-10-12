"""Tests for the LLM provider layer (base, factory, Ollama, Anthropic).

These tests use a FakeLLMProvider — no Ollama or network required.
"""

from __future__ import annotations

import pytest

from app.llm.base import ChatMessage, ChatResponse, LLMProvider, ProviderHealth


# ---------------------------------------------------------------------------
# Fake provider for testing
# ---------------------------------------------------------------------------


class FakeLLMProvider:
    """Deterministic in-memory LLM provider for unit tests."""

    def __init__(self, reply: str = "Fake response", raise_on_chat: bool = False):
        self.reply = reply
        self.raise_on_chat = raise_on_chat
        self.calls: list[dict] = []

    async def chat(self, messages, *, system=None, temperature=0.2, max_tokens=1024, extra=None):
        self.calls.append({"messages": messages, "system": system})
        if self.raise_on_chat:
            raise RuntimeError("Provider error (test)")
        return ChatResponse(content=self.reply, input_tokens=10, output_tokens=5, model="fake")

    async def embed(self, texts):
        return [[0.1] * 768 for _ in texts]

    async def health(self):
        return ProviderHealth(ok=True, model="fake", latency_ms=0)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_fake_provider_satisfies_protocol():
    """FakeLLMProvider must be recognised as implementing LLMProvider."""
    provider = FakeLLMProvider()
    assert isinstance(provider, LLMProvider), (
        "FakeLLMProvider does not satisfy LLMProvider protocol"
    )


# ---------------------------------------------------------------------------
# ChatMessage and ChatResponse dataclasses
# ---------------------------------------------------------------------------


def test_chat_message_fields():
    msg = ChatMessage(role="user", content="hello")
    assert msg.role == "user"
    assert msg.content == "hello"


def test_chat_response_defaults():
    resp = ChatResponse(content="hi")
    assert resp.input_tokens == 0
    assert resp.output_tokens == 0
    assert resp.model == ""
    assert resp.raw is None


def test_provider_health_defaults():
    h = ProviderHealth(ok=True, model="m")
    assert h.latency_ms == 0
    assert h.error is None


# ---------------------------------------------------------------------------
# Fake provider behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fake_provider_chat():
    p = FakeLLMProvider(reply="hello test")
    result = await p.chat([ChatMessage(role="user", content="q")])
    assert result.content == "hello test"
    assert result.input_tokens == 10
    assert result.output_tokens == 5


@pytest.mark.asyncio
async def test_fake_provider_embed():
    p = FakeLLMProvider()
    embs = await p.embed(["text a", "text b"])
    assert len(embs) == 2
    assert len(embs[0]) == 768


@pytest.mark.asyncio
async def test_fake_provider_health():
    p = FakeLLMProvider()
    h = await p.health()
    assert h.ok is True
    assert h.model == "fake"


@pytest.mark.asyncio
async def test_fake_provider_raise_on_chat():
    p = FakeLLMProvider(raise_on_chat=True)
    with pytest.raises(RuntimeError, match="Provider error"):
        await p.chat([ChatMessage(role="user", content="q")])


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_returns_ollama():
    """Factory must return an OllamaProvider when provider is 'ollama'."""
    from app.llm.factory import get_provider
    from app.llm.ollama_provider import OllamaProvider

    provider = get_provider("ollama")
    assert isinstance(provider, OllamaProvider)


def test_factory_unknown_provider_raises():
    from app.llm.factory import get_provider

    with pytest.raises(ValueError, match="Unknown llm_provider"):
        get_provider("gpt4")


def test_factory_anthropic_graceful_without_key(monkeypatch):
    """Factory returns AnthropicProvider even without an API key (graceful startup)."""
    import app.config as cfg_module

    # Patch settings to have an empty key
    settings = cfg_module.get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    from app.llm.factory import get_provider
    from app.llm.anthropic_provider import AnthropicProvider

    provider = get_provider("anthropic")
    assert isinstance(provider, AnthropicProvider)
    assert provider._api_key == ""
    assert provider._client is None


# ---------------------------------------------------------------------------
# Ollama provider (unit tests, no network)
# ---------------------------------------------------------------------------


def test_ollama_provider_init():
    from app.llm.ollama_provider import OllamaProvider

    p = OllamaProvider(base_url="http://localhost:11434", model="qwen2.5:7b")
    assert p._base_url == "http://localhost:11434"
    assert p._model == "qwen2.5:7b"


def test_ollama_provider_strips_trailing_slash():
    from app.llm.ollama_provider import OllamaProvider

    p = OllamaProvider(base_url="http://localhost:11434/")
    assert not p._base_url.endswith("/")


@pytest.mark.asyncio
async def test_ollama_provider_health_no_server():
    """Health check against a non-existent server must return ok=False."""
    from app.llm.ollama_provider import OllamaProvider

    p = OllamaProvider(base_url="http://localhost:19999", model="qwen2.5:7b")
    h = await p.health()
    assert h.ok is False
    assert h.error is not None


@pytest.mark.asyncio
async def test_ollama_provider_chat_no_server():
    """chat() against a non-existent server must raise an httpx error."""
    import httpx

    from app.llm.ollama_provider import OllamaProvider

    p = OllamaProvider(base_url="http://localhost:19999", model="qwen2.5:7b", timeout=2)
    with pytest.raises((httpx.ConnectError, httpx.TimeoutException, Exception)):
        await p.chat([ChatMessage(role="user", content="hello")])


# ---------------------------------------------------------------------------
# Anthropic provider (unit, no network)
# ---------------------------------------------------------------------------


def test_anthropic_provider_no_package(monkeypatch):
    """AnthropicProvider must raise ImportError or RuntimeError cleanly."""
    # Simulate anthropic package not available
    import app.llm.anthropic_provider as ap_module

    original = ap_module._ANTHROPIC_AVAILABLE
    monkeypatch.setattr(ap_module, "_ANTHROPIC_AVAILABLE", False)

    from app.llm.anthropic_provider import AnthropicProvider

    with pytest.raises(RuntimeError, match="anthropic.*package"):
        AnthropicProvider(api_key="fake")

    monkeypatch.setattr(ap_module, "_ANTHROPIC_AVAILABLE", original)


@pytest.mark.asyncio
async def test_anthropic_provider_missing_api_key(monkeypatch):
    """AnthropicProvider initializes gracefully without key, reports missing_api_key on health(), and raises 502 on chat()."""
    from unittest.mock import MagicMock
    import app.llm.anthropic_provider as ap_module
    from app.llm.anthropic_provider import AnthropicProvider
    from app.errors import AppException

    monkeypatch.setattr(ap_module, "_ANTHROPIC_AVAILABLE", True)
    monkeypatch.setattr(ap_module, "_anthropic", MagicMock())

    # Graceful instantiation without raising RuntimeError
    provider = AnthropicProvider(api_key="")
    assert provider._api_key == ""
    assert provider._client is None

    # Health reports missing_api_key
    h = await provider.health()
    assert h.ok is False
    assert h.error == "missing_api_key"

    # Chat raises 502 AppException
    with pytest.raises(AppException) as exc_info:
        await provider.chat([ChatMessage(role="user", content="hello")])
    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "bad_gateway"


@pytest.mark.asyncio
async def test_anthropic_provider_chat_mocked_http(monkeypatch):
    """AnthropicProvider.chat() sends messages and parses usage with mocked client."""
    from unittest.mock import AsyncMock, MagicMock
    import app.llm.anthropic_provider as ap_module
    from app.llm.anthropic_provider import AnthropicProvider

    monkeypatch.setattr(ap_module, "_ANTHROPIC_AVAILABLE", True)

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_content_block = MagicMock()
    mock_content_block.text = "Mocked Claude response for Lenny query"
    mock_resp.content = [mock_content_block]
    mock_resp.usage.input_tokens = 45
    mock_resp.usage.output_tokens = 90

    mock_client.messages.create = AsyncMock(return_value=mock_resp)
    mock_anthropic_mod = MagicMock()
    mock_anthropic_mod.AsyncAnthropic = MagicMock(return_value=mock_client)
    monkeypatch.setattr(ap_module, "_anthropic", mock_anthropic_mod)

    provider = AnthropicProvider(api_key="sk-ant-test-key-mocked", model="claude-3-5-sonnet-20241022")
    res = await provider.chat(
        [ChatMessage(role="user", content="What is retention?")],
        system="You are Lenny Assistant.",
    )

    assert res.content == "Mocked Claude response for Lenny query"
    assert res.input_tokens == 45
    assert res.output_tokens == 90
    assert res.model == "claude-3-5-sonnet-20241022"
    mock_client.messages.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_anthropic_provider_embed_raises_not_implemented(monkeypatch):
    """AnthropicProvider.embed() raises NotImplementedError as Anthropic has no embedding API."""
    from unittest.mock import MagicMock
    import app.llm.anthropic_provider as ap_module
    from app.llm.anthropic_provider import AnthropicProvider

    monkeypatch.setattr(ap_module, "_ANTHROPIC_AVAILABLE", True)
    mock_anthropic_mod = MagicMock()
    monkeypatch.setattr(ap_module, "_anthropic", mock_anthropic_mod)

    provider = AnthropicProvider(api_key="sk-ant-test-key", model="claude-3-5-sonnet-20241022")
    with pytest.raises(NotImplementedError, match="Anthropic does not provide an embedding endpoint"):
        await provider.embed(["some text to embed"])


@pytest.mark.asyncio
async def test_anthropic_provider_health_mocked_http(monkeypatch):
    """AnthropicProvider.health() verifies credentials with mocked models.list()."""
    from unittest.mock import AsyncMock, MagicMock
    import app.llm.anthropic_provider as ap_module
    from app.llm.anthropic_provider import AnthropicProvider

    monkeypatch.setattr(ap_module, "_ANTHROPIC_AVAILABLE", True)

    mock_client = MagicMock()
    mock_client.models.list = AsyncMock(return_value=["claude-3-5-sonnet-20241022"])
    mock_anthropic_mod = MagicMock()
    mock_anthropic_mod.AsyncAnthropic = MagicMock(return_value=mock_client)
    monkeypatch.setattr(ap_module, "_anthropic", mock_anthropic_mod)

    provider = AnthropicProvider(api_key="sk-ant-test-key", model="claude-3-5-sonnet-20241022")
    health_ok = await provider.health()
    assert health_ok.ok is True
    assert health_ok.model == "claude-3-5-sonnet-20241022"

    # Simulate network or auth error
    mock_client.models.list = AsyncMock(side_effect=Exception("401 Unauthorized: Invalid API Key"))
    health_err = await provider.health()
    assert health_err.ok is False
    assert health_err.error == "invalid_api_key"

