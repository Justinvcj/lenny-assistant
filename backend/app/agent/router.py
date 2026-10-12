"""Deterministic Intent Router for Lenny Growth Assistant.

Classifies incoming user messages into QA, ESSAY, or ARTIFACT based on
regex patterns, sentence structure, and multi-turn history per architecture.md §3.
"""

from __future__ import annotations

import enum
import re
from typing import Any, Optional, Sequence


class Intent(str, enum.Enum):
    """Supported intent classes."""

    QA = "QA"
    ESSAY = "ESSAY"
    ARTIFACT = "ARTIFACT"


# --- Precompiled Regex Patterns ---

# 1. Negation patterns (prevent false positives when user explicitly opts out)
RE_NEGATION_ESSAY = re.compile(
    r"\b(?:don't|do\s+not|never|no|without|not)\s+(?:writing|write|drafting|draft|making|make|generating|generate|creating|create)?\s*(?:an?\s+)?(?:essay|article|post|ship\s*30)\b",
    re.IGNORECASE,
)
RE_NEGATION_ARTIFACT = re.compile(
    r"\b(?:don't|do\s+not|never|no|without|not)\s+(?:creating|create|making|make|giving|give|showing|show|rendering|render|generating|generate)?\s*(?:an?\s+)?(?:html(?:\s+page)?|table|checklist|artifact|one-?pager|page|doc)\b",
    re.IGNORECASE,
)

# 2. ESSAY triggers
RE_SHIP30 = re.compile(
    r"\b(?:ship\s*30(?:\s*for\s*30)?|atomic\s+essay)\b",
    re.IGNORECASE,
)
RE_ESSAY_DIRECTIVE = re.compile(
    r"\b(?:write|draft|generate|compose|turn\s+(?:this|that)\s+into|make\s+(?:this|that)\s+into)\s+(?:an?\s+)?(?:essay|article|post|newsletter|piece)\b",
    re.IGNORECASE,
)
RE_ESSAY_TOPIC = re.compile(
    r"\bessay\s+(?:on|about|regarding)\b",
    re.IGNORECASE,
)
RE_ESSAY_STANDALONE = re.compile(
    r"\b(?:an?\s+)?essay\b",
    re.IGNORECASE,
)
RE_ESSAY_TRANSFORM = re.compile(
    r"\bturn\s+(?:that|this)\s+into\b",
    re.IGNORECASE,
)

# 3. ARTIFACT triggers
RE_HTML_PAGE = re.compile(
    r"\b(?:(?:export|save|download|output|render)\s+(?:as\s+|to\s+|this\s+as\s+)?html\b|html(?:\s+page|\s+file|\s+doc|\s+one-?pager)?|one-?pager|landing\s+page|web\s*page)\b",
    re.IGNORECASE,
)
RE_MARKDOWN_DOC = re.compile(
    r"\b(?:export|save|download|output|render)\s+(?:as\s+|to\s+|this\s+as\s+)?markdown\b|\bmarkdown\s+(?:doc|document|file)\b|\bmake\s+(?:a|an)\s+(?:page|document|one-?pager)\b|\bcreate\s+(?:a|an)\s+(?:page|document|one-?pager)\b",
    re.IGNORECASE,
)
RE_TABLE = re.compile(
    r"\b(?:comparison\s+table|table\s+of|matrix|spreadsheet)\b|\b(?:in|as|into)\s+(?:a\s+)?table\b|\b(?:create|make|give\s+me|generate|put\s+(?:this|that)\s+in)\s+(?:a\s+)?table\b",
    re.IGNORECASE,
)
RE_CHECKLIST_TEMPLATE = re.compile(
    r"\b(?:checklist|rubric|cheat\s*sheet|framework\s+doc|template|actionable\s+guide|playbook\s+doc)\b",
    re.IGNORECASE,
)
RE_CODE_ARTIFACT = re.compile(
    r"\b(?:code\s+snippet|python\s+script|sql\s+query|write\s+code)\b",
    re.IGNORECASE,
)

# 4. Multi-turn refinement patterns
RE_REVISE_ESSAY = re.compile(
    r"\b(?:rewrite|revise|shorten|expand|tighten|edit|rephrase|polish|punchier|add\s+(?:a\s+)?section|change\s+the\s+hook|update\s+the\s+conclusion|make\s+it\s+(?:shorter|longer|punchier))\b",
    re.IGNORECASE,
)
RE_REVISE_ARTIFACT = re.compile(
    r"\b(?:add|insert|include)\s+(?:a|an|another)?\s*(?:column|row|item|step|section)\b|\b(?:change|tweak|adjust)\s+(?:the\s+)?(?:style|css|color|formatting)\b|\b(?:update|modify|edit)\s+(?:the\s+)?(?:table|checklist|document|page|html|matrix)\b",
    re.IGNORECASE,
)

# Informational query check (inquiry about essays, not a creation request)
RE_INQUIRY_ABOUT_ESSAYS = re.compile(
    r"\b(?:did|does|what\s+did|who|which)\s+.*?\b(?:say|talk|mention|discuss|recommend)\s+.*?\bessays?\b",
    re.IGNORECASE,
)


def _get_last_assistant_intent(history: Sequence[Any]) -> Optional[Intent]:
    """Extract the intent of the most recent assistant message from history."""
    for msg in reversed(history):
        role = getattr(msg, "role", None) if not isinstance(msg, dict) else msg.get("role")
        if role == "assistant":
            intent_val = getattr(msg, "intent", None) if not isinstance(msg, dict) else msg.get("intent")
            if intent_val:
                try:
                    return Intent(intent_val)
                except ValueError:
                    pass
    return None


def classify_intent(
    message: str,
    history: Optional[Sequence[Any]] = None,
) -> Intent:
    """Classify user intent into QA, ESSAY, or ARTIFACT deterministically.

    Precedence:
    1. Check negation suppression (e.g. 'do not write an essay' -> QA).
    2. Check ESSAY triggers (Ship 30, atomic essay, write essay/article/post).
    3. Check ARTIFACT triggers (html, one-pager, landing page, table, checklist).
    4. Check multi-turn refinement (revising an essay or artifact from history).
    5. Default to QA (questions, advice, follow-ups).
    """
    clean_msg = message.strip()
    if not clean_msg:
        return Intent.QA

    # Step 1: Detect negation guards
    negates_essay = bool(RE_NEGATION_ESSAY.search(clean_msg))
    negates_artifact = bool(RE_NEGATION_ARTIFACT.search(clean_msg))

    # Step 2: Check explicit ESSAY triggers (Highest priority unless negated)
    if not negates_essay:
        # Check if this is an informational inquiry about essays
        is_informational_inquiry = bool(RE_INQUIRY_ABOUT_ESSAYS.search(clean_msg))

        if not is_informational_inquiry:
            if RE_SHIP30.search(clean_msg):
                return Intent.ESSAY
            if RE_ESSAY_DIRECTIVE.search(clean_msg):
                return Intent.ESSAY
            if RE_ESSAY_TOPIC.search(clean_msg):
                return Intent.ESSAY
            # Disambiguate "turn that into"
            if RE_ESSAY_TRANSFORM.search(clean_msg):
                # If explicit artifact target is mentioned, let ARTIFACT handle it
                if not (
                    RE_HTML_PAGE.search(clean_msg)
                    or RE_TABLE.search(clean_msg)
                    or RE_CHECKLIST_TEMPLATE.search(clean_msg)
                ):
                    return Intent.ESSAY
            if RE_ESSAY_STANDALONE.search(clean_msg) and not (
                clean_msg.lower().startswith("what") or clean_msg.lower().startswith("did")
            ):
                return Intent.ESSAY

    # Step 3: Check explicit ARTIFACT triggers
    if not negates_artifact:
        if (
            RE_HTML_PAGE.search(clean_msg)
            or RE_MARKDOWN_DOC.search(clean_msg)
            or RE_TABLE.search(clean_msg)
            or RE_CHECKLIST_TEMPLATE.search(clean_msg)
            or RE_CODE_ARTIFACT.search(clean_msg)
        ):
            return Intent.ARTIFACT

    # Step 4: Multi-turn contextual refinement
    if history:
        last_intent = _get_last_assistant_intent(history)
        if last_intent == Intent.ESSAY and not negates_essay:
            if RE_REVISE_ESSAY.search(clean_msg):
                return Intent.ESSAY
        elif last_intent == Intent.ARTIFACT and not negates_artifact:
            if RE_REVISE_ARTIFACT.search(clean_msg):
                return Intent.ARTIFACT

    # Step 5: Default to QA
    return Intent.QA


# Alias for compatibility with architecture.md sequence diagram classify(message, history)
classify = classify_intent
