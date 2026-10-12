"""Agent orchestrator using the Claude Agent SDK.

Fixed in post-P6 review (F1/F2/F3/F4/F5): matches the proven spike in
`spike/sdk_test.py`:

  - async with ClaudeSDKClient(options=ClaudeAgentOptions(...))
  - await client.query(prompt); async for msg in client.receive_response()
  - allowed_tools = ["mcp__lenny__<one tool>"], disallowed_tools = BUILTIN_TOOLS
  - cwd = fresh empty tempdir; env carries ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN
  - degraded fallback is used ONLY for genuine failures and always logs the
    exception type + message at ERROR level.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agent.options import ProviderConfig, build_agent_options
from app.agent.prompts import EXACT_REFUSAL_MESSAGE
from app.agent.router import Intent
from app.agent.tools import build_tool_server
from app.config import get_settings
from app.errors import AppException
from app.llm.base import ChatMessage, LLMProvider
from app.llm.factory import get_provider
from fastapi import status

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    content: str
    tool_trace: List[Dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    degraded: bool = False
    artifact: Optional[Dict[str, Any]] = None
    runtime: str = "sdk"               # "sdk" or "degraded"
    sdk_tools: List[str] = field(default_factory=list)
    num_turns: int = 0


# ---------------------------------------------------------------------------
# Source formatting (kept for legacy tests)
# ---------------------------------------------------------------------------


def _format_sources_for_prompt(sources: List[Dict[str, Any]]) -> str:
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
# SDK path (real, matches the spike)
# ---------------------------------------------------------------------------


async def _run_with_sdk(
    *,
    intent: Intent,
    system_prompt: str,
    user_message: str,
    provider_config: ProviderConfig,
    timeout_s: int,
    db: Any,
    embedder: Any,
    provider: Any,
    sources: Optional[List[Any]],
    max_artifact_bytes: int,
) -> AgentResult:
    """Run one agent turn via claude-agent-sdk against Ollama (or Anthropic).

    Any import/SDK exception is allowed to propagate — the public `run_agent`
    wraps this call and converts failures into the degraded fallback.
    """
    # Local import so test suites that mock the SDK via monkeypatch still work.
    from claude_agent_sdk import (
        AssistantMessage, ClaudeSDKClient, ResultMessage,
        SystemMessage, TextBlock, ToolUseBlock,
    )

    settings = get_settings()
    artifact_sink: Dict[str, Any] = {}
    tool_server = build_tool_server(
        intent=intent,
        db=db, embedder=embedder, provider=provider, sources=sources,
        top_k=settings.retrieval_top_k, min_score=settings.retrieval_min_score,
        max_artifact_bytes=max_artifact_bytes,
        artifact_sink=artifact_sink,
    )

    with tempfile.TemporaryDirectory(prefix="lenny-agent-") as cwd:
        options = build_agent_options(
            intent=intent,
            tools_server=tool_server,
            provider_config=provider_config,
            tempdir=Path(cwd),
            system_prompt=system_prompt,
            max_turns=5,
        )
        if provider_config.name == "anthropic":
            options.env["ANTHROPIC_API_KEY"] = provider_config.anthropic_api_key or ""

        tool_calls: List[Dict[str, Any]] = []
        final_text_parts: List[str] = []
        artifact_payload: Optional[Dict[str, Any]] = None
        init_tools: List[str] = []
        input_tokens = 0
        output_tokens = 0
        num_turns = 0

        async def _drive() -> None:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(user_message)
                async for message in client.receive_response():
                    if isinstance(message, SystemMessage):
                        if message.subtype == "init":
                            tools_from_init = message.data.get("tools") or []
                            init_tools.extend(tools_from_init)
                            logger.info(
                                "SDK init for intent %s: advertised tools=%r",
                                intent.value if hasattr(intent, "value") else intent,
                                tools_from_init,
                            )
                    elif isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, ToolUseBlock):
                                tool_calls.append({
                                    "tool": block.name,
                                    "input": block.input,
                                    "id": block.id,
                                })
                            elif isinstance(block, TextBlock):
                                if "invalid api key" in block.text.lower():
                                    raise AppException(
                                        code="bad_gateway",
                                        message="Anthropic authentication failed. Invalid API key.",
                                        status_code=status.HTTP_502_BAD_GATEWAY,
                                    )
                                final_text_parts.append(block.text)
                    elif isinstance(message, ResultMessage):
                        nonlocal input_tokens, output_tokens, num_turns
                        num_turns = message.num_turns
                        usage = message.usage or {}
                        input_tokens = int(usage.get("input_tokens", 0) or 0)
                        output_tokens = int(usage.get("output_tokens", 0) or 0)
                        if message.is_error:
                            err_msg = message.result or "SDK execution error"
                            if (
                                "invalid api key" in err_msg.lower()
                                or "auth" in err_msg.lower()
                                or "401" in err_msg
                            ):
                                raise AppException(
                                    code="bad_gateway",
                                    message="Anthropic authentication failed. Invalid API key.",
                                    status_code=status.HTTP_502_BAD_GATEWAY,
                                )
                            raise RuntimeError(f"SDK execution error: {err_msg}")
                        if message.result and not final_text_parts:
                            final_text_parts.append(message.result)
                    # Tool result blocks arrive on UserMessage; we don't need to
                    # mine them for the artifact — the handlers return a dict
                    # that the SDK's own machinery routes to the model. We get
                    # the artifact payload by inspecting our handler state via
                    # the ToolUseBlock inputs plus the handler side effect
                    # below. For reliability we re-run the artifact-producing
                    # tools in-process so we have the payload without parsing
                    # the SDK's tool-result transport.

        await asyncio.wait_for(_drive(), timeout=timeout_s)

        # Retrieve artifact payload captured directly by tool handlers during execution
        artifact_payload = artifact_sink.get("artifact")

        # Fallback replay ONLY if artifact was not captured by in-process tool handler
        if not artifact_payload:
            for call in tool_calls:
                name = call["tool"]
                args = call.get("input") or {}
                if name == "mcp__lenny__create_artifact":
                    from app.agent.tools import create_artifact as _ca
                    try:
                        out = await _ca(
                            title=args.get("title", "Generated Artifact"),
                            html=args.get("html", ""),
                            artifact_type=args.get("artifact_type", "html"),
                            max_bytes=max_artifact_bytes,
                        )
                        artifact_payload = out
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Replay of create_artifact failed: %s", exc)
                elif name == "mcp__lenny__generate_ship30_essay":
                    if sources and provider is not None:
                        try:
                            from app.skills.ship30 import generate_essay
                            result = await generate_essay(
                                topic=args.get("topic", "").strip() or "growth insights",
                                sources=list(sources),
                                provider=provider,
                            )
                            artifact_payload = {
                                "title": f"Ship 30 Essay: {args.get('topic', '')[:60]}",
                                "html": result.content,
                                "type": "markdown",
                                "size_bytes": len(result.content.encode("utf-8")),
                                "truncated": False,
                                "word_count": result.word_count,
                                "validation_report": {
                                    "passed": result.report.passed,
                                    "failed_rules": result.report.failed_rules,
                                },
                                "repaired": result.repaired,
                            }
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("Replay of ship30 essay failed: %s", exc)

        content = ("".join(final_text_parts).strip() or EXACT_REFUSAL_MESSAGE)
        if "invalid api key" in content.lower():
            raise AppException(
                code="bad_gateway",
                message="Anthropic authentication failed. Invalid API key.",
                status_code=status.HTTP_502_BAD_GATEWAY,
            )
        return AgentResult(
            content=content,
            tool_trace=[{"sdk_tools": init_tools, "calls": tool_calls}],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            degraded=False,
            artifact=artifact_payload,
            runtime="sdk",
            sdk_tools=init_tools,
            num_turns=num_turns,
        )


# ---------------------------------------------------------------------------
# Degraded fallback (direct provider call) — only for GENUINE SDK failures
# ---------------------------------------------------------------------------


async def _run_degraded(
    system_prompt: str,
    user_message: str,
    provider: LLMProvider,
    *,
    reason: str = "sdk_unavailable",
    exc_type: str = "unknown",
) -> AgentResult:
    logger.error(
        "orchestrator: degraded fallback engaged exc_type=%s reason=%s",
        exc_type, reason,
    )
    try:
        response = await provider.chat(
            messages=[ChatMessage(role="user", content=user_message)],
            system=system_prompt,
            temperature=0.2,
            max_tokens=1024,
        )
        return AgentResult(
            content=response.content or EXACT_REFUSAL_MESSAGE,
            tool_trace=[{
                "degraded": True,
                "degraded_reason": reason,
                "degraded_exc_type": exc_type,
            }],
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            degraded=True,
            runtime="degraded",
        )
    except AppException:
        # Re-raise explicit application exceptions (e.g. 502 bad_gateway)
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("orchestrator: degraded provider.chat failed: %s: %s",
                     type(exc).__name__, exc)
        err_str = str(exc)
        if (
            "401" in err_str
            or "auth" in err_str.lower()
            or "invalid api key" in err_str.lower()
            or "api_key" in err_str.lower()
            or "AuthenticationError" in type(exc).__name__
        ):
            if "not configured" in err_str.lower() or "not set" in err_str.lower() or "is required" in err_str.lower():
                msg = "Anthropic API key is not configured. Please set ANTHROPIC_API_KEY in environment."
            else:
                msg = "Anthropic authentication failed. Invalid API key."
            raise AppException(
                code="bad_gateway",
                message=msg,
                status_code=status.HTTP_502_BAD_GATEWAY,
            ) from exc
        return AgentResult(
            content=EXACT_REFUSAL_MESSAGE,
            tool_trace=[{
                "degraded": True,
                "degraded_reason": f"provider_also_failed: {exc}",
                "degraded_exc_type": type(exc).__name__,
            }],
            degraded=True,
            runtime="degraded",
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
    db: Any = None,
    embedder: Any = None,
    sources: Optional[List[Any]] = None,
) -> AgentResult:
    """Run the agent for a single user turn."""
    settings = get_settings()
    _provider = provider or get_provider()
    _timeout = timeout_s if timeout_s is not None else settings.agent_timeout_s

    provider_cfg = ProviderConfig(
        name=settings.llm_provider,
        model=settings.llm_model,
        ollama_base_url=settings.ollama_base_url,
        anthropic_api_key=settings.anthropic_api_key or None,
    )

    t0 = time.monotonic()
    try:
        result = await _run_with_sdk(
            intent=intent,
            system_prompt=system_prompt,
            user_message=user_message,
            provider_config=provider_cfg,
            timeout_s=_timeout,
            db=db,
            embedder=embedder,
            provider=_provider,
            sources=sources,
            max_artifact_bytes=settings.artifact_max_bytes,
        )
        elapsed = time.monotonic() - t0
        logger.info(
            "orchestrator: SDK ok intent=%s runtime=%s latency=%.1fs "
            "tokens_in=%d tokens_out=%d turns=%d sdk_tools=%s",
            intent.value, result.runtime, elapsed,
            result.input_tokens, result.output_tokens, result.num_turns,
            result.sdk_tools,
        )
        return result
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - t0
        if intent == Intent.ARTIFACT:
            logger.warning(
                "orchestrator: ARTIFACT intent timed out after %.1fs — skipping second provider call per Item 9b",
                elapsed,
            )
            return AgentResult(
                content="",
                tool_trace=[{
                    "degraded": True,
                    "degraded_reason": f"timeout after {elapsed:.1f}s",
                    "degraded_exc_type": "TimeoutError",
                }],
                degraded=True,
                runtime="degraded",
            )
        return await _run_degraded(
            system_prompt, user_message, _provider,
            reason=f"timeout after {elapsed:.1f}s", exc_type="TimeoutError",
        )
    except AppException:
        raise
    except Exception as exc:  # noqa: BLE001
        elapsed = time.monotonic() - t0
        err_str = str(exc)
        auth_exc_names = ("AuthenticationError", "PermissionDeniedError")
        if (
            type(exc).__name__ in auth_exc_names
            or "401" in err_str
            or "invalid api key" in err_str.lower()
            or "anthropic_api_key is required" in err_str.lower()
            or ("anthropic" in provider_cfg.name.lower() and "auth" in err_str.lower())
        ):
            if "anthropic_api_key is required" in err_str.lower() or "not configured" in err_str.lower():
                msg = "Anthropic API key is not configured. Please set ANTHROPIC_API_KEY in environment."
            else:
                msg = "Anthropic authentication failed. Invalid API key."
            logger.error("orchestrator: cloud provider auth error: %s: %s", type(exc).__name__, exc)
            raise AppException(
                code="bad_gateway",
                message=msg,
                status_code=status.HTTP_502_BAD_GATEWAY,
            ) from exc

        if intent == Intent.ARTIFACT:
            logger.warning(
                "orchestrator: ARTIFACT intent failed (%s: %s) — skipping second provider call per Item 9b",
                type(exc).__name__, exc,
            )
            return AgentResult(
                content="",
                tool_trace=[{
                    "degraded": True,
                    "degraded_reason": f"{exc} (after {elapsed:.1f}s)",
                    "degraded_exc_type": type(exc).__name__,
                }],
                degraded=True,
                runtime="degraded",
            )
        return await _run_degraded(
            system_prompt, user_message, _provider,
            reason=f"{exc} (after {elapsed:.1f}s)",
            exc_type=type(exc).__name__,
        )
