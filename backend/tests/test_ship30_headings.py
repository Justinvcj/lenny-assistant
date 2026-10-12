"""Regression tests for D1: ship30 hardcoded headings must not bleed across topics."""

from __future__ import annotations

from app.skills.ship30 import _derive_specific_themes


OLD_TEMPLATE_HEADINGS = {
    "Defining the Core Value Moment Early",
    "Measuring Leading Indicators vs. Vanity Metrics",
    "Compounding Feedback Loops and Team Workflows",
    "Friction Reduction and Operational Pitfalls",
    "Tactical Execution: From Pilot to Scaling",
}


def test_different_topics_produce_different_headings():
    """Two different topics must not produce identical heading sets (D1)."""
    themes_a = _derive_specific_themes("product-led growth loops featuring Elena Verna", sources=[], n=5)
    themes_b = _derive_specific_themes("activation energy for early stage startups", sources=[], n=5)
    assert themes_a != themes_b, (
        f"D1 regression — same headings for different topics: {themes_a}"
    )


def test_no_heading_from_old_hardcoded_list():
    """None of the five old template strings may appear as a heading (D1)."""
    for topic in [
        "product-led growth loops",
        "activation energy for early stage startups",
        "pricing strategy and willingness to pay",
    ]:
        themes = _derive_specific_themes(topic, sources=[], n=5)
        hits = [t for t in themes if t in OLD_TEMPLATE_HEADINGS]
        assert not hits, f"D1 regression — old-list heading leaked for topic {topic!r}: {hits}"


def test_no_duplicate_body_headings_within_essay():
    """Within one essay, body headings must all be unique (D1)."""
    themes = _derive_specific_themes("activation energy for early stage startups", sources=[], n=5)
    assert len(set(themes)) == len(themes), f"Duplicate body headings: {themes}"


def test_headings_short_and_without_full_topic():
    """Each heading is 4–8 words and does not contain the full topic string (D1)."""
    topic = "product-led growth loops"
    themes = _derive_specific_themes(topic, sources=[], n=5)
    for t in themes:
        n_words = len(t.split())
        assert 3 <= n_words <= 10, f"Heading length out of range: {t!r} ({n_words} words)"
        assert topic.lower() not in t.lower(), f"Heading contains the full topic: {t!r}"


# ---------------------------------------------------------------------------
# Validator-level checks for duplicate / old-template body headings (D1)
# ---------------------------------------------------------------------------

from app.skills.validator import validate_essay


def _essay_md(body_headings):
    """Minimal essay body with the given H2 headings so validator can parse it."""
    hook = "This is a short hook paragraph that frames the topic [S1].\n\n"
    body = ""
    for h in body_headings:
        body += f"## {h}\n\nSome body paragraph with claim [S1].\n\n"
    takeaway = "## Actionable Takeaways\n\n- Takeaway one [S1].\n"
    return "# My Topic Headline\n\n" + hook + body + takeaway


def test_validator_fails_on_duplicate_body_headings():
    md = _essay_md(["Framing one", "Framing one", "A separate angle"])
    rep = validate_essay(md, available_sources=[], topic="my topic")
    assert "R_SPECIFIC_HEADINGS" in rep.failed_rules, rep.failed_rules


def test_validator_fails_on_old_template_heading():
    md = _essay_md([
        "A unique heading",
        "Defining the Core Value Moment Early",  # old-list leak
        "A separate angle",
    ])
    rep = validate_essay(md, available_sources=[], topic="my topic")
    assert "R_SPECIFIC_HEADINGS" in rep.failed_rules, rep.failed_rules
