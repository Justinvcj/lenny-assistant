"""Agent orchestrator using the Claude Agent SDK.

Critical constraints from SPEC.md §4.5 and spike measurements:
  - SDK: claude-agent-sdk using ClaudeSDKClient
  - ANTHROPIC_BASE_URL → Ollama endpoint  (token = "ollama")
  - Disable ALL built-in tools (BUILTIN_TOOLS list emptied)
  - Allow ONLY intent-specific MCP tools (from agent/tools.py INTENT_TOOLS)
  - cwd = empty temp dir (prevents accidental FS access)
  - Hard timeout: AGENT_TIMEOUT_S
  - Degraded fallback: if SDK fails or times out → direct Ollama provider call
    with degraded=True in the result

Spike reference (spike/SPIKE_LOG.md):
  - Run 2: built-in tools disabled → input_tokens=384, tool called correctly
  - E2E latency: 15.2 s with qwen2.5:7b
  - Reliability: 22/25 tool calls, 10/10 refusals across 5 runs
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.agent.prompts import EXACT_REFUSAL_MESSAGE, build_system_prompt
from app.agent.router import Intent
from app.agent.tools import INTENT_TOOLS, TOOL_REGISTRY
from app.config import get_settings
from app.llm.base import ChatMessage, LLMProvider
from app.llm.factory import get_provider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class AgentResult:
    """Returned by run_agent()."""

    content: str
    tool_trace: List[Dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    degraded: bool = False
    artifact: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Source formatting helper
# ---------------------------------------------------------------------------


def _format_sources_for_prompt(sources: List[Dict[str, Any]]) -> str:
    """Convert retrieval results to the numbered <source> block format."""
    blocks = []
    for s in sources:
        sid = s.get("id", f"S{s.get('n', '?')}")
        title = s.get("title", "Unknown")
        guest = s.get("guest", "")
        slug = s.get("slug", s.get("doc_slug", ""))
        text = s.get("text", s.get("passage", ""))
        header = f'<source id="{sid}" untrusted title="{title}"'
        if guest:
            header += f' guest="{guest}"'
        if slug:
            header += f' slug="{slug}"'
        header += ">"
        blocks.append(f"{header}\n{text}\n</source>")
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# SDK-based agent run
# ---------------------------------------------------------------------------


async def _run_with_sdk(
    intent: Intent,
    system_prompt: str,
    user_message: str,
    ollama_base_url: str,
    timeout_s: int,
) -> AgentResult:
    """Attempt to run via Claude Agent SDK pointed at Ollama.

    This is the primary path.  Falls through and raises on any failure so
    the caller can trigger the degraded fallback.

    Key SDK configuration (from spike/SPIKE_LOG.md Run 2):
      - tools list = only INTENT_TOOLS[intent], NOT BUILTIN_TOOLS
      - cwd = empty tempdir
      - ANTHROPIC_BASE_URL env var → ollama endpoint
      - token = "ollama"
    """
    try:
        # Conditional import — SDK may not be installed in all environments
        from claude_agent_sdk import ClaudeSDKClient, run_agent as sdk_run_agent  # type: ignore
    except ImportError:
        raise RuntimeError(
            "claude-agent-sdk is not installed. "
            "Run: pip install claude-agent-sdk"
        )

    settings = get_settings()
    allowed_tool_names = INTENT_TOOLS.get(intent.value, ["search_transcripts"])

    # Build the in-process MCP tool list (only allowed tools)
    mcp_tools = {
        name: TOOL_REGISTRY[name]
        for name in allowed_tool_names
        if name in TOOL_REGISTRY
    }

    tool_trace: List[Dict[str, Any]] = []

    # Patch env so SDK routes to Ollama
    old_base_url = os.environ.get("ANTHROPIC_BASE_URL")
    old_api_key = os.environ.get("ANTHROPIC_API_KEY")

    try:
        os.environ["ANTHROPIC_BASE_URL"] = ollama_base_url
        os.environ["ANTHROPIC_API_KEY"] = "ollama"

        with tempfile.TemporaryDirectory() as cwd:
            client = ClaudeSDKClient(
                base_url=ollama_base_url,
                api_key="ollama",
                model=settings.llm_model,
            )

            result = await asyncio.wait_for(
                sdk_run_agent(
                    client=client,
                    system=system_prompt,
                    prompt=user_message,
                    tools=list(mcp_tools.values()),
                    # CRITICAL: no built-in tools (BUILTIN_TOOLS = [])
                    builtin_tools=[],
                    cwd=cwd,
                ),
                timeout=timeout_s,
            )

        content = result.result or EXACT_REFUSAL_MESSAGE
        tool_trace = [
            {"tool": t.get("name"), "input": t.get("input"), "output": t.get("output")}
            for t in getattr(result, "tool_calls", [])
        ]

        # Extract artifact if create_artifact was called
        artifact = None
        for trace in tool_trace:
            if trace.get("tool") == "create_artifact" and trace.get("output"):
                artifact = trace["output"]
                break

        usage = getattr(result, "usage", {}) or {}
        return AgentResult(
            content=content,
            tool_trace=tool_trace,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            degraded=False,
            artifact=artifact,
        )
    finally:
        # Restore environment
        if old_base_url is None:
            os.environ.pop("ANTHROPIC_BASE_URL", None)
        else:
            os.environ["ANTHROPIC_BASE_URL"] = old_base_url

        if old_api_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = old_api_key


# ---------------------------------------------------------------------------
# Degraded fallback: direct Ollama provider call
# ---------------------------------------------------------------------------


async def _run_degraded(
    system_prompt: str,
    user_message: str,
    provider: LLMProvider,
) -> AgentResult:
    """Direct provider call used when SDK path fails or times out."""
    logger.warning("orchestrator: using degraded fallback (direct provider call)")
    try:
        response = await provider.chat(
            messages=[ChatMessage(role="user", content=user_message)],
            system=system_prompt,
            temperature=0.2,
            max_tokens=1024,
        )
        return AgentResult(
            content=response.content or EXACT_REFUSAL_MESSAGE,
            tool_trace=[{"degraded": True, "reason": "sdk_unavailable"}],
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            degraded=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("orchestrator: degraded fallback also failed: %s", exc)
        return AgentResult(
            content=EXACT_REFUSAL_MESSAGE,
            tool_trace=[{"degraded": True, "reason": str(exc)}],
            degraded=True,
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_agent(
    intent: Intent,
    system_prompt: str,
    user_message: str,
    *,
    provider: Optional[LLMProvider] = None,
    timeout_s: Optional[int] = None,
) -> AgentResult:
    """Run the agent for a single user turn.

    Args:
        intent:        Classified intent (QA / ESSAY / ARTIFACT).
        system_prompt: Full grounded system prompt from agent/prompts.py.
        user_message:  The (possibly rewritten) user query.
        provider:      Override the LLM provider (useful in tests).
        timeout_s:     Override the agent timeout in seconds.

    Returns:
        AgentResult with content, tool_trace, token counts, degraded flag.
    """
    settings = get_settings()
    _provider = provider or get_provider()
    _timeout = timeout_s if timeout_s is not None else settings.agent_timeout_s
    _ollama_url = settings.ollama_base_url

    t0 = time.monotonic()

    try:
        result = await _run_with_sdk(
            intent=intent,
            system_prompt=system_prompt,
            user_message=user_message,
            ollama_base_url=_ollama_url,
            timeout_s=_timeout,
        )
        elapsed = time.monotonic() - t0
        logger.info(
            "orchestrator: SDK run ok intent=%s latency=%.1fs tokens_in=%d tokens_out=%d",
            intent.value,
            elapsed,
            result.input_tokens,
            result.output_tokens,
        )
        return result

    except (RuntimeError, ImportError) as sdk_err:
        # SDK not installed or misconfigured — go straight to degraded
        logger.warning("orchestrator: SDK unavailable (%s) — degraded", sdk_err)
        return await _run_degraded(system_prompt, user_message, _provider)

    except asyncio.TimeoutError:
        elapsed = time.monotonic() - t0
        logger.warning("orchestrator: SDK timed out after %.1fs — degraded", elapsed)
        return await _run_degraded(system_prompt, user_message, _provider)

    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - t0
        logger.error("orchestrator: SDK error after %.1fs: %s — degraded", elapsed, exc)
        return await _run_degraded(system_prompt, user_message, _provider)
