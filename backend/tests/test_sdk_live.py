"""Live Ollama/SDK roundtrip — mirrors the proven spike.

Skipped when Ollama (or the installed SDK) is unreachable. Produces the
final proof of F1/F3: the ClaudeSDKClient really talks to Ollama, the init
tool list contains ONLY our mcp__lenny__ tools, and run_agent returns
degraded == False.
"""

from __future__ import annotations

import os
import socket
import urllib.parse

import pytest

pytestmark = pytest.mark.ollama


def _ollama_reachable() -> bool:
    url = os.environ.get("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    try:
        parsed = urllib.parse.urlparse(url)
        host, port = parsed.hostname or "127.0.0.1", parsed.port or 11434
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


LIVE = _ollama_reachable()


@pytest.mark.skipif(not LIVE, reason="Ollama not reachable")
@pytest.mark.asyncio
async def test_sdk_live_runs_with_only_our_tools():
    """F3 proof: SDK init tool list contains ONLY our mcp__lenny__ tool."""
    from app.agent.orchestrator import run_agent
    from app.agent.prompts import build_system_prompt
    from app.agent.router import Intent

    system = build_system_prompt(sources=[], history=[])
    result = await run_agent(
        intent=Intent.QA,
        system_prompt=system,
        user_message="What does the podcast say about retention?",
        timeout_s=120,
        db=None, embedder=None, sources=[],
    )

    assert result.degraded is False, (
        f"Expected SDK path; got degraded. tool_trace={result.tool_trace}"
    )
    assert result.runtime == "sdk"
    # Init tool list must only contain our mcp__lenny__ tools.
    assert all(t.startswith("mcp__lenny__") for t in result.sdk_tools), (
        f"Found non-lenny tools in init list: {result.sdk_tools}"
    )
    assert len(result.sdk_tools) >= 1
