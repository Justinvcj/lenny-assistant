"""R2 artifact title grammar.

Question frames must be fully stripped so a derived title is a clean noun
phrase (title-cased), never the raw question frame. Fall back to the first
heading in the answer, then to the generic default.
"""
from __future__ import annotations

import pytest
from app.routers.chat import derive_summary_title

# Each case: (user_question, assistant_text, expected_title)
CASES = [
    ("What does the podcast say about user retention?",
     "Answer text", "User Retention: Summary"),
    ("What do guests say about pricing strategy?",
     "Answer text", "Pricing Strategy: Summary"),
    ("What do the guests say about activation?",
     "Answer text", "Activation: Summary"),
    ("How should a startup think about product-market fit?",
     "Answer text", "Product-Market Fit: Summary"),
    ("How do I know when I have product-market fit?",
     "Answer text", "Product-Market Fit: Summary"),
    ("What is activation?",
     "Answer text", "Activation: Summary"),
    ("Why is retention important?",
     "Answer text", "Retention Important: Summary"),
    ("Tell me about founder mode.",
     "Answer text", "Founder Mode: Summary"),
    ("Explain product-led growth loops.",
     "Answer text", "Product-Led Growth Loops: Summary"),
    ("How does Lenny think about AI PMs?",
     "Answer text", "Ai Pms: Summary"),
]


@pytest.mark.parametrize("question,answer,expected", CASES)
def test_derived_title_strips_question_frames(question, answer, expected):
    title = derive_summary_title(question, answer)
    # Must not leak question-frame words
    low = title.lower()
    forbidden_fragments = [
        "the podcast say",
        "guests say",
        "say about",
        "what do", "what does", "what is", "what are",
        "how do i", "how should",
        "how does lenny think",
        "tell me",
        "explain ",
    ]
    for frag in forbidden_fragments:
        assert frag not in low, (
            f"title {title!r} contains forbidden question-frame fragment {frag!r}"
        )
    assert title == expected, f"title {title!r} != expected {expected!r}"


def test_fallback_to_first_heading_when_question_unavailable():
    assert (
        derive_summary_title(None, "# Pricing Playbook\nBody")
        == "Pricing Playbook"
    )


def test_fallback_default_when_nothing_derivable():
    assert (
        derive_summary_title(None, "Plain body with no heading")
        == "Key Growth Insights: Executive Summary"
    )
