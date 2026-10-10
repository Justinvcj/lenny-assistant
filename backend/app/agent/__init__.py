"""Lenny Growth Assistant Agent Core.

Exports intent routing, prompt generation, citation verification, and helper utilities.
"""

from app.agent.prompts import (
    EXACT_REFUSAL_MESSAGE,
    build_system_prompt,
    format_conversation_history,
    format_source_blocks,
    is_standalone_query,
    rewrite_query,
)
from app.agent.router import (
    Intent,
    classify,
    classify_intent,
)
from app.agent.verify import (
    EXACT_REFUSAL_SENTENCE,
    VerificationResult,
    extract_citation_tags,
    is_refusal_response,
    resolve_citations,
    strip_invalid_tags,
    verify_citations,
)

__all__ = [
    # Router
    "Intent",
    "classify",
    "classify_intent",
    # Prompts & Rewriter
    "EXACT_REFUSAL_MESSAGE",
    "build_system_prompt",
    "format_conversation_history",
    "format_source_blocks",
    "is_standalone_query",
    "rewrite_query",
    # Verifier
    "EXACT_REFUSAL_SENTENCE",
    "VerificationResult",
    "extract_citation_tags",
    "is_refusal_response",
    "resolve_citations",
    "strip_invalid_tags",
    "verify_citations",
]
