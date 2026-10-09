import asyncio
import os
import time

os.environ["ANTHROPIC_BASE_URL"] = "http://localhost:11434"
os.environ["ANTHROPIC_AUTH_TOKEN"] = "ollama"

from claude_agent_sdk import (
    tool,
    create_sdk_mcp_server,
    ClaudeAgentOptions,
    ClaudeSDKClient,
)


@tool(
    "search_transcripts",
    "Search the podcast transcripts for product and growth advice. "
    "Use this for ANY knowledge question.",
    {"query": str},
)
async def search_transcripts(args):
    print(f"\n>>> TOOL CALLED with query: {args['query']}\n")
    return {
        "content": [
            {
                "type": "text",
                "text": "Episode 12 (Guest A): Retention is driven by "
                "activation within the first week.",
            }
        ]
    }


server = create_sdk_mcp_server(
    name="lenny", version="1.0.0", tools=[search_transcripts]
)

BUILTIN_TOOLS = [
    "Task", "Bash", "CronCreate", "CronDelete", "CronList", "DesignSync",
    "Edit", "EnterWorktree", "ExitWorktree", "Glob", "Grep", "ListAgents",
    "Monitor", "NotebookEdit", "PowerShell", "PushNotification", "Read",
    "ReportFindings", "ScheduleWakeup", "SendMessage", "Skill", "TaskStop",
    "WebFetch", "WebSearch", "Workflow", "Write",
]

options = ClaudeAgentOptions(
    model="qwen2.5:7b",
    mcp_servers={"lenny": server},
    allowed_tools=["mcp__lenny__search_transcripts"],
    disallowed_tools=BUILTIN_TOOLS,
    system_prompt=(
        "You are a transcript assistant. For every question, call the "
        "search_transcripts tool first, then answer using only its result "
        "and cite the episode. Never use any other tool."
    ),
    max_turns=6,
)


async def main():
    start = time.time()
    async with ClaudeSDKClient(options=options) as client:
        await client.query("Tell me about activation in the first week.")
        async for message in client.receive_response():
            print(message)
    print(f"\nTotal seconds: {time.time() - start:.1f}")


asyncio.run(asyncio.wait_for(main(), timeout=300))