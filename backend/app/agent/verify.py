"""Citation extraction, validation, and verification engine for Lenny Growth Assistant.

Extracts [S#] tags from assistant answers, strips out-of-bounds tags,
resolves trusted citations from retrieval records, detects refusals,
and determines if a non-refusal answer needs a retry due to missing citations.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, List, Optional, Sequence, Set
from pydantic import BaseModel, Field

from app.agent.prompts import EXACT_REFUSAL_MESSAGE
from app.rag.retrieval import RetrievalResult
from app.schemas import CitationItem

# Canonical refusal sentence per SPEC and PROMPTS.md
EXACT_REFUSAL_SENTENCE = EXACT_REFUSAL_MESSAGE

# Regex for matching individual citation tags: [S1], [s2], [ S3 ]
TAG_REGEX = re.compile(r"\[\s*[sS](\d+)\s*\]")

# Regex for matching any bracket containing S-prefixed citation tags
# e.g. [S1], [s2], [ S3 ], [S1, S2], [s1, s3]
ANY_CITATION_BRACKET_REGEX = re.compile(r"\[\s*[sS]\d+\s*(?:,\s*[sS]\d+\s*)*\]")


class VerificationResult(BaseModel):
    """Result of citation verification and tag validation."""

    cleaned_text: str = Field(
        ...,
        description="Assistant response text with invalid citation tags stripped.",
    )
    citations: List[CitationItem] = Field(
        default_factory=list,
        description="Ordered, deduplicated CitationItem list resolved from sources.",
    )
    valid_tags: List[int] = Field(
        default_factory=list,
        description="Source numbers found in text that mapped to valid retrieved sources.",
    )
    invalid_tags: List[int] = Field(
        default_factory=list,
        description="Out-of-bounds or invalid source numbers found in text.",
    )
    is_refusal: bool = Field(
        default=False,
        description="True if the response is an intentional refusal.",
    )
    needs_retry: bool = Field(
        default=False,
        description="True if a non-refusal answer contains zero valid citations.",
    )


def extract_citation_tags(text: str) -> List[int]:
    """Extract all [S#] tag numbers from response text in order of appearance.

    Supports:
    - [S1], [S2], [s3], [ S4 ]
    - Grouped tags: [S1, S2], [s1, s3]
    - Adjacent brackets: [S1][S2]
    - Ignores non-source brackets: [2024], [Appendix], [SX], [S]
    """
    tags: List[int] = []
    if not text:
        return tags

    for match in ANY_CITATION_BRACKET_REGEX.finditer(text):
        bracket_content = match.group(0)
        numbers = re.findall(r"[sS](\d+)", bracket_content)
        for num_str in numbers:
            tags.append(int(num_str))

    return tags


def is_refusal_response(text: str) -> bool:
    """Check if the response matches the canonical refusal sentence.

    Normalizes whitespace, surrounding quotes, casing, and trailing punctuation.
    """
    if not text:
        return False

    normalized = text.strip().strip('"\'').strip().rstrip(".").lower()
    canonical_normalized = EXACT_REFUSAL_MESSAGE.rstrip(".").lower()
    return normalized == canonical_normalized


def strip_invalid_tags(text: str, valid_tag_set: Set[int]) -> str:
    """Remove out-of-bounds [S#] tags from text while preserving valid tags.

    Normalizes resulting double spaces and punctuation spacing.
    """
    if not text:
        return text

    def replace_bracket(match: re.Match) -> str:
        bracket_content = match.group(0)
        items = re.findall(r"([sS](\d+))", bracket_content)
        kept_numbers = [int(num_str) for _, num_str in items if int(num_str) in valid_tag_set]

        if not kept_numbers:
            return ""
        if len(kept_numbers) == 1:
            return f"[S{kept_numbers[0]}]"
        return "[" + ", ".join(f"S{num}" for num in kept_numbers) + "]"

    cleaned = ANY_CITATION_BRACKET_REGEX.sub(replace_bracket, text)
    # Clean up spaces before punctuation caused by stripping tags
    cleaned = re.sub(r"[ \t]+([.,;:!?])", r"\1", cleaned)
    # Collapse multiple horizontal whitespace into a single space
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def resolve_citations(
    valid_tags: Sequence[int],
    sources: Sequence[Any],
) -> List[CitationItem]:
    """Resolve CitationItem models from retrieved sources matching valid tags.

    Deduplicates citations while preserving order of first appearance.
    NEVER fabricates metadata from model text.
    """
    citations: List[CitationItem] = []
    seen_tags: Set[int] = set()

    for tag in valid_tags:
        if tag in seen_tags:
            continue
        seen_tags.add(tag)

        # 1-based indexing: S1 -> sources[0]
        source_idx = tag - 1
        if 0 <= source_idx < len(sources):
            src = sources[source_idx]
            if isinstance(src, dict):
                chunk_id = src.get("chunk_id")
                doc_slug = src.get("document_slug") or src.get("doc_slug") or ""
                title = src.get("title") or "Unknown"
                guest = src.get("guest")
                passage = src.get("text") or src.get("passage") or ""
            else:
                chunk_id = getattr(src, "chunk_id", None)
                doc_slug = getattr(src, "document_slug", getattr(src, "doc_slug", ""))
                title = getattr(src, "title", "Unknown")
                guest = getattr(src, "guest", None)
                passage = getattr(src, "text", getattr(src, "passage", ""))

            # Guarantee valid UUID
            if isinstance(chunk_id, str):
                parsed_chunk_id = uuid.UUID(chunk_id)
            elif isinstance(chunk_id, uuid.UUID):
                parsed_chunk_id = chunk_id
            else:
                parsed_chunk_id = uuid.uuid4()

            citations.append(
                CitationItem(
                    n=tag,
                    chunk_id=parsed_chunk_id,
                    doc_slug=doc_slug,
                    title=title,
                    guest=guest,
                    passage=passage,
                )
            )

    return citations


def verify_citations(
    answer: str,
    sources: Sequence[Any],
    db: Optional[Any] = None,
) -> VerificationResult:
    """Full citation verification pipeline.

    1. Check for intentional refusal.
    2. Extract all citation tags.
    3. Segregate valid vs invalid tags against available sources.
    4. Strip invalid tags from answer text while preserving valid tags.
    5. Resolve CitationItem objects from retrieved sources.
    6. Determine needs_retry flag.
    """
    clean_ans = answer.strip() if answer else ""

    # Check for intentional refusal
    if is_refusal_response(clean_ans):
        return VerificationResult(
            cleaned_text=clean_ans,
            citations=[],
            valid_tags=[],
            invalid_tags=[],
            is_refusal=True,
            needs_retry=False,
        )

    # If answer is empty or whitespace
    if not clean_ans:
        return VerificationResult(
            cleaned_text="",
            citations=[],
            valid_tags=[],
            invalid_tags=[],
            is_refusal=False,
            needs_retry=True,
        )

    # Extract all citation tags
    all_tags = extract_citation_tags(clean_ans)
    k = len(sources)

    valid_tag_set = {n for n in all_tags if 1 <= n <= k}
    valid_tags = [n for n in all_tags if n in valid_tag_set]
    invalid_tags = [n for n in all_tags if n not in valid_tag_set]

    # Clean text by removing out-of-bounds tags
    cleaned_text = strip_invalid_tags(clean_ans, valid_tag_set)

    # Resolve CitationItems from retrieved sources
    citations = resolve_citations(valid_tags, sources)

    # Substantive non-refusal answer with zero valid citations triggers retry
    needs_retry = len(citations) == 0

    return VerificationResult(
        cleaned_text=cleaned_text,
        citations=citations,
        valid_tags=valid_tags,
        invalid_tags=invalid_tags,
        is_refusal=False,
        needs_retry=needs_retry,
    )
