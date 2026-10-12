"""Tests for Ship 30 section heading generation, validation, and repair (Item 1)."""
from __future__ import annotations

import pytest

from app.llm.base import ChatMessage, ChatResponse
from app.skills.ship30 import (
    FALLBACK_HEADINGS,
    generate_section_heading,
    plan_outline,
    repair_assembled_headings,
    validate_heading,
)
from app.skills.validator import validate_essay


EXACT_BAD_HEADINGS = [
    "Angle 2 on pricing strategy",
    "Angle 3 on Pricing Strategy",
    "Angle 5 on pricing strategy",
    "Angle 6 on pricing strategy",
    "Challenge Lies Identifying Right Product Features",
    "Repeatedly Tweaking Onboarding Flow Exploring Other",
    "Jeanne DeWitt Grosser Seasoned Marketer Advises",
]


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0
        self.prompts = []

    async def chat(self, messages, **kwargs):
        self.call_count += 1
        self.prompts.append(messages[-1].content if messages else "")
        idx = min(self.call_count - 1, len(self.responses) - 1)
        return ChatResponse(content=self.responses[idx], input_tokens=10, output_tokens=10, model="fake")


@pytest.mark.parametrize("bad_heading", EXACT_BAD_HEADINGS)
def test_exact_bad_headings_rejected(bad_heading):
    valid, reason = validate_heading(bad_heading, topic="pricing strategy")
    assert not valid, f"Expected {bad_heading!r} to be rejected, but it passed! Reason: {reason}"
    assert reason, "Expected a failure reason when heading is rejected"


def test_heading_validation_rules():
    # Length < 4 words
    assert not validate_heading("Too Short Now")[0]
    # Length > 8 words
    assert not validate_heading("This Heading Is Much Too Long For An Essay Section Title")[0]
    # Lowercase start
    assert not validate_heading("why retention matters most for teams")[0]
    # Ends with stop word
    assert not validate_heading("Finding The Right Features For", topic="")[0]
    assert not validate_heading("Finding The Right Features Other", topic="")[0]
    # Angle <number>
    assert not validate_heading("Angle 4 on Customer Retention")[0]
    # Topic string: at most 1
    topic = "product-led growth"
    v1, _ = validate_heading("Understanding The Principles Of Retention", topic=topic, existing_headings=[])
    assert v1
    v2, _ = validate_heading("Why Product-Led Growth Compounds Quickly", topic=topic, existing_headings=[])
    assert v2
    # Second heading containing topic string must fail
    v3, reason3 = validate_heading(
        "Another Take On Product-Led Growth Loops",
        topic=topic,
        existing_headings=["Why Product-Led Growth Compounds Quickly"],
    )
    assert not v3, "Second heading with topic string must be rejected"


def test_plan_outline_holds_only_slot_ids_and_word_budgets():
    plans = plan_outline("pricing strategy", [])
    for p in plans:
        assert hasattr(p, "slot_id"), "SectionPlan must have slot_id"
        assert p.word_budget > 0
        assert "Angle" not in p.slot_id
        if not p.is_hook and not p.is_takeaway:
            assert p.slot_id.startswith("body_") or p.slot_id.startswith("slot_")


@pytest.mark.asyncio
async def test_generate_heading_good():
    llm = FakeLLM(["Why Retention Decides Early Traction"])
    heading = await generate_section_heading(
        section_text="Retention is the bedrock of growth. [S1]",
        topic="pricing strategy",
        existing_headings=[],
        provider=llm,
    )
    assert heading == "Why Retention Decides Early Traction"
    assert llm.call_count == 1


@pytest.mark.asyncio
async def test_generate_heading_retry_success():
    llm = FakeLLM([
        "Angle 2 on pricing strategy",  # Attempt 1: bad
        "Why Retention Decides Early Traction",  # Attempt 2: good
    ])
    heading = await generate_section_heading(
        section_text="Retention is the bedrock of growth. [S1]",
        topic="pricing strategy",
        existing_headings=[],
        provider=llm,
    )
    assert heading == "Why Retention Decides Early Traction"
    assert llm.call_count == 2
    assert "rejected" in llm.prompts[1].lower() or "angle" in llm.prompts[1].lower()


@pytest.mark.asyncio
async def test_generate_heading_retry_fallback():
    llm = FakeLLM([
        "Angle 2 on pricing strategy",  # Attempt 1: bad
        "Angle 3 on pricing strategy",  # Attempt 2: bad
    ])
    heading = await generate_section_heading(
        section_text="Retention is the bedrock of growth. [S1]",
        topic="pricing strategy",
        existing_headings=[],
        provider=llm,
    )
    assert heading == FALLBACK_HEADINGS[0]  # "What the guests say"
    assert llm.call_count == 2


@pytest.mark.asyncio
async def test_generate_heading_duplicates_rejected_and_handled():
    llm = FakeLLM([
        "Why Retention Decides Early Traction",  # Duplicate of existing
        "Angle 2 on pricing strategy",  # Bad retry
    ])
    heading = await generate_section_heading(
        section_text="Retention is the bedrock of growth. [S1]",
        topic="pricing strategy",
        existing_headings=["Why Retention Decides Early Traction"],
        provider=llm,
    )
    assert heading in FALLBACK_HEADINGS
    assert heading != "Why Retention Decides Early Traction"


def test_repair_assembled_headings():
    bad_essay = (
        "# For Founders: How to Master Pricing Strategy\n\n"
        "Opening hook paragraph with at least thirty words to explain why pricing strategy is critical for every early stage founder navigating market headwinds and finding customer traction. [S1]\n\n"
        "## Angle 2 on pricing strategy\n\n"
        "- Point 1 [S1]\n- Point 2 [S1]\n\n"
        "**Key takeaway**: price high early.\n\n"
        "## Challenge Lies Identifying Right Product Features\n\n"
        "- Point 3 [S1]\n\n"
        "**Important**: features matter.\n\n"
        "## Actionable Takeaways\n\n"
        "- Test prices weekly [S1]."
    )
    repaired = repair_assembled_headings(bad_essay, topic="pricing strategy")
    assert "Angle 2 on pricing strategy" not in repaired
    assert "Challenge Lies Identifying Right Product Features" not in repaired
    assert "## What the guests say" in repaired
    assert "## Where teams get stuck" in repaired
    assert "## Actionable Takeaways" in repaired


def _essay_md(body_headings):
    hook = "This is a short hook paragraph that frames the topic with sufficient words to pass the hook threshold before the first header appears in the essay [S1].\n\n"
    body = ""
    for h in body_headings:
        body += f"## {h}\n\nSome body paragraph with claim [S1].\n\n- Bullet item [S1]\n\n**Bold insight** text.\n\n"
    takeaway = "## Actionable Takeaways\n\n- Takeaway one [S1].\n"
    return "# My Topic Headline: Guide For Startup Teams\n\n" + hook + body + takeaway


def test_validator_fails_on_duplicate_body_headings():
    md = _essay_md(["Framing Customer Needs First", "Framing Customer Needs First", "Understanding Market Pull Dynamics"])
    rep = validate_essay(md, available_sources=[], topic="my topic")
    assert "R_SPECIFIC_HEADINGS" in rep.failed_rules, rep.failed_rules


def test_validator_fails_on_old_template_heading():
    md = _essay_md([
        "Understanding Market Pull Dynamics",
        "Defining the Core Value Moment Early",  # old-list leak
        "Testing Channel Economics Early",
    ])
    rep = validate_essay(md, available_sources=[], topic="my topic")
    assert "R_SPECIFIC_HEADINGS" in rep.failed_rules, rep.failed_rules


def test_validator_fails_on_angle_or_stop_word_headings():
    md = _essay_md([
        "Angle 2 on Pricing Strategy",
        "Repeatedly Tweaking Onboarding Flow Exploring Other",
        "Testing Channel Economics Early",
    ])
    rep = validate_essay(md, available_sources=[], topic="pricing strategy")
    assert "R_SPECIFIC_HEADINGS" in rep.failed_rules, rep.failed_rules
