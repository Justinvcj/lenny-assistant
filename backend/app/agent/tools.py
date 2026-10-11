"""MCP tool definitions for the Lenny agent.

Three in-process MCP tools exposed to the Claude Agent SDK:
  QA       → search_transcripts
  ESSAY    → generate_ship30_essay
  ARTIFACT → create_artifact

The SDK invokes each tool with ONLY the model-synthesised `args` dict. Per-
request dependencies (DB session, embedder, provider, pre-retrieved sources)
must therefore be bound to the tool handlers via closure. `build_tool_server`
builds a fresh McpSdkServerConfig per request with those closures in place.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

logger = logging.getLogger(__name__)

ToolResult = Dict[str, Any]


def _text_result(text: str) -> ToolResult:
    """SDK tools must return the MCP {content:[{type:'text', text:...}]} shape."""
    return {"content": [{"type": "text", "text": text}]}


# ---------------------------------------------------------------------------
# Per-request tool factory
# ---------------------------------------------------------------------------


def build_tools(
    *,
    db: Any,
    embedder: Any,
    provider: Any,
    sources: Optional[List[Any]] = None,
    top_k: int = 6,
    min_score: float = 0.58,
    max_artifact_bytes: int = 200_000,
) -> List[SdkMcpTool[Any]]:
    """Build the three `@tool`-wrapped SdkMcpTool instances for one request.

    Each tool closes over the given dependencies so later SDK invocations
    (which pass only the model-synthesised args dict) still reach the real
    DB, embedder, provider, and the pre-retrieved sources.
    """
    captured_sources = list(sources) if sources else []

    @tool(
        "search_transcripts",
        "Search Lenny's Podcast transcripts for product and growth advice. "
        "Call this before answering any user question.",
        {"query": str},
    )
    async def _search_transcripts(args: Dict[str, Any]) -> ToolResult:
        query = args.get("query", "").strip()
        if not query:
            return _text_result("Empty query — refine and try again.")
        if db is None or embedder is None:
            logger.warning("search_transcripts: no db/embedder bound — returning empty")
            return _text_result("NO RELEVANT RESULTS FOUND.")

        from app.rag.retrieval import retrieve

        results = await retrieve(
            query=query, db=db, top_k=top_k, min_score=min_score, embedder=embedder,
        )
        if not results:
            return _text_result("NO RELEVANT RESULTS FOUND.")

        lines: List[str] = []
        for i, r in enumerate(results, start=1):
            lines.append(
                f"[S{i}] Episode: {r.title}"
                f"{' (guest ' + r.guest + ')' if r.guest else ''}\n"
                f"{r.text.strip()}"
            )
        return _text_result("\n\n".join(lines))

    @tool(
        "create_artifact",
        "Package generated HTML or Markdown content into a renderable artifact. "
        "Use this only when the user asked for a page, one-pager, table, or doc.",
        {"title": str, "html": str, "artifact_type": str},
    )
    async def _create_artifact(args: Dict[str, Any]) -> ToolResult:
        title = args.get("title", "Generated Artifact")
        body = args.get("html", "")
        clean_type = (args.get("artifact_type") or "html").strip().lower()
        if clean_type not in ("html", "markdown"):
            clean_type = "html"
        encoded = body.encode("utf-8")
        truncated = len(encoded) > max_artifact_bytes
        if truncated:
            body = encoded[:max_artifact_bytes].decode("utf-8", errors="replace")
        payload = {
            "title": title,
            "html": body,
            "type": clean_type,
            "size_bytes": min(len(encoded), max_artifact_bytes),
            "truncated": truncated,
        }
        logger.info("create_artifact: title=%r type=%s bytes=%d", title, clean_type, payload["size_bytes"])
        return {
            "content": [{"type": "text", "text": f"Artifact '{title}' created ({payload['size_bytes']} bytes)."}],
            "_artifact": payload,
        }

    @tool(
        "generate_ship30_essay",
        "Generate a grounded Ship 30 for 30 essay (hook + body + takeaway, ~1,250 words) "
        "from the pre-retrieved transcript sources. Use this ONLY for essay requests.",
        {"topic": str},
    )
    async def _generate_ship30_essay(args: Dict[str, Any]) -> ToolResult:
        topic = args.get("topic", "").strip() or "growth insights"
        if not captured_sources or provider is None:
            logger.warning("generate_ship30_essay: no sources/provider bound")
            return _text_result(
                f"Essay generation requires grounded sources; none were available for topic {topic!r}."
            )

        from app.skills.ship30 import generate_essay

        result = await generate_essay(topic=topic, sources=captured_sources, provider=provider)
        summary = (
            f"Essay drafted ({result.word_count} words). "
            f"Validation: {'passed' if result.report.passed else 'failed ' + ','.join(result.report.failed_rules)}."
        )
        return {
            "content": [{"type": "text", "text": summary}],
            "_artifact": {
                "title": f"Ship 30 Essay: {topic[:60]}",
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
            },
        }

    return [_search_transcripts, _create_artifact, _generate_ship30_essay]


def build_tool_server(
    *,
    db: Any,
    embedder: Any,
    provider: Any,
    sources: Optional[List[Any]] = None,
    top_k: int = 6,
    min_score: float = 0.58,
    max_artifact_bytes: int = 200_000,
    server_name: str = "lenny",
) -> McpSdkServerConfig:
    """Wrap `build_tools` as a `create_sdk_mcp_server` config."""
    tools = build_tools(
        db=db, embedder=embedder, provider=provider, sources=sources,
        top_k=top_k, min_score=min_score, max_artifact_bytes=max_artifact_bytes,
    )
    return create_sdk_mcp_server(name=server_name, version="1.0.0", tools=tools)


# ---------------------------------------------------------------------------
# Legacy / test-only direct callables (kept for existing unit tests)
# ---------------------------------------------------------------------------


async def search_transcripts(
    query: str,
    *,
    top_k: int = 6,
    min_score: float = 0.58,
    db=None,
    embedder=None,
) -> Dict[str, Any]:
    """Direct Python entry point used by legacy unit tests."""
    if db is None or embedder is None:
        return {"sources": [], "count": 0}
    from app.rag.retrieval import retrieve
    results = await retrieve(query=query, db=db, top_k=top_k, min_score=min_score, embedder=embedder)
    sources = [
        {
            "id": f"S{i + 1}", "chunk_id": str(r.chunk_id), "text": r.text,
            "score": round(r.score, 4), "title": r.title, "guest": r.guest,
            "slug": r.document_slug, "start_char": r.start_char, "end_char": r.end_char,
        }
        for i, r in enumerate(results)
    ]
    return {"sources": sources, "count": len(sources)}


async def create_artifact(
    title: str, html: str, *, artifact_type: str = "html", max_bytes: int = 200_000,
) -> Dict[str, Any]:
    clean_type = artifact_type.strip().lower()
    if clean_type not in ("html", "markdown"):
        from app.errors import AppException
        raise AppException(
            code="invalid_artifact_type",
            message=f"Artifact type must be 'html' or 'markdown', got '{artifact_type}'",
            status_code=422,
        )
    encoded = html.encode("utf-8")
    truncated = len(encoded) > max_bytes
    if truncated:
        encoded = encoded[:max_bytes]
        html = encoded.decode("utf-8", errors="replace")
    return {
        "title": title, "html": html, "type": clean_type,
        "size_bytes": len(encoded), "truncated": truncated,
    }


async def generate_ship30_essay(
    topic: str,
    key_points: Optional[List[str]] = None,
    *,
    sources: Optional[List[Any]] = None,
    provider=None,
) -> Dict[str, Any]:
    if sources is None or provider is None:
        return {
            "topic": topic,
            "content": f"# Essay: {topic}\n\n*(Essay generation requires grounded sources and an active LLM provider.)*",
            "word_count": 0,
            "validation_report": {"passed": False, "failed_rules": ["R_LENGTH"]},
            "status": "degraded",
        }
    from app.skills.ship30 import generate_essay
    result = await generate_essay(topic=topic, sources=sources, provider=provider)
    return {
        "topic": topic,
        "content": result.content,
        "word_count": result.word_count,
        "validation_report": {
            "passed": result.report.passed,
            "failed_rules": result.report.failed_rules,
        },
        "repaired": result.repaired,
        "status": "ok" if result.report.passed else "validation_failed",
    }


TOOL_REGISTRY: Dict[str, Any] = {
    "search_transcripts": search_transcripts,
    "create_artifact": create_artifact,
    "generate_ship30_essay": generate_ship30_essay,
}

INTENT_TOOLS: Dict[str, List[str]] = {
    "QA": ["search_transcripts"],
    "ESSAY": ["search_transcripts", "generate_ship30_essay"],
    "ARTIFACT": ["search_transcripts", "create_artifact"],
}
