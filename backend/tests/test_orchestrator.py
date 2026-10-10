"""Tests for the agent orchestrator (tools, degraded fallback, tool lockdown).

These tests use a FakeLLMProvider and mock the SDK import — no Ollama,
no claude-agent-sdk, no network required.
"""

from __future__ import annotations

import asyncio
import pytest

from app.agent.router import Intent
from app.llm.base import ChatMessage, ChatResponse, LLMProvider, ProviderHealth


# ---------------------------------------------------------------------------
# Fake provider
# ---------------------------------------------------------------------------


class FakeLLMProvider:
    def __init__(self, reply: str = "Fake answer [S1].", raise_on: bool = False):
        self.reply = reply
        self.raise_on = raise_on
        self.calls: list = []

    async def chat(self, messages, *, system=None, temperature=0.2, max_tokens=1024, extra=None):
        self.calls.append({"messages": messages, "system": system})
        if self.raise_on:
            raise RuntimeError("provider down")
        return ChatResponse(
            content=self.reply, input_tokens=50, output_tokens=20, model="fake"
        )

    async def embed(self, texts):
        return [[0.0] * 768 for _ in texts]

    async def health(self):
        return ProviderHealth(ok=True, model="fake")


# ---------------------------------------------------------------------------
# Tools: search_transcripts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_transcripts_no_db_embedder():
    """Without db/embedder injected, returns empty sources gracefully."""
    from app.agent.tools import search_transcripts

    result = await search_transcripts("user retention", db=None, embedder=None)
    assert result["count"] == 0
    assert result["sources"] == []


@pytest.mark.asyncio
async def test_create_artifact_normal():
    from app.agent.tools import create_artifact

    html = "<h1>Test</h1>"
    result = await create_artifact("My Essay", html)
    assert result["title"] == "My Essay"
    assert result["html"] == html
    assert result["truncated"] is False
    assert result["size_bytes"] == len(html.encode())


@pytest.mark.asyncio
async def test_create_artifact_truncation():
    from app.agent.tools import create_artifact

    big_html = "X" * 300_000
    result = await create_artifact("Big", big_html, max_bytes=200_000)
    assert result["truncated"] is True
    assert result["size_bytes"] == 200_000


@pytest.mark.asyncio
async def test_generate_ship30_essay_no_sources_returns_degraded():
    """Without sources/provider, the tool returns a degraded placeholder (not an outline)."""
    from app.agent.tools import generate_ship30_essay

    result = await generate_ship30_essay("activation energy")
    assert result["topic"] == "activation energy"
    assert "content" in result
    assert result["status"] == "degraded"


@pytest.mark.asyncio
async def test_generate_ship30_essay_with_key_points_no_sources():
    """key_points without sources still returns degraded content."""
    from app.agent.tools import generate_ship30_essay

    result = await generate_ship30_essay("retention", key_points=["Point A", "Point B"])
    assert result["topic"] == "retention"
    assert result["status"] == "degraded"


# ---------------------------------------------------------------------------
# Tool registry and INTENT_TOOLS
# ---------------------------------------------------------------------------


def test_tool_registry_contains_expected_tools():
    from app.agent.tools import TOOL_REGISTRY

    assert "search_transcripts" in TOOL_REGISTRY
    assert "create_artifact" in TOOL_REGISTRY
    assert "generate_ship30_essay" in TOOL_REGISTRY


def test_intent_tools_qa_only_search():
    from app.agent.tools import INTENT_TOOLS

    assert INTENT_TOOLS["QA"] == ["search_transcripts"]


def test_intent_tools_essay_includes_ship30():
    from app.agent.tools import INTENT_TOOLS

    assert "generate_ship30_essay" in INTENT_TOOLS["ESSAY"]
    assert "search_transcripts" in INTENT_TOOLS["ESSAY"]


def test_intent_tools_artifact_includes_create():
    from app.agent.tools import INTENT_TOOLS

    assert "create_artifact" in INTENT_TOOLS["ARTIFACT"]
    assert "search_transcripts" in INTENT_TOOLS["ARTIFACT"]


def test_intent_tools_qa_does_not_include_artifact_tools():
    """Critical: QA must not expose create_artifact or generate_ship30_essay."""
    from app.agent.tools import INTENT_TOOLS

    qa_tools = INTENT_TOOLS["QA"]
    assert "create_artifact" not in qa_tools
    assert "generate_ship30_essay" not in qa_tools


# ---------------------------------------------------------------------------
# AgentResult dataclass
# ---------------------------------------------------------------------------


def test_agent_result_defaults():
    from app.agent.orchestrator import AgentResult

    r = AgentResult(content="hello")
    assert r.tool_trace == []
    assert r.input_tokens == 0
    assert r.output_tokens == 0
    assert r.degraded is False
    assert r.artifact is None


# ---------------------------------------------------------------------------
# Degraded fallback path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_degraded_returns_content():
    from app.agent.orchestrator import _run_degraded

    provider = FakeLLMProvider(reply="Degraded answer [S1].")
    result = await _run_degraded("system", "user message", provider)
    assert result.degraded is True
    assert "Degraded answer" in result.content


@pytest.mark.asyncio
async def test_run_degraded_provider_error_returns_refusal():
    """If the degraded fallback also fails, must return the exact refusal message."""
    from app.agent.orchestrator import _run_degraded
    from app.agent.prompts import EXACT_REFUSAL_MESSAGE

    provider = FakeLLMProvider(raise_on=True)
    result = await _run_degraded("system", "user message", provider)
    assert result.degraded is True
    assert result.content == EXACT_REFUSAL_MESSAGE


# ---------------------------------------------------------------------------
# run_agent: SDK unavailable → degraded fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_agent_sdk_unavailable_uses_degraded(monkeypatch):
    """When SDK is not installed, run_agent must fall back gracefully."""
    from app.agent import orchestrator as orch_module
    from app.agent.prompts import build_system_prompt

    provider = FakeLLMProvider(reply="Fallback answer [S1].")

    # Simulate SDK unavailable by patching _run_with_sdk to raise ImportError
    async def mock_sdk_fail(*args, **kwargs):
        raise ImportError("claude-agent-sdk not installed")

    monkeypatch.setattr(orch_module, "_run_with_sdk", mock_sdk_fail)

    system = build_system_prompt(sources=[], history=[])
    result = await orch_module.run_agent(
        intent=Intent.QA,
        system_prompt=system,
        user_message="What is activation?",
        provider=provider,
        timeout_s=30,
    )

    assert result.degraded is True
    assert "Fallback answer" in result.content


@pytest.mark.asyncio
async def test_run_agent_sdk_timeout_uses_degraded(monkeypatch):
    """When SDK times out, run_agent must fall back gracefully."""
    from app.agent import orchestrator as orch_module
    from app.agent.prompts import build_system_prompt

    provider = FakeLLMProvider(reply="Timeout fallback [S1].")

    async def mock_sdk_timeout(*args, **kwargs):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(orch_module, "_run_with_sdk", mock_sdk_timeout)

    system = build_system_prompt(sources=[], history=[])
    result = await orch_module.run_agent(
        intent=Intent.QA,
        system_prompt=system,
        user_message="Test question",
        provider=provider,
        timeout_s=30,
    )

    assert result.degraded is True


@pytest.mark.asyncio
async def test_run_agent_sdk_error_uses_degraded(monkeypatch):
    """Any unexpected SDK error must trigger degraded fallback."""
    from app.agent import orchestrator as orch_module
    from app.agent.prompts import build_system_prompt

    provider = FakeLLMProvider(reply="Error fallback [S1].")

    async def mock_sdk_error(*args, **kwargs):
        raise RuntimeError("SDK internal error")

    monkeypatch.setattr(orch_module, "_run_with_sdk", mock_sdk_error)

    system = build_system_prompt(sources=[], history=[])
    result = await orch_module.run_agent(
        intent=Intent.QA,
        system_prompt=system,
        user_message="Test question",
        provider=provider,
        timeout_s=30,
    )

    assert result.degraded is True


# ---------------------------------------------------------------------------
# Source formatting helper
# ---------------------------------------------------------------------------


def test_format_sources_empty():
    from app.agent.orchestrator import _format_sources_for_prompt

    result = _format_sources_for_prompt([])
    assert result == ""


def test_format_sources_single():
    from app.agent.orchestrator import _format_sources_for_prompt

    sources = [
        {
            "id": "S1",
            "title": "How to grow",
            "guest": "Alice",
            "slug": "ep-12",
            "text": "Retention drives growth.",
        }
    ]
    result = _format_sources_for_prompt(sources)
    assert 'id="S1"' in result
    assert 'untrusted' in result
    assert "Retention drives growth." in result
    assert 'guest="Alice"' in result


def test_format_sources_multiple():
    from app.agent.orchestrator import _format_sources_for_prompt

    sources = [
        {"id": "S1", "title": "T1", "text": "text one", "slug": "s1"},
        {"id": "S2", "title": "T2", "text": "text two", "slug": "s2"},
    ]
    result = _format_sources_for_prompt(sources)
    assert "text one" in result
    assert "text two" in result
    assert result.index("S1") < result.index("S2")


def test_format_sources_no_guest():
    """Sources without a guest field must not include guest attribute."""
    from app.agent.orchestrator import _format_sources_for_prompt

    sources = [{"id": "S1", "title": "T1", "text": "body"}]
    result = _format_sources_for_prompt(sources)
    assert "guest" not in result
