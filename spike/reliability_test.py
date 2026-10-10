import asyncio
import os

os.environ["ANTHROPIC_BASE_URL"] = "http://localhost:11434"
os.environ["ANTHROPIC_AUTH_TOKEN"] = "ollama"

from claude_agent_sdk import (
    tool, create_sdk_mcp_server, ClaudeAgentOptions, ClaudeSDKClient,
    AssistantMessage, ToolUseBlock, TextBlock,
)


@tool("search_transcripts",
      "Search the podcast transcripts for product and growth advice. "
      "Use this for ANY knowledge question.",
      {"query": str})
async def search_transcripts(args):
    q = args["query"].lower()
    if "activation" in q or "retention" in q:
        text = ("Episode 12 (Guest A): Retention is driven by "
                "activation within the first week.")
    else:
        text = "NO RELEVANT RESULTS FOUND."
    return {"content": [{"type": "text", "text": text}]}


server = create_sdk_mcp_server(name="lenny", version="1.0.0",
                               tools=[search_transcripts])

BUILTIN_TOOLS = [
    "Task", "Bash", "CronCreate", "CronDelete", "CronList", "DesignSync",
    "Edit", "EnterWorktree", "ExitWorktree", "Glob", "Grep", "ListAgents",
    "Monitor", "NotebookEdit", "PowerShell", "PushNotification", "Read",
    "ReportFindings", "ScheduleWakeup", "SendMessage", "Skill", "TaskStop",
    "WebFetch", "WebSearch", "Workflow", "Write",
]

SYSTEM = (
    "You are a transcript assistant. For every question, call the "
    "search_transcripts tool first. Answer ONLY with facts stated in the "
    "tool result, and cite the episode. Do not add explanations or "
    "inferences beyond the tool result. If the result says NO RELEVANT "
    "RESULTS FOUND, reply exactly: I don't have information about that "
    "in the transcripts."
)

QUESTIONS = [
    "Tell me about activation in the first week.",
    "What does the podcast say about retention?",
    "How does early activation relate to retention?",
    "What is the capital of France?",
    "How do I bake sourdough bread?",
]


async def run_one(question):
    options = ClaudeAgentOptions(
        model="qwen2.5:7b",
        mcp_servers={"lenny": server},
        allowed_tools=["mcp__lenny__search_transcripts"],
        disallowed_tools=BUILTIN_TOOLS,
        system_prompt=SYSTEM,
        max_turns=6,
    )
    tool_called, answer = False, ""
    async with ClaudeSDKClient(options=options) as client:
        await client.query(question)
        async for m in client.receive_response():
            if isinstance(m, AssistantMessage):
                for b in m.content:
                    if isinstance(b, ToolUseBlock):
                        tool_called = True
                    if isinstance(b, TextBlock):
                        answer = b.text
    return tool_called, answer


async def main():
    hits = 0
    for q in QUESTIONS:
        called, answer = await run_one(q)
        hits += called
        print(f"\nQ: {q}\n  tool called: {called}\n  answer: {answer}")
    print(f"\nTOOL CALL RATE: {hits}/{len(QUESTIONS)}")

asyncio.run(main())