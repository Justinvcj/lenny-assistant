"""Tests covering F3: the real ClaudeAgentOptions built for each intent.

These assert the invariants that D3 (locked-down agent) requires:
  - allowed_tools is EXACTLY the one mcp__lenny__ tool for that intent.
  - every entry in the spike's BUILTIN_TOOLS list is in disallowed_tools.
  - cwd is an existing EMPTY directory.
  - env for the ollama provider carries ANTHROPIC_AUTH_TOKEN="ollama" and the
    base URL, and NEVER sets ANTHROPIC_API_KEY (F5).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from app.agent.options import (
    BUILTIN_TOOLS,
    GROUNDING_SYSTEM_PROMPT,
    ProviderConfig,
    build_agent_options,
)
from app.agent.router import Intent
from app.agent.tools import build_tool_server


@pytest.fixture
def tempdir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def tool_server():
    return build_tool_server(db=None, embedder=None, provider=None, sources=[])


@pytest.fixture
def ollama_cfg():
    return ProviderConfig(
        name="ollama", model="qwen2.5:7b",
        ollama_base_url="http://host.docker.internal:11434",
    )


def test_qa_allowlist_is_only_search_transcripts(tempdir, tool_server, ollama_cfg):
    opts = build_agent_options(Intent.QA, tool_server, ollama_cfg, tempdir)
    assert opts.allowed_tools == ["mcp__lenny__search_transcripts"]


def test_essay_allowlist_is_only_ship30(tempdir, tool_server, ollama_cfg):
    opts = build_agent_options(Intent.ESSAY, tool_server, ollama_cfg, tempdir)
    assert opts.allowed_tools == ["mcp__lenny__generate_ship30_essay"]


def test_artifact_allowlist_is_only_create_artifact(tempdir, tool_server, ollama_cfg):
    opts = build_agent_options(Intent.ARTIFACT, tool_server, ollama_cfg, tempdir)
    assert opts.allowed_tools == ["mcp__lenny__create_artifact"]


def test_builtins_fully_disallowed(tempdir, tool_server, ollama_cfg):
    opts = build_agent_options(Intent.QA, tool_server, ollama_cfg, tempdir)
    disallowed = set(opts.disallowed_tools)
    for name in BUILTIN_TOOLS:
        assert name in disallowed, f"{name} missing from disallowed_tools"


def test_cwd_is_empty_directory(tempdir, tool_server, ollama_cfg):
    opts = build_agent_options(Intent.QA, tool_server, ollama_cfg, tempdir)
    assert opts.cwd is not None
    cwd_path = Path(opts.cwd)
    assert cwd_path.is_dir()
    assert not any(cwd_path.iterdir()), "cwd must be empty — prevents CLAUDE.md leak"


def test_env_for_ollama_sets_auth_token_not_api_key(tempdir, tool_server, ollama_cfg):
    opts = build_agent_options(Intent.QA, tool_server, ollama_cfg, tempdir)
    assert opts.env.get("ANTHROPIC_BASE_URL") == "http://host.docker.internal:11434"
    assert opts.env.get("ANTHROPIC_AUTH_TOKEN") == "ollama"
    # F5: never set ANTHROPIC_API_KEY for the ollama provider.
    assert "ANTHROPIC_API_KEY" not in opts.env


def test_process_env_untouched_by_builder(tempdir, tool_server, ollama_cfg):
    """The pure builder must never mutate os.environ (ANTHROPIC_API_KEY)."""
    before = os.environ.get("ANTHROPIC_API_KEY")
    build_agent_options(Intent.QA, tool_server, ollama_cfg, tempdir)
    after = os.environ.get("ANTHROPIC_API_KEY")
    assert before == after


def test_tempdir_must_be_empty(tool_server, ollama_cfg):
    with tempfile.TemporaryDirectory() as d:
        # Plant a file to simulate a project CLAUDE.md.
        Path(d, "CLAUDE.md").write_text("secret")
        with pytest.raises(ValueError):
            build_agent_options(Intent.QA, tool_server, ollama_cfg, Path(d))


def test_system_prompt_prepended_with_grounding(tempdir, tool_server, ollama_cfg):
    opts = build_agent_options(
        Intent.QA, tool_server, ollama_cfg, tempdir, system_prompt="ADDITIONAL",
    )
    assert isinstance(opts.system_prompt, str)
    assert opts.system_prompt.startswith(GROUNDING_SYSTEM_PROMPT)
    assert "ADDITIONAL" in opts.system_prompt


def test_max_turns_default_is_five(tempdir, tool_server, ollama_cfg):
    opts = build_agent_options(Intent.QA, tool_server, ollama_cfg, tempdir)
    assert opts.max_turns == 5


def test_mcp_server_registered(tempdir, tool_server, ollama_cfg):
    opts = build_agent_options(Intent.QA, tool_server, ollama_cfg, tempdir)
    assert "lenny" in opts.mcp_servers


# ---------------------------------------------------------------------------
# Tool factory binding (F2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_factory_binds_sources_to_ship30(monkeypatch):
    """generate_ship30_essay handler must see the sources captured by the factory."""
    from app.agent.tools import build_tools

    captured = {"ran": False, "n_sources": -1}

    source_blobs = [
        type("S", (), {"text": "retention is driven by activation", "title": "ep12",
                       "guest": "A", "chunk_id": "x", "score": 0.9,
                       "document_slug": "ep12", "start_char": 0, "end_char": 10,
                       "chunk_index": 0, "speaker": None})(),
    ]

    async def _fake_generate_essay(*, topic, sources, provider):
        captured["ran"] = True
        captured["n_sources"] = len(sources)
        from types import SimpleNamespace

        from app.skills.ship30 import EssayResult
        report = SimpleNamespace(passed=True, word_count=100, failed_rules=[], rule_results=[])
        return EssayResult(content="# Essay\n", word_count=100, report=report, repaired=False)

    import app.skills.ship30 as ship30_mod
    monkeypatch.setattr(ship30_mod, "generate_essay", _fake_generate_essay)

    class _FakeProvider:
        async def chat(self, *args, **kwargs):
            raise AssertionError("provider should not be called directly")

    tools = build_tools(db=None, embedder=None, provider=_FakeProvider(), sources=source_blobs)
    ship_tool = next(t for t in tools if t.name == "generate_ship30_essay")
    await ship_tool.handler({"topic": "activation"})

    assert captured["ran"] is True
    assert captured["n_sources"] == 1


@pytest.mark.asyncio
async def test_tool_factory_search_handler_uses_bound_db(monkeypatch):
    """search_transcripts handler must route through the bound db + embedder."""
    from app.agent.tools import build_tools

    captured = {"db": None, "embedder": None, "query": None}

    async def _fake_retrieve(*, query, db, top_k, min_score, embedder):
        captured["db"] = db
        captured["embedder"] = embedder
        captured["query"] = query
        return []

    import app.rag.retrieval as retrieval_mod
    monkeypatch.setattr(retrieval_mod, "retrieve", _fake_retrieve)

    sentinel_db = object()
    sentinel_embedder = object()
    tools = build_tools(db=sentinel_db, embedder=sentinel_embedder, provider=None, sources=[])
    search_tool = next(t for t in tools if t.name == "search_transcripts")
    await search_tool.handler({"query": "retention"})

    assert captured["db"] is sentinel_db
    assert captured["embedder"] is sentinel_embedder
    assert captured["query"] == "retention"


@pytest.mark.asyncio
async def test_tool_server_qa_intent_narrows_to_search_transcripts_only():
    """QA intent must narrow MCP tools to search_transcripts only."""
    from mcp.types import ListToolsRequest

    server_cfg = build_tool_server(
        db=None, embedder=None, provider=None, sources=[], intent=Intent.QA,
    )
    handler = server_cfg["instance"].request_handlers[ListToolsRequest]
    res = await handler(ListToolsRequest(method="tools/list"))
    tool_names = [t.name for t in res.root.tools]
    assert tool_names == ["search_transcripts"]


@pytest.mark.asyncio
async def test_tool_server_essay_intent_narrows_to_ship30_only():
    """ESSAY intent must narrow MCP tools to generate_ship30_essay only."""
    from mcp.types import ListToolsRequest

    server_cfg = build_tool_server(
        db=None, embedder=None, provider=None, sources=[], intent=Intent.ESSAY,
    )
    handler = server_cfg["instance"].request_handlers[ListToolsRequest]
    res = await handler(ListToolsRequest(method="tools/list"))
    tool_names = [t.name for t in res.root.tools]
    assert tool_names == ["generate_ship30_essay"]


@pytest.mark.asyncio
async def test_tool_server_artifact_intent_narrows_to_create_artifact_only():
    """ARTIFACT intent must narrow MCP tools to create_artifact only."""
    from mcp.types import ListToolsRequest

    server_cfg = build_tool_server(
        db=None, embedder=None, provider=None, sources=[], intent=Intent.ARTIFACT,
    )
    handler = server_cfg["instance"].request_handlers[ListToolsRequest]
    res = await handler(ListToolsRequest(method="tools/list"))
    tool_names = [t.name for t in res.root.tools]
    assert tool_names == ["create_artifact"]
