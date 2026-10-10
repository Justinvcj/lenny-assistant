"""MCP tool definitions for the Lenny agent.

These are in-process MCP tool functions exposed to the Claude Agent SDK.
ONLY the tools listed here are allowed — no built-in tools are ever enabled.

Tool set by intent:
    QA      → search_transcripts
    ESSAY   → search_transcripts, generate_ship30_essay
    ARTIFACT→ search_transcripts, create_artifact
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool input/output types (plain dicts — SDK serialises to JSON)
# ---------------------------------------------------------------------------

# Shared type alias for tool result payloads
ToolResult = Dict[str, Any]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def search_transcripts(
    query: str,
    *,
    top_k: int = 6,
    min_score: float = 0.58,
    db=None,  # SQLAlchemy AsyncSession injected at call time
    embedder=None,  # OllamaEmbeddingsClient injected at call time
) -> ToolResult:
    """Search the transcript corpus using pgvector similarity.

    This is the *only* retrieval path.  All answers must be grounded here.

    Args:
        query:     Natural-language search string.
        top_k:     Maximum number of chunks to return.
        min_score: Minimum cosine similarity threshold.
        db:        Injected AsyncSession (filled by orchestrator).
        embedder:  Injected embeddings client (filled by orchestrator).

    Returns:
        dict with keys:
            sources: list of source dicts (id, text, score, title, guest, slug)
            count:   int — how many sources were found
    """
    if db is None or embedder is None:
        # Fallback for unit tests that inject None
        logger.warning("search_transcripts called without db/embedder — returning empty")
        return {"sources": [], "count": 0}

    from app.rag.retrieval import retrieve

    results = await retrieve(
        query=query,
        db=db,
        top_k=top_k,
        min_score=min_score,
        embedder=embedder,
    )

    sources = [
        {
            "id": f"S{i + 1}",
            "chunk_id": str(r.chunk_id),
            "text": r.text,
            "score": round(r.score, 4),
            "title": r.title,
            "guest": r.guest,
            "slug": r.document_slug,
            "start_char": r.start_char,
            "end_char": r.end_char,
        }
        for i, r in enumerate(results)
    ]

    logger.info("search_transcripts query=%r → %d sources", query, len(sources))
    return {"sources": sources, "count": len(sources)}


async def create_artifact(
    title: str,
    html: str,
    *,
    max_bytes: int = 200_000,
) -> ToolResult:
    """Package generated HTML into an artifact payload.

    The HTML is stored as-is; the frontend renders it in a sandboxed iframe.
    Content is truncated at max_bytes to prevent abuse.

    Args:
        title:     Human-readable artifact title.
        html:      Raw HTML string to render.
        max_bytes: Hard cap on artifact size (default 200 KB).

    Returns:
        dict with keys: title, html, size_bytes, truncated
    """
    encoded = html.encode("utf-8")
    truncated = len(encoded) > max_bytes
    if truncated:
        encoded = encoded[:max_bytes]
        html = encoded.decode("utf-8", errors="replace")
        logger.warning("create_artifact: truncated to %d bytes", max_bytes)

    return {
        "title": title,
        "html": html,
        "size_bytes": len(encoded),
        "truncated": truncated,
    }


async def generate_ship30_essay(
    topic: str,
    key_points: Optional[List[str]] = None,
) -> ToolResult:
    """Placeholder stub for the Ship-30 essay generator (P6 feature).

    Returns a structured essay outline that the orchestrator can expand.
    Full implementation added in P6.

    Args:
        topic:      The essay topic extracted from the user message.
        key_points: Optional list of points to include.

    Returns:
        dict with keys: topic, outline (list of str), status
    """
    logger.info("generate_ship30_essay placeholder called for topic=%r", topic)
    outline = [
        f"Hook: Why {topic} matters for product-led growth",
        "Opening insight from the transcripts",
        "Key lesson 1 — with source citation",
        "Key lesson 2 — with source citation",
        "Actionable takeaway",
        "Call to action / closing",
    ]
    if key_points:
        outline = key_points + outline

    return {
        "topic": topic,
        "outline": outline,
        "status": "placeholder — full implementation in P6",
    }


# ---------------------------------------------------------------------------
# Tool registry — maps tool name → async callable
# ---------------------------------------------------------------------------

TOOL_REGISTRY: Dict[str, Any] = {
    "search_transcripts": search_transcripts,
    "create_artifact": create_artifact,
    "generate_ship30_essay": generate_ship30_essay,
}

# Tool sets per intent (used by orchestrator to restrict allowed tools)
INTENT_TOOLS: Dict[str, List[str]] = {
    "QA": ["search_transcripts"],
    "ESSAY": ["search_transcripts", "generate_ship30_essay"],
    "ARTIFACT": ["search_transcripts", "create_artifact"],
}
