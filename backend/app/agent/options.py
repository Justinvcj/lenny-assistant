"""Pure builder for ClaudeAgentOptions.

Enforces D3 (locked-down agent) from SPEC.md: allowlist narrowed to one or two
MCP tools per intent and every built-in SDK tool disabled.

Reference: spike/sdk_test.py — the ONLY code path proven to work against the
installed claude-agent-sdk + Ollama.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import McpSdkServerConfig

from app.agent.router import Intent


# Full built-in SDK tool list, mirrored from spike/sdk_test.py. Passed as
# `disallowed_tools` so the SDK's CLI never advertises any of them to the model.
BUILTIN_TOOLS: List[str] = [
    "Task", "TaskCreate", "TaskGet", "TaskList", "TaskOutput", "TaskStop",
    "TaskUpdate", "Bash", "CronCreate", "CronDelete", "CronList", "DesignSync",
    "Edit", "EnterWorktree", "ExitWorktree", "Glob", "Grep", "ListAgents",
    "Monitor", "NotebookEdit", "PowerShell", "PushNotification", "Read",
    "ReportFindings", "ScheduleWakeup", "SendMessage", "Skill", "WebFetch",
    "WebSearch", "Workflow", "Write",
]


# Allowed MCP tools per intent (the actual public tool names appear as
# "mcp__lenny__<tool>" once the SDK registers the create_sdk_mcp_server block).
INTENT_ALLOWED_TOOLS: Dict[Intent, List[str]] = {
    Intent.QA: ["search_transcripts"],
    Intent.ESSAY: ["generate_ship30_essay"],
    Intent.ARTIFACT: ["create_artifact"],
}


# Prepended to the grounded system prompt built by prompts.build_system_prompt.
# Instructs the model to call the one allowed MCP tool before answering.
GROUNDING_SYSTEM_PROMPT = (
    "You are the Lenny Growth Assistant. For every user message you MUST call "
    "the single MCP tool available to you (prefix `mcp__lenny__`) before you "
    "reply. Base your answer only on the tool result or the <source> blocks "
    "in the user turn, and tag every claim with its [S#] identifier. If no "
    "sources support the answer, reply exactly: "
    "I don't have information about that in the transcripts."
)


@dataclass(frozen=True)
class ProviderConfig:
    """Minimum provider info required to point the SDK at a backend."""

    name: str                       # "ollama" or "anthropic"
    model: str                      # e.g. "qwen2.5:7b"
    ollama_base_url: Optional[str] = None  # required when name == "ollama"
    anthropic_api_key: Optional[str] = None  # required when name == "anthropic"


def _mcp_prefix(tool_name: str, server_name: str = "lenny") -> str:
    """Return the SDK-visible identifier for an in-process MCP tool."""
    return f"mcp__{server_name}__{tool_name}"


def build_agent_options(
    intent: Intent,
    tools_server: McpSdkServerConfig,
    provider_config: ProviderConfig,
    tempdir: Path,
    *,
    system_prompt: Optional[str] = None,
    max_turns: int = 5,
    server_name: str = "lenny",
) -> ClaudeAgentOptions:
    """Build the ClaudeAgentOptions used for a single agent turn.

    - allowed_tools: ONLY the mcp__lenny__<tool> entry for this intent.
    - disallowed_tools: every built-in from the spike's BUILTIN_TOOLS list.
    - cwd: a fresh empty temp dir (no project CLAUDE.md / AGENTS.md leak).
    - env: for the ollama provider, ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN
      (never ANTHROPIC_API_KEY — per SPEC §2 and verified in the installed SDK
      signature which accepts an `env: dict[str, str]` field).
    """
    tempdir = Path(tempdir)
    if not tempdir.exists() or not tempdir.is_dir():
        raise ValueError(f"tempdir must be an existing directory: {tempdir}")
    if any(tempdir.iterdir()):
        raise ValueError(f"tempdir must be empty to prevent prompt leakage: {tempdir}")

    allowed_simple = INTENT_ALLOWED_TOOLS.get(intent, ["search_transcripts"])
    allowed_tools = [_mcp_prefix(n, server_name) for n in allowed_simple]

    env: Dict[str, str] = {}
    if provider_config.name == "ollama":
        if not provider_config.ollama_base_url:
            raise ValueError("ollama_base_url is required for the ollama provider")
        env["ANTHROPIC_BASE_URL"] = provider_config.ollama_base_url
        env["ANTHROPIC_AUTH_TOKEN"] = "ollama"
        # Deliberately NOT setting ANTHROPIC_API_KEY (SPEC §2, F5).
    elif provider_config.name == "anthropic":
        if not provider_config.anthropic_api_key:
            raise ValueError("anthropic_api_key is required for the anthropic provider")
        env["ANTHROPIC_AUTH_TOKEN"] = provider_config.anthropic_api_key

    full_system_prompt = (
        f"{GROUNDING_SYSTEM_PROMPT}\n\n{system_prompt}"
        if system_prompt else GROUNDING_SYSTEM_PROMPT
    )

    return ClaudeAgentOptions(
        model=provider_config.model,
        mcp_servers={server_name: tools_server},
        allowed_tools=allowed_tools,
        disallowed_tools=list(BUILTIN_TOOLS),
        system_prompt=full_system_prompt,
        max_turns=max_turns,
        cwd=str(tempdir),
        env=env,
        permission_mode="default",
    )
