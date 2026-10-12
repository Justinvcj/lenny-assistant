"""STEP 4 regression: section headings derive from section content, not from the topic string."""

from __future__ import annotations

from app.skills.ship30 import derive_heading_from_section


def test_heading_from_first_supported_claim():
    section = (
        "## OLD PLACEHOLDER\n\n"
        "Activation happens in the first week when a user completes the first "
        "meaningful action [S1]. Teams that neglect this hemorrhage retention.\n"
    )
    h = derive_heading_from_section(section, topic="activation energy for startups")
    assert isinstance(h, str) and len(h) > 0
    assert len(h.split()) >= 3
    assert len(h.split()) <= 8
    assert "activation energy for startups" not in h.lower()
    assert ":" not in h


def test_heading_does_not_leak_full_topic():
    section = (
        "## OLD\n\n"
        "Product-led growth loops compound when every user creates incentives "
        "for the next invite [S2].\n"
    )
    h = derive_heading_from_section(section, topic="product-led growth loops")
    assert "product-led growth loops" not in h.lower()


def test_heading_fallback_when_no_supported_claim():
    section = "## OLD\n\nIntroduction without any citation.\n"
    h = derive_heading_from_section(section, topic="pricing strategy")
    assert len(h.split()) >= 3


def test_two_different_sections_get_different_headings():
    s1 = "## OLD\n\nQualitative interviews reveal the hidden drivers of churn [S1].\n"
    s2 = "## OLD\n\nQuant metrics should track activation within the first week [S2].\n"
    h1 = derive_heading_from_section(s1, topic="retention")
    h2 = derive_heading_from_section(s2, topic="retention")
    assert h1 != h2
