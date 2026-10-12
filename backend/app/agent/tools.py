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
from typing import Any

from app.agent.router import Intent
from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

logger = logging.getLogger(__name__)

ToolResult = dict[str, Any]


def _text_result(text: str) -> ToolResult:
    """SDK tools must return the MCP {content:[{type:'text', text:...}]} shape."""
    return {"content": [{"type": "text", "text": text}]}


def normalize_artifact_type(raw_type: str | None) -> str:
    """Normalize user or model artifact type aliases to 'html' or 'markdown'.

    Aliases:
      html, htm, page, webpage, html page, one-page, one-pager, landing, table, dashboard -> html
      markdown, md, doc, document, text, notes, report -> markdown
    """
    if not raw_type:
        return "html"
    s = str(raw_type).strip().lower()
    if s in (
        "html", "htm", "page", "webpage", "html page", "one-page", "one-pager",
        "one pager", "landing", "landing page", "table", "dashboard",
    ):
        return "html"
    if s in ("markdown", "md", "doc", "document", "text", "notes", "report"):
        return "markdown"
    if "html" in s or "webpage" in s:
        return "html"
    if "markdown" in s:
        return "markdown"
    return s


CREATE_ARTIFACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Short descriptive title of the artifact",
        },
        "html": {
            "type": "string",
            "description": "The full content of the artifact. For html, full valid HTML document. For markdown, full valid markdown.",
        },
        "artifact_type": {
            "type": "string",
            "enum": ["html", "markdown"],
            "description": "The artifact type. Allowed values are strictly 'html' or 'markdown'. Use 'html' for page/one-page/landing/webpage/table/dashboard; 'markdown' for doc/document/notes.",
        },
    },
    "required": ["title", "html", "artifact_type"],
}


# ---------------------------------------------------------------------------
# Per-request tool factory
# ---------------------------------------------------------------------------


def build_tools(
    *,
    db: Any = None,
    embedder: Any = None,
    provider: Any = None,
    sources: list[Any] | None = None,
    top_k: int = 6,
    min_score: float = 0.58,
    max_artifact_bytes: int = 200_000,
    intent: Intent | None = None,
    artifact_sink: dict[str, Any] | None = None,
) -> list[SdkMcpTool[Any]]:
    """Build the `@tool`-wrapped SdkMcpTool instances for one request.

    When intent is supplied, returns ONLY the tool for that intent (SPEC D2):
      QA       → [search_transcripts]
      ESSAY    → [generate_ship30_essay]
      ARTIFACT → [create_artifact]
    """
    captured_sources = list(sources) if sources else []

    @tool(
        "search_transcripts",
        "Search Lenny's Podcast transcripts for product and growth advice. "
        "Call this before answering any user question.",
        {"query": str},
    )
    async def _search_transcripts(args: dict[str, Any]) -> ToolResult:
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

        lines: list[str] = []
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
        "Allowed artifact_type values: 'html' (for pages/one-pagers/landing pages/tables) or 'markdown' (for documents/notes).",
        CREATE_ARTIFACT_SCHEMA,
    )
    async def _create_artifact(args: dict[str, Any]) -> ToolResult:
        try:
            title = (args.get("title") or "Generated Artifact").strip()
            body = args.get("html") or args.get("content") or ""
            raw_type = args.get("artifact_type") or args.get("type") or "html"
            clean_type = normalize_artifact_type(raw_type)

            if clean_type not in ("html", "markdown"):
                return {
                    "content": [{"type": "text", "text": f"Error: Invalid artifact_type '{raw_type}'. Allowed values: 'html' or 'markdown'. Please retry with a valid type."}],
                    "is_error": True,
                }

            if not body:
                return {
                    "content": [{"type": "text", "text": "Error: 'html' (content) argument cannot be empty. Please provide the document content."}],
                    "is_error": True,
                }

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
            if artifact_sink is not None:
                artifact_sink["artifact"] = payload
            logger.info("create_artifact: title=%r type=%s bytes=%d", title, clean_type, payload["size_bytes"])
            return {
                "content": [{"type": "text", "text": f"Artifact '{title}' created ({payload['size_bytes']} bytes, type={clean_type})."}],
                "_artifact": payload,
            }
        except Exception as exc:
            logger.error("create_artifact failed with exception: %s", exc, exc_info=True)
            return {
                "content": [{"type": "text", "text": f"Error creating artifact: {exc!s}. Please retry with valid arguments: title, html, and artifact_type ('html' or 'markdown')."}],
                "is_error": True,
            }

    @tool(
        "generate_ship30_essay",
        "Generate a grounded Ship 30 for 30 essay (hook + body + takeaway, ~1,250 words) "
        "from the pre-retrieved transcript sources. Use this ONLY for essay requests.",
        {"topic": str},
    )
    async def _generate_ship30_essay(args: dict[str, Any]) -> ToolResult:
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
        essay_payload = {
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
        }
        if artifact_sink is not None:
            artifact_sink["artifact"] = essay_payload
        return {
            "content": [{"type": "text", "text": summary}],
            "_artifact": essay_payload,
        }

    if intent is not None:
        intent_key = intent.value if isinstance(intent, Intent) else str(intent).upper()
        if intent_key == "QA":
            return [_search_transcripts]
        elif intent_key == "ESSAY":
            return [_generate_ship30_essay]
        elif intent_key == "ARTIFACT":
            return [_create_artifact]

    return [_search_transcripts, _create_artifact, _generate_ship30_essay]


def build_tool_server(
    *,
    db: Any,
    embedder: Any,
    provider: Any,
    sources: list[Any] | None = None,
    top_k: int = 6,
    min_score: float = 0.58,
    max_artifact_bytes: int = 200_000,
    server_name: str = "lenny",
    intent: Intent | None = None,
    artifact_sink: dict[str, Any] | None = None,
) -> McpSdkServerConfig:
    """Wrap `build_tools` as a `create_sdk_mcp_server` config narrowed to the request intent."""
    tools = build_tools(
        db=db, embedder=embedder, provider=provider, sources=sources,
        top_k=top_k, min_score=min_score, max_artifact_bytes=max_artifact_bytes,
        intent=intent, artifact_sink=artifact_sink,
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
) -> dict[str, Any]:
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
) -> dict[str, Any]:
    clean_type = normalize_artifact_type(artifact_type)
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
    key_points: list[str] | None = None,
    *,
    sources: list[Any] | None = None,
    provider=None,
) -> dict[str, Any]:
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


TOOL_REGISTRY: dict[str, Any] = {
    "search_transcripts": search_transcripts,
    "create_artifact": create_artifact,
    "generate_ship30_essay": generate_ship30_essay,
}

INTENT_TOOLS: dict[str, list[str]] = {
    "QA": ["search_transcripts"],
    "ESSAY": ["generate_ship30_essay"],
    "ARTIFACT": ["create_artifact"],
}
