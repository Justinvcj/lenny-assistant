import asyncio
import os
import time

# Point the SDK at local Ollama. "ollama" is a dummy value, not a real key.
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

options = ClaudeAgentOptions(
    model="llama3.2:3b",
    mcp_servers={"lenny": server},
    allowed_tools=["mcp__lenny__search_transcripts"],
    system_prompt=(
        "You answer questions using ONLY the search_transcripts tool. "
        "Always call it first. Cite the episode."
    ),
    max_turns=4,
)


async def main():
    start = time.time()
    async with ClaudeSDKClient(options=options) as client:
        await client.query("Tell me about activation in the first week.")
        async for message in client.receive_response():
            print(message)
    print(f"\nTotal seconds: {time.time() - start:.1f}")


asyncio.run(asyncio.wait_for(main(), timeout=300))