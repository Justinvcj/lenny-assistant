"""Unit tests for the Ship 30 essay skill pipeline (P6b).

Tests:
  - Validator: good essays pass, under-length fails R_LENGTH, missing hook fails R_HOOK,
    invalid citations fail R_CITATION.
  - plan_outline: correct section count and word budgets.
  - generate_essay (end-to-end with FakeLLMProvider): no real Ollama needed.
"""

from __future__ import annotations

import asyncio
import pytest
from dataclasses import dataclass, field
from typing import Any, List, Optional

from app.skills.validator import (
    ValidationReport,
    count_words,
    extract_sections,
    validate_essay,
)
from app.skills.ship30 import (
    EssayResult,
    SectionPlan,
    assemble_essay,
    generate_essay,
    plan_outline,
)
from app.llm.base import ChatMessage, ChatResponse, LLMProvider, ProviderHealth


# ---------------------------------------------------------------------------
# FakeLLMProvider
# ---------------------------------------------------------------------------


class FakeLLMProvider:
    """Deterministic fake LLM that returns preset text per call count."""

    def __init__(self, responses: Optional[List[str]] = None):
        self.responses = responses or []
        self.call_count = 0
        self.prompts: List[str] = []

    async def chat(
        self,
        messages: List[ChatMessage],
        *,
        system: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        extra: Optional[Any] = None,
    ) -> ChatResponse:
        self.call_count += 1
        self.prompts.append(messages[-1].content if messages else "")
        idx = min(self.call_count - 1, len(self.responses) - 1)
        text = self.responses[idx] if self.responses else f"Draft section #{self.call_count} [S1]."
        return ChatResponse(content=text, input_tokens=50, output_tokens=100, model="fake")

    async def embed(self, texts: List[str]) -> List[List[float]]:
        return [[0.1] * 768 for _ in texts]

    async def health(self) -> ProviderHealth:
        return ProviderHealth(ok=True, model="fake")


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeChunk:
    text: str
    title: str = "Test Episode"
    guest: str = "Test Guest"
    score: float = 0.80


def make_sources(n: int = 5) -> List[FakeChunk]:
    return [FakeChunk(text=f"Source content {i} about product growth and retention [S{i}].", title=f"Episode {i}") for i in range(1, n + 1)]


def make_good_essay(sources: List[Any]) -> str:
    """Build a valid Ship 30 essay with all rules satisfied (≥1,000 words)."""
    src_tags = " ".join(f"[S{i}]" for i in range(1, min(len(sources) + 1, 4)))

    paras_content = {
        1: "Longitudinal data from over 200 growth-stage venture investments demonstrates that cohort retention outranks top-of-funnel acquisition by an order of magnitude. When retention curves flatten above 20%, payback periods compress from eighteen months down to five. Teams prioritizing activation metrics build sustainable unit economics that weather market contractions.",
        2: "Operational cadence separates market leaders from also-rans in competitive product categories. Product engineering pods aligned around a singular North Star metric ship targeted iterations three times faster than functional silos. Weekly experiment retrospectives ensure insights propagate across the entire product organization systematically.",
        3: "Customer feedback loops must capture unvarnished reality rather than flattering vanity signals. Top operators schedule direct weekly user interviews with recently churned accounts to map friction points in onboarding flows. These qualitative inputs frequently reveal non-obvious positioning mismatches that quantitative telemetry obscures.",
        4: "Leading growth practitioners establish explicit cross-functional activation milestones before scaling marketing spend. When developers and marketers review identical onboarding telemetry, experimentation velocity accelerates rapidly. Documented user journey friction audits expose high-dropoff steps early in product lifecycles.",
        5: "Capital efficiency hinges directly on whether products solve acute workflow pain or incidental curiosities. Startups that identify high-frequency usage habits achieve organic expansion without heavy enterprise sales overhead. Sustainable compound growth emerges when existing customers become enthusiastic advocates within their peer networks.",
        6: "Rigorous cohort analysis provides the clearest lens into long-term customer lifetime value dynamics. By disaggregating user groups by acquisition channel and sign-up month, product teams uncover hidden degradation in underlying product value. This analytical discipline prevents costly premature expansion initiatives.",
        7: "Cross-functional alignment around activation metrics ensures all teams row in the same strategic direction. When marketing, sales, and product share accountability for month-one retention, customer onboarding experiences improve dramatically. Alignment reduces friction across the entire user conversion journey.",
        8: "Systematic friction reduction in initial product setup unlocks substantial compounding conversion gains. Removing extraneous form fields and deferring email verification allows new users to experience immediate product value. Immediate gratification reinforces positive behavioral feedback loops from first interaction.",
        9: "Distribution advantages amplify strong retention mechanics but cannot substitute for fundamental product value. When early adopters experience genuine delight during their initial workflow session, word-of-mouth loops ignite spontaneously across developer communities. Sustained growth compounds only when new users discover undeniable utility quickly.",
        10: "Product instrumentation must capture every micro-conversion along the user journey with granular telemetry. Logging critical aha moments empowers growth engineering squads to optimize onboarding sequences with statistical confidence. Continuous measurement separates elite technology teams from stagnant organizations.",
        11: "Pricing experiments conducted before achieving market resonance often introduce catastrophic confounding variables. Early monetization tests should focus on willingness-to-pay signals rather than aggressive short-term revenue extraction. Aligning monetization with realized customer value creates enduring commercial partnerships.",
        12: "Organizational focus remains the scarcest operational resource across early-stage technology companies. Saying no to peripheral enterprise feature requests preserves engineering bandwidth for core product polish. Extreme focus on the primary customer persona accelerates the path toward dominant market share.",
    }

    def body_para(n: int) -> str:
        """Return a distinct paragraph with citations."""
        text = paras_content.get(n, paras_content[1])
        return f"{text} {src_tags}"

    return f"""# Why Product-Market Fit Matters: The Early-Stage Founder's Guide to True PMF

This is why product-market fit matters for every founder building a company today.
The evidence is brutal: most startups fail not because of bad technology, but because they built something
nobody wanted badly enough to come back for. PMF is the difference between a product that grows on its
own and one that requires constant intervention to keep users engaged. {src_tags}

## Why PMF Matters

**Product-market fit** is the single most important milestone for any early-stage company.
Here is what the data shows:

- Companies with strong PMF retain 70% of cohorts at month 6 {src_tags}
- Without PMF, even excellent marketing fails to produce sustainable growth
- Founders who find PMF before scaling have 5x higher success rates in subsequent rounds

The evidence from hundreds of founders confirms this pattern. {body_para(1)}

{body_para(2)}

{body_para(8)}

The implications are significant: every dollar of growth spend before PMF is essentially wasted, because
the leaky bucket problem means you will spend just as much next month to maintain the same user count. {src_tags}

{body_para(6)}

{body_para(7)}

{body_para(9)}

## How to Measure PMF

**Measuring PMF** requires a systematic approach using leading indicators, not vanity metrics.

- Track the Sean Ellis PMF score: ask users "how disappointed would you be if this disappeared?" {src_tags}
- Monitor weekly active usage cohorts against your own baseline week over week
- Look for organic word-of-mouth that grows without paid acquisition driving it

The **40% threshold** is the gold standard most founders target on the Ellis survey. {body_para(3)}

Many teams confuse engagement spikes with retention — they are completely different signals. A product
launch can generate enormous short-term engagement while cohort curves still slope sharply to zero. {src_tags}
Track the 30-day, 60-day, and 90-day retention windows before declaring PMF achieved. {body_para(4)}

{body_para(10)}

{body_para(11)}

## Common Mistakes Founders Make

**Founders often mistake traction for PMF** — these are fundamentally different signals and the
confusion leads teams to scale prematurely, burning runway on a leaky growth engine.

- High sign-ups with low retention is a red flag, not a green light {src_tags}
- Investors can identify fake PMF during due diligence through cohort analysis
- **Premature scaling** before PMF is confirmed is the number one startup killer, bar none

{body_para(5)} Solving this requires discipline: do not let investor pressure or board dynamics push
you into growth mode before your retention curves have proven the product earns its place. {src_tags}

{body_para(12)}

The founders who resist this pressure and stay focused on the product consistently outperform those who
optimise for optics. The market eventually rewards honesty about where you are in the PMF journey. {src_tags}

## Actionable Takeaways

- **Measure retention weekly**: cohort curves that flatten at a non-zero level signal real PMF {src_tags}
- **Talk to churned users** every single week without exception — they reveal the truth about your product
- **Do not scale paid acquisition** until organic word-of-mouth exceeds 30% of new signups {src_tags}
- Set a 40% PMF score target on the Ellis survey before committing to your next funding round
"""


# ---------------------------------------------------------------------------
# Validator unit tests
# ---------------------------------------------------------------------------


class TestValidator:

    def test_good_essay_passes_all_rules(self):
        sources = make_sources(5)
        essay = make_good_essay(sources)
        report = validate_essay(essay, sources)
        assert report.passed, f"Expected pass but got: {report.failed_rules}\n{essay}"

    def test_under_length_fails_r_length(self):
        sources = make_sources(3)
        short_essay = "This is a very short essay. [S1]\n\n## Section One\n\nNot enough words here. **Bold.** [S1]\n\n- bullet\n\n## Actionable Takeaways\n\nToo short. [S1]"
        report = validate_essay(short_essay, sources)
        assert "R_LENGTH" in report.failed_rules

    def test_missing_hook_fails_r_hook(self):
        sources = make_sources(3)
        # Essay starts immediately with H2 — no hook
        essay = """## Why PMF Matters

**PMF matters** for all founders. [S1]

- bullet one
- bullet two [S1]

## Measuring PMF

Track cohort retention carefully. **Weekly actives** are key. [S2]

- metric one [S2]
- metric two

## Common Mistakes

**Premature scaling** kills startups. [S3]

- mistake one [S3]

## Actionable Takeaways

- **Measure first** [S1]
- Track retention
- Talk to churned users
"""
        # Make it long enough to not fail R_LENGTH
        essay = essay + "\n" + " ".join(["word"] * 700) + " [S1]"
        report = validate_essay(essay, sources)
        assert "R_HOOK" in report.failed_rules

    def test_invalid_citation_fails_r_citation(self):
        sources = make_sources(3)  # valid: S1, S2, S3
        essay = make_good_essay(sources)
        # Inject an out-of-bounds citation
        bad_essay = essay.replace("[S3]", "[S99]")
        report = validate_essay(bad_essay, sources)
        assert "R_CITATION" in report.failed_rules

    def test_no_formatting_fails_r_formatting(self):
        sources = make_sources(3)
        essay_no_fmt = f"""This is the opening hook for the essay about product growth. [S1]
It matters because retention drives revenue.

## Section One

This section has no bullets and no bold text at all.
Just plain prose about product market fit. [S1]

## Section Two

More plain prose here without formatting elements.
Still no bullets or bold emphasis to speak of. [S2]

## Section Three

Third body section also lacks formatting.
Plain text only here. [S3]

## Actionable Takeaways

Take action on the lessons above. Learn from the data. [S1]
"""
        report = validate_essay(essay_no_fmt, sources)
        assert "R_FORMATTING" in report.failed_rules

    def test_missing_takeaway_fails_r_takeaway(self):
        sources = make_sources(3)
        essay = f"""Opening hook paragraph here with sufficient length. [S1]

## Section One

**Bold insight here.** Content about PMF. [S1]

- bullet one
- bullet two

## Section Two

**Second insight.** More content. [S2]

- another bullet [S2]

## Section Three

**Third insight.** Final body section. [S3]

- yet another bullet [S3]
"""
        # Long enough to avoid R_LENGTH
        essay = essay + "\n" + " ".join(["word"] * 500) + " [S1]"
        report = validate_essay(essay, sources)
        assert "R_TAKEAWAY" in report.failed_rules


# ---------------------------------------------------------------------------
# plan_outline tests
# ---------------------------------------------------------------------------


class TestPlanOutline:

    def test_plan_outline_structure(self):
        sources = make_sources(6)
        plans = plan_outline("product-market fit", sources)
        # Must have hook + body sections + takeaway
        assert plans[0].is_hook
        assert plans[-1].is_takeaway
        body = [p for p in plans if not p.is_hook and not p.is_takeaway]
        assert 3 <= len(body) <= 5

    def test_plan_outline_word_budgets(self):
        sources = make_sources(5)
        plans = plan_outline("retention", sources)
        for p in plans:
            assert p.word_budget > 0

    def test_plan_outline_no_sources(self):
        plans = plan_outline("topic", [])
        assert len(plans) >= 3  # still produces a plan

    def test_total_budget_within_target(self):
        sources = make_sources(5)
        plans = plan_outline("growth loops", sources)
        total = sum(p.word_budget for p in plans)
        # Total budget should be in 900-1500 range
        assert 900 <= total <= 1500


# ---------------------------------------------------------------------------
# generate_essay end-to-end with FakeLLMProvider
# ---------------------------------------------------------------------------


HOOK_TEXT = """Building a product people love is the hardest challenge in tech today.
Every founder faces the same brutal truth: you can have perfect technology and
still fail because nobody cares enough to come back. This essay explains the
key lessons from operators who cracked the code. [S1] [S2]"""

SECTION_TEXTS = [
    """## Why PMF Matters

**Product-market fit** is the foundation of everything else. Without it, growth is a
leaky bucket that marketing spend cannot fill.

- Companies with strong PMF retain 70%+ of cohorts at month 6 [S1]
- Founders who prioritise PMF before scaling have 5x higher success rates [S2]
- **The data is unambiguous**: retention cohorts tell the truth [S1]

Measure it early and measure it often. [S2]""",

    """## How to Measure PMF

**Retention cohorts** are the leading indicator every product team must track weekly.

- Use the Sean Ellis 40% test: "how disappointed if this product disappeared?" [S3]
- Monitor DAU/MAU ratio — top-quartile products exceed 50% [S3]
- **Look for organic word-of-mouth** growing without paid acquisition [S4]

The 40% threshold is the gold standard. [S4]""",

    """## Common Mistakes Founders Make

**Premature scaling** is the number one mistake in the startup playbook.

- Scaling ads before PMF wastes runway and distorts cohort data [S5]
- Mistaking viral loops for retention is a classic trap [S5]
- **Churned users hold the answer** — talk to them every week [S1]

Avoid the growth-at-all-costs mindset until retention is proven. [S2]""",

    """## Actionable Takeaways

- **Measure retention weekly**: flat cohort curves signal real PMF [S1]
- Talk to churned users every single week — they reveal the truth
- **Don't scale paid acquisition** until organic word-of-mouth exceeds 30% of signups [S3]
- Set a 40% PMF score target before your next funding round [S4]""",
]


@pytest.mark.asyncio
async def test_generate_essay_calls_provider_per_section():
    """generate_essay makes one LLM call per outline section."""
    sources = make_sources(5)
    plans = plan_outline("PMF", sources)
    n_sections = len(plans)

    # Provide enough text to pass validation
    responses = [HOOK_TEXT] + SECTION_TEXTS[:n_sections - 1]
    # Pad if needed
    while len(responses) < n_sections:
        responses.append(SECTION_TEXTS[-1])

    provider = FakeLLMProvider(responses=responses)
    result = await generate_essay("PMF", sources, provider)
    # At least one call per section, plus up to 2 expansion passes if word count < 1100
    assert provider.call_count >= n_sections
    assert isinstance(result, EssayResult)
    assert result.content
    assert result.word_count > 0


@pytest.mark.asyncio
async def test_generate_essay_returns_validation_report():
    """generate_essay always returns a ValidationReport."""
    sources = make_sources(5)
    provider = FakeLLMProvider(responses=[HOOK_TEXT] + SECTION_TEXTS)
    result = await generate_essay("retention", sources, provider)
    assert result.report is not None
    assert isinstance(result.report.passed, bool)


@pytest.mark.asyncio
async def test_generate_essay_no_sources_degrades_gracefully():
    """generate_essay with 0 sources completes without error (citations will fail)."""
    provider = FakeLLMProvider(responses=[HOOK_TEXT] + SECTION_TEXTS)
    result = await generate_essay("any topic", [], provider)
    assert isinstance(result, EssayResult)
    # With 0 sources, R_CITATION should fail (no valid source set)
    # but we should still get content back
    assert result.content


@pytest.mark.asyncio
async def test_generate_essay_repair_pass_not_looped():
    """If validation fails, repair runs at most once (call count <= 2 * n_sections)."""
    sources = make_sources(5)
    plans = plan_outline("growth", sources)
    n_sections = len(plans)

    # All responses are garbage that will fail validation
    bad_response = "Short answer."
    provider = FakeLLMProvider(responses=[bad_response] * (n_sections * 2 + 2))

    result = await generate_essay("growth", sources, provider)
    # Max calls = n_sections (draft) + n_sections (repair) = 2 * n_sections
    assert provider.call_count <= n_sections * 2 + 2
    # result is always returned — never raises
    assert isinstance(result, EssayResult)


def test_ship30_rules_have_verified_sources():
    """Verify that all rules in ship30_rules.yaml cite verified guide sections with 0 unverified labels."""
    from app.skills.validator import load_rules_config
    config = load_rules_config()
    rules = config.get("rules", [])
    assert len(rules) >= 7

    for rule in rules:
        source = rule.get("source", "")
        assert source, f"Rule {rule.get('id')} has empty source"
        assert "DRAFT-UNVERIFIED" not in source, f"Rule {rule.get('id')} has unverified source label: {source}"
        assert rule.get("id"), "Rule missing id"
        assert rule.get("name"), "Rule missing name"
        assert rule.get("description"), "Rule missing description"

    rule_ids = {r["id"] for r in rules}
    expected_ids = {"R_LENGTH", "R_HOOK", "R_STRUCTURE", "R_FORMATTING", "R_TAKEAWAY", "R_CITATION"}
    assert expected_ids.issubset(rule_ids)
