"""Ship 30 for 30 essay generation skill.

Pipeline per PROMPTS.md P6b:
  1. Retrieve / accept grounded sources.
  2. Plan outline: hook + N body sections + actionable takeaways.
  3. Draft SECTION BY SECTION with separate LLM calls (7B cannot write 1,250 in one pass).
  4. Assemble Markdown, run the validator.
  5. If validation fails, run ONE repair pass on failing sections. Never loop again.
  6. Return { content, word_count, report }.

NEVER loops more than once on repair.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.llm.base import ChatMessage, LLMProvider
from app.skills.validator import ValidationReport, validate_essay

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SectionPlan:
    title: str
    word_budget: int
    source_indices: List[int]  # 1-based indices into sources list
    is_hook: bool = False
    is_takeaway: bool = False


@dataclass
class EssayResult:
    content: str
    word_count: int
    report: ValidationReport
    repaired: bool = False


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_HOOK_PROMPT = """\
Write a compelling opening hook for a Ship 30-style essay about: {topic}

The hook must:
- Be 80-120 words (do NOT use a heading like "Introduction")
- Establish immediately why this topic matters for product leaders and founders
- Be direct, active-voice, and operator-focused
- Reference [S{first_src}] or [S{second_src}] naturally in-line

Sources available:
{sources_block}

Write ONLY the hook paragraph. No heading. No preamble."""

_SECTION_PROMPT = """\
Write the section titled "## {title}" for a Ship 30-style essay about: {topic}

Requirements:
- {word_budget} words (stay within ±50 words)
- Start with "## {title}" heading
- Use at least 1 bullet list or numbered list
- Bold at least 1 key insight with **bold**
- Alternate sentence lengths with dynamic rhythm (e.g. 1/3/1 or 1/5/1 cadences; avoid monotonous blocks)
- Fast rate of revelation: every sentence must push the thesis forward without circular fluff
- Pass 'The Tequila Test': reject generic platitudes in favor of contrarian, battle-tested operator insights
- Tag every factual claim with [S#] using ONLY these source indices: {allowed_tags}
- Active voice. No jargon. Operator tone (product leaders, founders).
- Do NOT invent claims. Ground everything in the sources below.

Sources:
{sources_block}

Write ONLY this section (heading + body). Nothing before or after."""

_TAKEAWAY_PROMPT = """\
Write the final section "## Actionable Takeaways" for a Ship 30-style essay about: {topic}

Requirements:
- 80-120 words
- Start with "## Actionable Takeaways"
- 3-4 bullet points summarising the key operator lessons
- Bold the most important phrase in each bullet
- Reference at least 1 [S#] from: {allowed_tags}
- Active voice. Decisive. No fluff.

Sources:
{sources_block}

Write ONLY this section."""

_REPAIR_PROMPT = """\
Revise this essay section to fix the following validation failures: {failures}

Topic: {topic}
Section to revise:
---
{section_content}
---

Available sources: {allowed_tags}
Sources text:
{sources_block}

Rules:
- Keep the ## heading exactly as-is
- Add [S#] citations if missing (ONLY from allowed indices above)
- Add bullets/bold if missing
- Stay within {word_budget} words
- Do NOT change the core content, only add what is missing

Return ONLY the revised section."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_sources_block(sources: List[Any], indices: List[int]) -> str:
    """Build a numbered source block for use in LLM prompts."""
    lines = []
    for idx in indices:
        if 1 <= idx <= len(sources):
            s = sources[idx - 1]
            title = getattr(s, "title", None) or s.get("title", "Episode") if isinstance(s, dict) else getattr(s, "title", "Episode")
            guest = getattr(s, "guest", None) or (s.get("guest", "") if isinstance(s, dict) else "")
            text = getattr(s, "text", None) or (s.get("text", "") if isinstance(s, dict) else "")
            header = f"[S{idx}] {title}" + (f" — {guest}" if guest else "")
            lines.append(f"{header}\n{text[:600]}")
    return "\n\n".join(lines) if lines else "(no sources)"


def _all_source_indices(sources: List[Any]) -> List[int]:
    return list(range(1, len(sources) + 1))


# ---------------------------------------------------------------------------
# 1. Plan outline
# ---------------------------------------------------------------------------


def plan_outline(topic: str, sources: List[Any]) -> List[SectionPlan]:
    """Build a section-by-section plan with word budgets.

    Structure:
      - Hook paragraph (~100 words, no heading)
      - 3-4 thematic body sections (~250-300 words each)
      - Actionable Takeaways (~100 words)

    Total budget: ~1,150-1,350 words, safely within 1,000-1,500 validator window.
    """
    n_sources = len(sources)
    if n_sources == 0:
        logger.warning("plan_outline called with 0 sources — essay will lack citations")

    all_idx = _all_source_indices(sources)

    # Distribute sources across sections
    n_body = 3 if n_sources <= 5 else 4
    per_section = max(2, n_sources // (n_body + 1))

    plans: List[SectionPlan] = []

    # Hook (no heading section)
    hook_srcs = all_idx[:min(2, len(all_idx))]
    plans.append(SectionPlan(
        title="Hook",
        word_budget=100,
        source_indices=hook_srcs if hook_srcs else ([1] if all_idx else []),
        is_hook=True,
    ))

    # Body section themes derived from topic
    themes = _derive_themes(topic, n_body)
    for i, theme in enumerate(themes):
        start = max(0, i * per_section)
        end = start + per_section + 1
        srcs = all_idx[start:end] if all_idx else []
        if not srcs and all_idx:
            srcs = all_idx[:2]
        plans.append(SectionPlan(
            title=theme,
            word_budget=270,
            source_indices=srcs,
        ))

    # Actionable Takeaways
    plans.append(SectionPlan(
        title="Actionable Takeaways",
        word_budget=100,
        source_indices=all_idx[-min(3, len(all_idx)):] if all_idx else [],
        is_takeaway=True,
    ))

    logger.info("plan_outline: topic=%r → %d sections", topic, len(plans))
    return plans


def _derive_themes(topic: str, n: int) -> List[str]:
    """Return n generic thematic titles from the topic string."""
    t = topic.strip().title()
    base = [
        f"Why {t} Matters",
        f"What the Data Says About {t}",
        f"How Top Founders Approach {t}",
        f"Common Mistakes in {t}",
        f"Scaling {t} Beyond Seed Stage",
    ]
    return base[:n]


# ---------------------------------------------------------------------------
# 2. Draft section
# ---------------------------------------------------------------------------


async def draft_section(
    plan: SectionPlan,
    topic: str,
    sources: List[Any],
    provider: LLMProvider,
) -> str:
    """Draft a single section using a targeted LLM call."""
    sources_block = _build_sources_block(sources, plan.source_indices)
    allowed_tags = ", ".join(f"[S{i}]" for i in plan.source_indices) or "[S1]"

    if plan.is_hook:
        first = plan.source_indices[0] if plan.source_indices else 1
        second = plan.source_indices[1] if len(plan.source_indices) > 1 else first
        prompt = _HOOK_PROMPT.format(
            topic=topic,
            first_src=first,
            second_src=second,
            sources_block=sources_block,
        )
    elif plan.is_takeaway:
        prompt = _TAKEAWAY_PROMPT.format(
            topic=topic,
            allowed_tags=allowed_tags,
            sources_block=sources_block,
        )
    else:
        prompt = _SECTION_PROMPT.format(
            topic=topic,
            title=plan.title,
            word_budget=plan.word_budget,
            allowed_tags=allowed_tags,
            sources_block=sources_block,
        )

    resp = await provider.chat(
        [ChatMessage(role="user", content=prompt)],
        temperature=0.3,
        max_tokens=600,
    )
    return resp.content.strip()


# ---------------------------------------------------------------------------
# 3. Assemble + validate
# ---------------------------------------------------------------------------


def assemble_essay(sections: List[str]) -> str:
    """Join drafted sections with blank-line separators."""
    return "\n\n".join(s.strip() for s in sections if s.strip())


# ---------------------------------------------------------------------------
# 4. Repair pass (max once)
# ---------------------------------------------------------------------------


async def repair_section(
    section_content: str,
    section_plan: SectionPlan,
    topic: str,
    sources: List[Any],
    provider: LLMProvider,
    failures: List[str],
) -> str:
    """One repair call for a failing section. Never called more than once per section."""
    sources_block = _build_sources_block(sources, _all_source_indices(sources))
    allowed_tags = ", ".join(f"[S{i}]" for i in _all_source_indices(sources)) or "[S1]"

    prompt = _REPAIR_PROMPT.format(
        failures="; ".join(failures),
        topic=topic,
        section_content=section_content,
        allowed_tags=allowed_tags,
        sources_block=sources_block,
        word_budget=section_plan.word_budget + 50,
    )
    resp = await provider.chat(
        [ChatMessage(role="user", content=prompt)],
        temperature=0.2,
        max_tokens=700,
    )
    return resp.content.strip()


# ---------------------------------------------------------------------------
# 5. Main entry point
# ---------------------------------------------------------------------------


async def generate_essay(
    topic: str,
    sources: List[Any],
    provider: LLMProvider,
) -> EssayResult:
    """Full Ship 30 essay pipeline.

    Args:
        topic:    Essay topic (from user message).
        sources:  List of retrieved transcript chunks (RetrievalResult or dicts).
        provider: LLM provider to call for text generation.

    Returns:
        EssayResult with content, word_count, and ValidationReport.
    """
    if not sources:
        logger.warning("generate_essay: no sources provided, essay will be ungrounded")

    # 1. Plan
    outline = plan_outline(topic, sources)

    # 2. Draft section-by-section
    drafted: List[str] = []
    for plan in outline:
        text = await draft_section(plan, topic, sources, provider)
        drafted.append(text)
        logger.debug("Drafted section %r (%d chars)", plan.title, len(text))

    # 3. Assemble
    essay_md = assemble_essay(drafted)

    # 4. Validate
    report = validate_essay(essay_md, sources)
    logger.info("Validation after draft: %s", report.summary())

    if report.passed:
        from app.skills.validator import count_words
        return EssayResult(
            content=essay_md,
            word_count=report.word_count,
            report=report,
            repaired=False,
        )

    # 5. ONE repair pass on failing sections only
    # Map section titles to their drafted text
    section_map: Dict[str, str] = {}
    for plan, text in zip(outline, drafted):
        section_map[plan.title] = text

    # Identify which sections have citation failures
    citation_failures_by_section: Dict[str, List[str]] = {}
    for rv in report.rule_results:
        if rv.rule_id == "R_CITATION" and not rv.passed:
            # Parse out section titles from the details string
            for fail_str in rv.details.split(";"):
                fail_str = fail_str.strip()
                for plan in outline:
                    if plan.title.lower() in fail_str.lower() and not plan.is_hook and not plan.is_takeaway:
                        citation_failures_by_section.setdefault(plan.title, []).append(fail_str)

    # Also repair sections related to R_FORMATTING / R_TAKEAWAY / R_HOOK if applicable
    repaired_any = False
    for plan, original_text in zip(outline, drafted):
        failures_for_section: List[str] = []

        if plan.is_hook and "R_HOOK" in report.failed_rules:
            failures_for_section.append("Hook is missing or too short. Write at least 30 words before the first heading.")
        if plan.is_takeaway and "R_TAKEAWAY" in report.failed_rules:
            failures_for_section.append("Takeaways section is missing or too short.")
        if not plan.is_hook and not plan.is_takeaway:
            if "R_FORMATTING" in report.failed_rules:
                failures_for_section.append("Add bullet list and bold emphasis (**text**).")
            if plan.title in citation_failures_by_section:
                failures_for_section.extend(citation_failures_by_section[plan.title])

        if failures_for_section:
            idx = outline.index(plan)
            drafted[idx] = await repair_section(
                original_text, plan, topic, sources, provider, failures_for_section
            )
            repaired_any = True
            logger.info("Repaired section %r", plan.title)

    # If R_LENGTH fails, we don't repair (word count is a drafting quality issue;
    # repair would require iterative expansion which violates the no-loop rule).

    # Reassemble after repairs
    essay_md = assemble_essay(drafted)
    final_report = validate_essay(essay_md, sources)
    logger.info("Validation after repair: %s", final_report.summary())

    return EssayResult(
        content=essay_md,
        word_count=final_report.word_count,
        report=final_report,
        repaired=repaired_any,
    )
