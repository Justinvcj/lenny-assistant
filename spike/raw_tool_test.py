import ollama

def search_transcripts(query: str) -> str:
    return "Episode 12 (Guest A): Retention is driven by early activation within the first week."

tools = [{
    "type": "function",
    "function": {
        "name": "search_transcripts",
        "description": "Search podcast transcripts for product/growth advice. Use for any knowledge question.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "search query"}},
            "required": ["query"],
        },
    },
}]

questions = [
    "What does the podcast say about retention?",
    "What is the capital of France?",
    "Tell me about activation in the first week.",
]

for q in questions:
    r = ollama.chat(
        model="qwen2.5:7b",
        messages=[{"role": "user", "content": q}],
        tools=tools,
        options={"num_ctx": 4096},
    )
    calls = r.message.tool_calls
    print(f"\nQ: {q}\n  tool_calls: {calls}\n  text: {r.message.content[:100]}")