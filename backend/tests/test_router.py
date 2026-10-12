"""Unit tests for the Deterministic Intent Router."""

import pytest
from app.agent.router import Intent, classify, classify_intent


class DummyMessage:
    """Helper mock object mimicking Message or MessageResponse."""

    def __init__(self, role: str, intent: str | None = None):
        self.role = role
        self.intent = intent


# --- Test Cases TC01 to TC34 per Explorer 1 specification ---

ROUTER_TEST_CASES = [
    # QA (Core Domain)
    ("What do guests say about activation in the first week?", None, Intent.QA, "TC01: standard onboarding query"),
    ("How should early stage startups approach pricing and monetization?", None, Intent.QA, "TC02: monetization query"),
    ("What are Jason Lemkin's favorite interview questions for sales?", None, Intent.QA, "TC03: hiring query"),
    ("Tell me about Elena Verna's views on B2B product-led growth.", None, Intent.QA, "TC04: PLG knowledge"),
    ("How should founders give away their Legos as the company scales?", None, Intent.QA, "TC05: Molly Graham framework"),
    ("What is the difference between retention and engagement?", None, Intent.QA, "TC06: metric definitions"),
    # QA (Follow-ups)
    ("What about for B2B?", [DummyMessage("assistant", "QA")], Intent.QA, "TC07: short follow-up retains QA"),
    ("Which episode did that quote come from?", [DummyMessage("assistant", "QA")], Intent.QA, "TC08: metadata follow-up retains QA"),
    ("Can you give me another example of that from the podcast?", [DummyMessage("assistant", "QA")], Intent.QA, "TC09: clarification follow-up retains QA"),
    # QA (Off-topic queries routed to QA for downstream retrieval rejection)
    ("How do I bake sourdough bread with wild yeast?", None, Intent.QA, "TC10: off-topic baking"),
    ("Who won the 2026 World Cup football championship?", None, Intent.QA, "TC11: off-topic sports"),
    ("What are the capital gains tax rates for commercial real estate in Texas?", None, Intent.QA, "TC12: off-topic tax"),
    # QA (Informational query containing the word 'essay')
    ("Did Paul Graham ever discuss writing essays on the podcast?", None, Intent.QA, "TC13: inquiry about essays"),
    # ESSAY (Ship 30 & Atomic Essay)
    ("Turn that into a Ship 30 essay", [DummyMessage("assistant", "QA")], Intent.ESSAY, "TC14: ship 30 essay"),
    ("Write a ship30 essay on product-market fit", None, Intent.ESSAY, "TC15: case-insensitive ship30 essay"),
    ("Can you draft a Ship 30 for 30 post about activation loops?", None, Intent.ESSAY, "TC16: ship 30 for 30 post"),
    ("Write an atomic essay on giving away your Legos", None, Intent.ESSAY, "TC17: atomic essay"),
    # ESSAY (Direct Directives & Transformations)
    ("Write an essay on why retention is the foundation of growth", None, Intent.ESSAY, "TC18: write an essay on"),
    ("Draft an essay about viral acquisition loops", None, Intent.ESSAY, "TC19: draft an essay about"),
    ("Turn this into an essay", [DummyMessage("assistant", "QA")], Intent.ESSAY, "TC20: turn this into an essay"),
    ("Turn that into an article for my newsletter", [DummyMessage("assistant", "QA")], Intent.ESSAY, "TC21: turn that into an article"),
    ("Draft a post about common onboarding mistakes", None, Intent.ESSAY, "TC22: draft a post about"),
    # ESSAY (Multi-turn Refinement)
    ("Rewrite section 2 with a punchier hook and shorter sentences", [DummyMessage("assistant", "ESSAY")], Intent.ESSAY, "TC23: revise essay hook"),
    ("Make it shorter and strengthen the takeaway", [DummyMessage("assistant", "ESSAY")], Intent.ESSAY, "TC24: condense essay"),
    # ARTIFACT (HTML, Landing Page, Markdown Doc)
    ("Make an HTML one-pager about retention loops", None, Intent.ARTIFACT, "TC25: html one-pager"),
    ("Format this advice as an html page", [DummyMessage("assistant", "QA")], Intent.ARTIFACT, "TC26: html page"),
    ("Generate a mock landing page for a B2B SaaS onboarding flow", None, Intent.ARTIFACT, "TC27: landing page"),
    ("Create a markdown doc summarizing the top 5 pricing models", None, Intent.ARTIFACT, "TC28: markdown doc"),
    # ARTIFACT (Table, Checklist, Template, Code)
    ("Put the differences between sales-led and product-led growth in a comparison table", None, Intent.ARTIFACT, "TC29: comparison table"),
    ("Give me an actionable hiring checklist for evaluating a Head of Product", None, Intent.ARTIFACT, "TC30: hiring checklist"),
    ("Create a 30-day onboarding template for new PMs", None, Intent.ARTIFACT, "TC31: onboarding template"),
    ("Write a Python script to calculate net revenue retention from cohort data", None, Intent.ARTIFACT, "TC32: python script"),
    # ARTIFACT (Multi-turn Refinement)
    ("Add another column to the table for customer acquisition cost", [DummyMessage("assistant", "ARTIFACT")], Intent.ARTIFACT, "TC33: add column to table"),
    # Edge Cases (Negations & Suppression)
    ("Please do not write an essay, just give me a direct answer", None, Intent.QA, "TC34: negation suppresses essay"),
]


@pytest.mark.parametrize("query,history,expected_intent,desc", ROUTER_TEST_CASES)
def test_router_phrasings(query: str, history: list | None, expected_intent: Intent, desc: str):
    """Verify that classify_intent accurately classifies all 34 cataloged phrasings."""
    res = classify_intent(query, history=history)
    assert res == expected_intent, f"Failed on {desc}: expected {expected_intent}, got {res}"


def test_classify_alias():
    """Verify classify is an exact alias for classify_intent."""
    assert classify("Write a ship30 essay") == Intent.ESSAY
    assert classify("What is retention?") == Intent.QA


def test_empty_and_whitespace_input():
    """Verify empty or whitespace-only queries default to QA."""
    assert classify_intent("") == Intent.QA
    assert classify_intent("   \n\t  ") == Intent.QA


def test_negation_artifact():
    """Verify that negation of artifact triggers falls back to QA."""
    assert classify_intent("Don't create a table, just explain it in words") == Intent.QA
    assert classify_intent("No html page please, give me raw advice") == Intent.QA
    assert classify_intent("Never generate code snippets") == Intent.QA


def test_artifact_refinement_without_history():
    """Verify that an ambiguous editing instruction without artifact history defaults to QA."""
    assert classify_intent("Add another column", history=None) == Intent.QA


def test_essay_refinement_without_history():
    """Verify that a refinement phrase without essay history defaults to QA."""
    assert classify_intent("Make it punchier", history=None) == Intent.QA


def test_new_question_during_essay_session_routes_to_qa():
    """Verify that a substantive knowledge question asked during an essay session routes to QA."""
    history = [DummyMessage("assistant", "ESSAY")]
    assert classify_intent("Who was the guest on episode 42?", history=history) == Intent.QA


def test_dict_history_support():
    """Verify history can be provided as a list of dicts."""
    history = [{"role": "assistant", "intent": "ARTIFACT"}]
    assert classify_intent("Add another column to the table", history=history) == Intent.ARTIFACT


def test_transform_disambiguation():
    """Verify 'turn that into...' routes to ARTIFACT when target is table/html, else ESSAY."""
    assert classify_intent("Turn that into a comparison table") == Intent.ARTIFACT
    assert classify_intent("Turn that into an html page") == Intent.ARTIFACT
    assert classify_intent("Turn that into a checklist") == Intent.ARTIFACT
    assert classify_intent("Turn that into an essay") == Intent.ESSAY
    assert classify_intent("Turn that into a post") == Intent.ESSAY
