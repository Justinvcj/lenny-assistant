"""Ship 30 for 30 essay generation skill.

Pipeline per PROMPTS.md P6b and Round 2 specification:
  1. Retrieve / accept grounded sources.
  2. Draft H1 headline derived from topic and strongest supported claim.
  3. Plan outline: slot ids and word budgets only (no user-visible section titles).
  4. Draft SECTION BY SECTION with separate LLM calls.
  5. Enforce section word count budgets with targeted expansion/trimming.
  6. Generate heading for each body section after its body is final with ONE short LLM call.
  7. Assemble Markdown with strict citation normalization and paragraph deduplication.
  8. Deterministically validate and repair assembled headings before storage.
  9. Run validator. If validation fails, run ONE repair pass on failing sections.
  10. Return { content, word_count, report, repaired }.

NEVER loops more than once on repair.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.agent.verify import (
    deduplicate_paragraphs,
    has_illegal_citations,
    normalize_citations,
    verify_essay_groundedness,
)
from app.llm.base import ChatMessage, LLMProvider
from app.skills.validator import ValidationReport, count_body_words, count_words, validate_essay

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SectionPlan:
    slot_id: str
    word_budget: int
    source_indices: List[int]  # 1-based indices into sources list
    is_hook: bool = False
    is_takeaway: bool = False

    @property
    def title(self) -> str:
        return self.slot_id


@dataclass
class EssayResult:
    content: str
    word_count: int
    report: ValidationReport
    repaired: bool = False
    title: str = ""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FALLBACK_HEADINGS: List[str] = [
    "What the guests say",
    "Where teams get stuck",
    "How to put it into practice",
    "What to measure",
    "A common mistake to avoid",
    "A real example",
]

STOP_WORDS_END = {
    "a", "an", "the", "of", "to", "for", "in", "on", "with",
    "and", "or", "other", "about", "from", "by", "at", "as",
}

KNOWN_BAD_HEADINGS = {
    "challenge lies identifying right product features",
    "repeatedly tweaking onboarding flow exploring other",
    "jeanne dewitt grosser seasoned marketer advises",
}


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_HOOK_PROMPT = """\
Write a compelling opening hook for a Ship 30-style essay about: {topic}

The hook must:
- Be 100-140 words (do NOT use any heading like "Introduction" or "Hook")
- Establish immediately why this topic matters for product leaders and founders
- Be direct, active-voice, and operator-focused
- Reference [S{first_src}] or [S{second_src}] naturally in-line
- Do NOT repeat or include the main headline

Sources available:
{sources_block}

Write ONLY the hook paragraph. No heading. No preamble."""

_SECTION_PROMPT = """\
Write a body section for a Ship 30-style essay about: {topic}

Requirements:
- {word_budget} words (stay within 80% to 125% of this budget: {min_budget}–{max_budget} words)
- Focus on a single distinct operational theme or contrarian insight supported by the sources
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

Write ONLY this section body. Do not include any heading. Nothing before or after."""

_TAKEAWAY_PROMPT = """\
Write the final section "## Actionable Takeaways" for a Ship 30-style essay about: {topic}

Requirements:
- 100-140 words
- Start with "## Actionable Takeaways"
- 3-4 bullet points summarising the key operator lessons
- Bold the most important phrase in each bullet
- Reference at least 1 [S#] from: {allowed_tags}
- Active voice. Decisive. No fluff.

Sources:
{sources_block}

Write ONLY this section."""

_EXPANSION_PROMPT = """\
Expand the following essay section to add more operator depth, tactical examples, and execution nuance based ONLY on the provided unused source passages.
Target: Add about {additional_words} words to this section.

Topic: {topic}
Current section content:
---
{section_content}
---

Unused grounding sources available:
{sources_block}
Allowed citation tags: {allowed_tags}

Requirements:
- If a "## " heading is present, keep it exactly as-is
- Add concrete operator frameworks or tactical execution steps based SOLELY on the unused sources above
- Never hallucinate claims not present in the sources
- Keep all existing [S#] tags and citations; add [S#] tags from allowed tags for newly added claims
- Maintain bullet list and bold insights (**text**)

Return ONLY the complete expanded section."""

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
- State ONLY what the source says; write fewer sentences if support is thin
- Add [S#] citations if missing (ONLY from allowed indices above)
- Add bullets/bold if missing
- Stay within {word_budget} words
- Do NOT duplicate paragraphs or add introductory hooks

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
            title = getattr(s, "title", None) or (s.get("title", "Episode") if isinstance(s, dict) else "Episode")
            guest = getattr(s, "guest", None) or (s.get("guest", "") if isinstance(s, dict) else "")
            text = getattr(s, "text", None) or (s.get("text", "") if isinstance(s, dict) else "")
            header = f"[S{idx}] {title}" + (f" — {guest}" if guest else "")
            lines.append(f"{header}\n{text[:600]}")
    return "\n\n".join(lines) if lines else "(no sources)"


def _all_source_indices(sources: List[Any]) -> List[int]:
    return list(range(1, len(sources) + 1))


# ---------------------------------------------------------------------------
# 1. Headline & Outline Planning
# ---------------------------------------------------------------------------


async def draft_headline(topic: str, sources: List[Any], provider: LLMProvider) -> str:
    """Generate an H1 headline following the Ship 30 headline framework."""
    strongest_claim = ""
    if sources:
        s0 = sources[0]
        txt = getattr(s0, "text", "") if hasattr(s0, "text") else (s0.get("text", "") if isinstance(s0, dict) else "")
        strongest_claim = txt[:400]

    prompt = f"""Write an H1 headline for a Ship 30 essay following the Ship 30 headline framework.
Topic: {topic}
Key source insight: {strongest_claim}

Ship 30 Headline Framework:
1. Who it is for (e.g. 'For Product Leaders and Founders')
2. What it is about (the core mechanism)
3. Why to read it (the concrete payoff, outcome, or contrarian lesson)

Format: Return ONLY the single line: '# [Headline]'. No quotes, no preamble."""

    try:
        resp = await provider.chat(
            [ChatMessage(role="user", content=prompt)],
            temperature=0.2,
            max_tokens=80,
        )
        h1 = resp.content.strip()
        lines = [line.strip() for line in h1.split("\n") if line.strip()]
        for line in lines:
            if line.startswith("# ") and not line.startswith("##"):
                return line
            elif line.startswith("#"):
                return "# " + line.lstrip("# ")
    except Exception as exc:
        logger.warning("draft_headline failed: %s", exc)

    clean_t = topic.strip().title()
    return f"# For Product Leaders: How to Operationalize {clean_t} to Drive Compounding Growth"


def plan_outline(topic: str, sources: List[Any]) -> List[SectionPlan]:
    """Build a section-by-section plan with slot ids and word budgets.

    The plan holds ONLY slot ids and word budgets (no user-visible titles).
    """
    all_idx = _all_source_indices(sources)
    n_body = 5

    plans: List[SectionPlan] = []

    # Hook (no heading section) ~120 words
    hook_srcs = all_idx[:min(2, len(all_idx))]
    plans.append(SectionPlan(
        slot_id="hook",
        word_budget=120,
        source_indices=hook_srcs if hook_srcs else ([1] if all_idx else []),
        is_hook=True,
    ))

    # 5 Body section slots (~240 words each)
    for i in range(n_body):
        if all_idx:
            src1 = all_idx[i % len(all_idx)]
            src2 = all_idx[(i + 1) % len(all_idx)]
            srcs = [src1] if src1 == src2 else [src1, src2]
        else:
            srcs = []
        plans.append(SectionPlan(
            slot_id=f"body_{i + 1}",
            word_budget=240,
            source_indices=srcs,
        ))

    # Actionable Takeaways ~120 words
    takeaway_srcs = all_idx[-min(3, len(all_idx)):] if all_idx else []
    plans.append(SectionPlan(
        slot_id="takeaways",
        word_budget=120,
        source_indices=takeaway_srcs,
        is_takeaway=True,
    ))

    logger.info("plan_outline: topic=%r → %d sections (total planned %d words)",
                topic, len(plans), sum(p.word_budget for p in plans))
    return plans


# ---------------------------------------------------------------------------
# Heading validation, generation, and repair
# ---------------------------------------------------------------------------


def validate_heading(
    heading: str,
    topic: str = "",
    existing_headings: Optional[Sequence[str]] = None,
) -> Tuple[bool, Optional[str]]:
    """Deterministically validate a section heading.

    Rules:
    - 4 to 8 words
    - First character uppercase
    - Must NOT end with a stop word (a, an, the, of, to, for, in, on, with, and, or, other, about, from, by, at, as)
    - Must not match "Angle <number>"
    - No duplicates (case-insensitive)
    - At most ONE heading contains the topic string (normalize case and hyphens before comparing)
    - No sentence fragments or plan titles
    """
    raw_h = heading.strip()
    if not raw_h:
        return False, "Heading is empty"

    clean_h = raw_h.strip('"\'`').strip()
    if ":" in clean_h:
        return False, "Heading must not contain colons"
    if '"' in clean_h or "'" in clean_h:
        return False, "Heading must not contain quotation marks"
    if raw_h.endswith((".", ",", ";", "!", "?")):
        return False, "Heading must not end with trailing punctuation"

    clean_h = clean_h.rstrip(".:,;!?").strip()
    if not clean_h:
        return False, "Heading is empty"

    # Known bad headings / fragments
    if clean_h.lower() in KNOWN_BAD_HEADINGS:
        return False, f"Heading {clean_h!r} is a sentence fragment"

    # Plan slot / title rejection
    if clean_h.lower() in {"hook", "takeaway", "takeaways", "actionable takeaways"} or re.match(
        r"^(?:body|section|slot)[_\s]*\d+$", clean_h, re.I
    ):
        return False, f"Heading {clean_h!r} is a plan slot or title"

    # Angle <number>
    if re.search(r"\bAngle\s+\d+\b", clean_h, re.IGNORECASE):
        return False, "Heading must not match 'Angle <number>'"

    # Fragment patterns
    if re.search(r"\b(advises|explains|says|suggests|notes|shares|warns|argues|recommends)\b$", clean_h, re.I):
        return False, "Heading must not end with a reporting verb"
    if re.search(r"\b(lies|stands|remains)\s+[a-z]+ing\b", clean_h, re.I):
        return False, "Heading must not be a sentence fragment"

    # First character uppercase
    if not clean_h[0].isupper():
        return False, "First character must be uppercase"

    # Word count: 4 to 8 words (or from FALLBACK_HEADINGS)
    words = clean_h.split()
    if clean_h not in FALLBACK_HEADINGS:
        if len(words) < 4 or len(words) > 8:
            return False, f"Heading must have 4 to 8 words (got {len(words)})"

    # Must not end with a stop word
    last_word = re.sub(r"[^\w]", "", words[-1]).lower()
    if last_word in STOP_WORDS_END:
        return False, f"Heading must not end with stop word '{words[-1]}'"

    # Duplicates check (case-insensitive)
    if existing_headings:
        clean_existing = [h.strip().lower() for h in existing_headings if h.strip()]
        if clean_h.lower() in clean_existing:
            return False, f"Duplicate heading {clean_h!r}"

    # Topic string check: at most one heading contains the topic string
    if topic:
        norm_topic = re.sub(r"[\s\-]+", " ", topic).strip().lower()
        if len(norm_topic.split()) >= 2:
            norm_h = re.sub(r"[\s\-]+", " ", clean_h).strip().lower()
            if norm_topic in norm_h:
                already_has_topic = False
                if existing_headings:
                    for eh in existing_headings:
                        if norm_topic in re.sub(r"[\s\-]+", " ", eh).strip().lower():
                            already_has_topic = True
                            break
                if already_has_topic:
                    return False, f"At most one heading may contain topic string {topic!r}"

    return True, None


async def generate_section_heading(
    section_text: str,
    topic: str,
    existing_headings: Sequence[str],
    provider: LLMProvider,
) -> str:
    """Generate a heading for a final section body using ONE short LLM call."""
    lines = [l for l in section_text.splitlines() if not l.lstrip().startswith("#")]
    body_only = "\n".join(lines).strip() or section_text.strip()

    prompt = (
        "Given the following essay section text, output only a heading of 4 to 8 words "
        "in Title Case, specific to the section's main claim, no colon, no quotation marks, "
        "no trailing punctuation, not containing the essay topic string, and not a sentence fragment.\n\n"
        f"Section text:\n{body_only}"
    )

    # Attempt 1
    resp = await provider.chat(
        [ChatMessage(role="user", content=prompt)],
        temperature=0.2,
        max_tokens=60,
    )
    raw_h = resp.content.strip().splitlines()[0].lstrip("#").strip() if resp.content else ""
    raw_h = raw_h.strip('"\'`').rstrip(".:,;!?").strip()

    valid, reason = validate_heading(raw_h, topic=topic, existing_headings=existing_headings)
    if valid:
        return raw_h

    logger.warning("Heading attempt 1 invalid (%s): %r. Retrying once.", reason, raw_h)

    # Retry once with failure reason appended to instruction
    retry_prompt = (
        f"{prompt}\n\n"
        f"Previous attempt was rejected: {reason}. "
        "Please output only a valid heading meeting all instructions."
    )
    resp2 = await provider.chat(
        [ChatMessage(role="user", content=retry_prompt)],
        temperature=0.2,
        max_tokens=60,
    )
    raw_h2 = resp2.content.strip().splitlines()[0].lstrip("#").strip() if resp2.content else ""
    raw_h2 = raw_h2.strip('"\'`').rstrip(".:,;!?").strip()

    valid2, reason2 = validate_heading(raw_h2, topic=topic, existing_headings=existing_headings)
    if valid2:
        return raw_h2

    logger.warning("Heading attempt 2 invalid (%s): %r. Using fallback label.", reason2, raw_h2)

    # Fallback to first unused label from FALLBACK_HEADINGS
    clean_existing = [h.strip().lower() for h in existing_headings]
    for fallback in FALLBACK_HEADINGS:
        if fallback.lower() not in clean_existing:
            return fallback

    return FALLBACK_HEADINGS[0]


def repair_assembled_headings(essay_md: str, topic: str = "") -> str:
    """Validate and repair headings on assembled markdown essay.

    Ensures no bad heading reaches storage. Body headings that fail validation
    are replaced with the first unused label from FALLBACK_HEADINGS.
    """
    lines = essay_md.splitlines()
    repaired_lines = []
    seen_headings: List[str] = []

    for line in lines:
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            h = m.group(1).strip()
            # Hook has no heading; Takeaways & Sources are fixed
            if h in ("Actionable Takeaways", "Sources") or h.startswith("Actionable Takeaways"):
                repaired_lines.append(line)
                continue
            valid, reason = validate_heading(h, topic=topic, existing_headings=seen_headings)
            if valid:
                seen_headings.append(h)
                repaired_lines.append(line)
            else:
                # Pick first unused fallback
                chosen = None
                clean_seen = [sh.lower() for sh in seen_headings]
                for fb in FALLBACK_HEADINGS:
                    if fb.lower() not in clean_seen:
                        chosen = fb
                        break
                if not chosen:
                    chosen = FALLBACK_HEADINGS[0]
                seen_headings.append(chosen)
                repaired_lines.append(f"## {chosen}")
                logger.info("Repaired assembled heading: %r -> %r (reason: %s)", h, chosen, reason)
        else:
            repaired_lines.append(line)

    return "\n".join(repaired_lines)


def derive_heading_from_section(section_text: str, topic: str = "") -> str:
    """Deterministic fallback helper for deriving a heading from a section."""
    lines = [l for l in section_text.splitlines() if not l.lstrip().startswith("#")]
    body = "\n".join(lines).strip() or section_text.strip()
    words = [w for w in re.findall(r"[A-Za-z]+", body) if len(w) > 2]
    if len(words) >= 4:
        candidate = " ".join(w.capitalize() for w in words[:5])
        valid, _ = validate_heading(candidate, topic=topic)
        if valid:
            return candidate
    for fb in FALLBACK_HEADINGS:
        valid, _ = validate_heading(fb, topic=topic)
        if valid:
            return fb
    return FALLBACK_HEADINGS[0]


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
    min_budget = int(plan.word_budget * 0.80)
    max_budget = int(plan.word_budget * 1.25)

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
            word_budget=plan.word_budget,
            min_budget=min_budget,
            max_budget=max_budget,
            allowed_tags=allowed_tags,
            sources_block=sources_block,
        )

    resp = await provider.chat(
        [ChatMessage(role="user", content=prompt)],
        temperature=0.3,
        max_tokens=650,
    )
    raw_text = resp.content.strip()

    # Post-process drafted section
    if plan.is_hook:
        # Strip any accidental headings from the hook
        cleaned = re.sub(r"^#+\s+[^\n]+\n*", "", raw_text).strip()
        return cleaned

    if not plan.is_hook and not plan.is_takeaway:
        # Strip any heading so drafted[i] contains the section body.
        # Its heading will be generated after the body is final.
        cleaned = re.sub(r"^##\s+[^\n]+\n*", "", raw_text).strip()
        return cleaned or raw_text

    return raw_text


# ---------------------------------------------------------------------------
# 3. Assemble
# ---------------------------------------------------------------------------


def assemble_essay(headline: str, sections: List[str]) -> str:
    """Join headline and drafted sections, normalising citations and deduplicating paragraphs."""
    h1 = headline.strip()
    if not h1.startswith("# ") and not h1.startswith("#"):
        h1 = f"# {h1}"

    cleaned_parts = [h1]
    for s in sections:
        clean_s = s.strip()
        if clean_s:
            clean_s = normalize_citations(clean_s)
            cleaned_parts.append(clean_s)

    joined = "\n\n".join(cleaned_parts)
    # Deduplicate duplicate/near-duplicate paragraphs across the entire essay
    deduped = deduplicate_paragraphs(joined)
    return deduped


# ---------------------------------------------------------------------------
# 4. Repair & Expansion passes
# ---------------------------------------------------------------------------


async def expand_section(
    section_content: str,
    section_plan: SectionPlan,
    topic: str,
    sources: List[Any],
    provider: LLMProvider,
    additional_words: int = 120,
) -> str:
    """Expand a single short section with a targeted expansion prompt using unused sources."""
    used_set = set(section_plan.source_indices)
    unused_indices = [i for i in _all_source_indices(sources) if i not in used_set]
    if not unused_indices:
        unused_indices = section_plan.source_indices

    sources_block = _build_sources_block(sources, unused_indices)
    allowed_tags = ", ".join(f"[S{i}]" for i in unused_indices) or "[S1]"

    prompt = _EXPANSION_PROMPT.format(
        additional_words=additional_words,
        topic=topic,
        section_content=section_content,
        sources_block=sources_block,
        allowed_tags=allowed_tags,
    )
    resp = await provider.chat(
        [ChatMessage(role="user", content=prompt)],
        temperature=0.3,
        max_tokens=700,
    )
    expanded = resp.content.strip()
    return expanded if expanded else section_content


def trim_essay_sections(
    drafted: List[str], outline: List[SectionPlan], target_max: int = 1350
) -> List[str]:
    """Trim excess paragraphs from longest body sections while preserving headings, lists, and citations."""
    current_total = sum(count_words(s) for s in drafted)
    if current_total <= target_max:
        return drafted

    result = list(drafted)
    body_indices = [
        i for i, p in enumerate(outline)
        if not p.is_hook and not p.is_takeaway
    ]
    body_indices.sort(key=lambda i: count_words(result[i]), reverse=True)

    for idx in body_indices:
        if current_total <= target_max:
            break
        text = result[idx]
        paras = text.split("\n\n")
        if len(paras) > 3:
            for p_idx in range(len(paras) - 1, 0, -1):
                p = paras[p_idx]
                if not p.startswith("##") and not p.startswith("-") and not p.startswith("*") and not p.startswith("1."):
                    removed_wc = count_words(p)
                    paras.pop(p_idx)
                    result[idx] = "\n\n".join(paras)
                    current_total -= removed_wc
                    break
    return result


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
        word_budget=section_plan.word_budget,
        allowed_tags=allowed_tags,
        sources_block=sources_block,
    )
    resp = await provider.chat(
        [ChatMessage(role="user", content=prompt)],
        temperature=0.3,
        max_tokens=650,
    )
    repaired = resp.content.strip()
    return repaired if repaired else section_content


# ---------------------------------------------------------------------------
# 5. Main essay generation pipeline
# ---------------------------------------------------------------------------


async def generate_essay(
    topic: str,
    sources: List[Any],
    provider: LLMProvider,
) -> EssayResult:
    """Full Ship 30 essay pipeline targeting ~1,250 words (1,000-1,500 bounds)."""
    if not sources:
        logger.warning("generate_essay: no sources provided, essay will be ungrounded")

    t_start = time.perf_counter()
    timings: List[Tuple[str, float]] = []

    # 1. Headline
    t_h0 = time.perf_counter()
    headline = await draft_headline(topic, sources, provider)
    timings.append(("Headline", (time.perf_counter() - t_h0) * 1000))

    # 2. Plan outline: holds only slot ids and word budgets
    t_o0 = time.perf_counter()
    outline = plan_outline(topic, sources)
    timings.append(("Outline Planning", (time.perf_counter() - t_o0) * 1000))

    # 3. Draft section-by-section
    drafted: List[str] = []
    for plan in outline:
        t_sec0 = time.perf_counter()
        text = await draft_section(plan, topic, sources, provider)
        drafted.append(text)
        t_sec_ms = (time.perf_counter() - t_sec0) * 1000
        timings.append((f"Section: {plan.title}", t_sec_ms))
        logger.debug("Drafted section %r (%.1fms, %d chars)", plan.title, t_sec_ms, len(text))

    # 4. Enforce section word count budgets (80%-125%)
    essay_md = assemble_essay(headline, drafted)
    current_wc = count_body_words(essay_md)

    from app.skills.validator import load_rules_config as _load_rules
    _meta = _load_rules().get("metadata", {})
    LEN_MIN = _meta.get("min_word_count", 1100)
    LEN_MAX = _meta.get("max_word_count", 1400)
    LEN_TRIM = _meta.get("trim_target", 1350)

    # Trim if above max
    t_trim0 = time.perf_counter()
    if current_wc > LEN_MAX:
        logger.info("Essay word count %d > %d: trimming to <=%d", current_wc, LEN_MAX, LEN_TRIM)
        drafted = trim_essay_sections(drafted, outline, target_max=LEN_TRIM)
        essay_md = assemble_essay(headline, drafted)
        current_wc = count_body_words(essay_md)
    timings.append(("Trimming / Budget", (time.perf_counter() - t_trim0) * 1000))

    # Expand if below min
    t_exp0 = time.perf_counter()
    expand_passes = 0
    while current_wc < LEN_MIN and expand_passes < 2:
        shortfall = LEN_MIN - current_wc
        body_order = sorted(
            [i for i, p in enumerate(outline) if not p.is_hook and not p.is_takeaway],
            key=lambda i: count_words(drafted[i]),
        )
        if not body_order:
            break
        added_any = False
        for i in body_order:
            if shortfall <= 0:
                break
            expanded = await expand_section(
                drafted[i], outline[i], topic, sources, provider,
                additional_words=max(80, min(200, shortfall // max(1, len(body_order)) + 40)),
            )
            if expanded and expanded != drafted[i]:
                before = count_words(drafted[i])
                drafted[i] = expanded
                after = count_words(drafted[i])
                shortfall -= max(0, after - before)
                added_any = True
        essay_md = assemble_essay(headline, drafted)
        from app.agent.verify import strip_unverified_quote_sentences as _strip_q
        essay_md, _ = _strip_q(essay_md, sources)
        from app.agent.verify import normalize_citations as _norm_c
        essay_md = _norm_c(essay_md)
        current_wc = count_body_words(essay_md)
        expand_passes += 1
        logger.info("Expansion pass %d: body_words=%d (target_min=%d)",
                    expand_passes, current_wc, LEN_MIN)
        if not added_any:
            break
    timings.append(("Expansion Passes", (time.perf_counter() - t_exp0) * 1000))

    # 5. Generate headings with ONE short LLM call per section now that bodies are final
    t_head0 = time.perf_counter()
    assigned_headings: List[str] = []
    for i, plan in enumerate(outline):
        if plan.is_hook or plan.is_takeaway:
            continue
        h = await generate_section_heading(
            section_text=drafted[i],
            topic=topic,
            existing_headings=assigned_headings,
            provider=provider,
        )
        assigned_headings.append(h)
        body_only = re.sub(r"^##\s+[^\n]+\n*", "", drafted[i]).strip()
        drafted[i] = f"## {h}\n\n{body_only}"
    timings.append(("Heading Generation", (time.perf_counter() - t_head0) * 1000))

    # 6. Assemble essay and repair headings deterministically
    essay_md = assemble_essay(headline, drafted)
    essay_md = repair_assembled_headings(essay_md, topic=topic)

    # Delete sentences with unverified direct quotes before validation
    from app.agent.verify import strip_unverified_quote_sentences
    essay_md, pre_quotes_deleted = strip_unverified_quote_sentences(essay_md, sources)
    if pre_quotes_deleted:
        logger.warning("ship30 pre-validate: deleted %d unverified-quote sentence(s)", pre_quotes_deleted)

    # 7. Validate
    t_val0 = time.perf_counter()
    report = validate_essay(essay_md, sources, topic=topic)
    timings.append(("Validation Pass 1", (time.perf_counter() - t_val0) * 1000))
    logger.info("Validation after drafting/expansion: %s", report.summary())

    if report.passed:
        total_ms = (time.perf_counter() - t_start) * 1000
        timing_table_lines = ["Ship 30 Per-Stage Timing Table:"]
        for stage_name, duration_ms in timings:
            timing_table_lines.append(f"  - {stage_name}: {duration_ms:.1f}ms")
        timing_table_lines.append(f"  - Total Pipeline Duration: {total_ms:.1f}ms")
        logger.info("\n".join(timing_table_lines))
        return EssayResult(
            content=essay_md,
            word_count=report.word_count,
            report=report,
            repaired=False,
            title=headline,
        )

    # 8. ONE repair pass on failing sections (structure & citations)
    t_rep0 = time.perf_counter()
    repaired_any = False
    for plan in outline:
        failures_for_section: List[str] = []

        if plan.is_hook and "R_HOOK" in report.failed_rules:
            failures_for_section.append("Hook is missing or too short. Write at least 30 words before the first heading.")
        if plan.is_takeaway and "R_TAKEAWAY" in report.failed_rules:
            failures_for_section.append("Takeaways section is missing or too short.")
        if not plan.is_hook and not plan.is_takeaway:
            if "R_FORMATTING" in report.failed_rules:
                failures_for_section.append("Add bullet list and bold emphasis (**text**).")
            if "R_CITATION" in report.failed_rules:
                failures_for_section.append("Add at least one valid [S#] citation referencing the provided sources.")

        if failures_for_section:
            idx = outline.index(plan)
            drafted[idx] = await repair_section(
                drafted[idx], plan, topic, sources, provider, failures_for_section
            )
            repaired_any = True
            logger.info("Repaired section %r", plan.title)
    timings.append(("Repair Pass", (time.perf_counter() - t_rep0) * 1000))

    # Reassemble after repairs and repair headings
    essay_md = assemble_essay(headline, drafted)
    essay_md = repair_assembled_headings(essay_md, topic=topic)

    essay_md, quotes_deleted = strip_unverified_quote_sentences(essay_md, sources)
    if quotes_deleted:
        logger.warning("ship30: deleted %d sentence(s) with unverified direct quotes", quotes_deleted)

    t_val1 = time.perf_counter()
    final_report = validate_essay(essay_md, sources, topic=topic)
    timings.append(("Validation Final", (time.perf_counter() - t_val1) * 1000))
    logger.info("Validation after repair: %s", final_report.summary())

    total_ms = (time.perf_counter() - t_start) * 1000
    timing_table_lines = ["Ship 30 Per-Stage Timing Table:"]
    for stage_name, duration_ms in timings:
        timing_table_lines.append(f"  - {stage_name}: {duration_ms:.1f}ms")
    timing_table_lines.append(f"  - Total Pipeline Duration: {total_ms:.1f}ms")
    logger.info("\n".join(timing_table_lines))

    return EssayResult(
        content=essay_md,
        word_count=final_report.word_count,
        report=final_report,
        repaired=repaired_any,
        title=headline,
    )
