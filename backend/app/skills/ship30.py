"""Ship 30 for 30 essay generation skill.

Pipeline per PROMPTS.md P6b and Round 2 specification:
  1. Retrieve / accept grounded sources.
  2. Draft H1 headline derived from topic and strongest supported claim.
  3. Plan outline: hook + N specific body sections + actionable takeaways.
  4. Draft SECTION BY SECTION with separate LLM calls (7B cannot write 1,250 in one pass).
  5. Assemble Markdown with strict citation normalization and paragraph deduplication.
  6. Enforce section word count budgets (80%-125%) with targeted expansion/trimming.
  7. Run validator. If validation fails, run ONE repair pass on failing sections. Never loop again.
  8. Return { content, word_count, report, repaired }.

NEVER loops more than once on repair.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

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
    title: str = ""


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
Write the section titled "## {title}" for a Ship 30-style essay about: {topic}

Requirements:
- {word_budget} words (stay within 80% to 125% of this budget: {min_budget}–{max_budget} words)
- Start IMMEDIATELY with "## {title}" heading (no preamble before the heading)
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
Expand the following essay section titled "## {title}" to add more operator depth, tactical examples, and execution nuance based ONLY on the provided unused source passages.
Target: Add about {additional_words} words to this section.

Topic: {topic}
Section title: {title}
Current section content:
---
{section_content}
---

Unused grounding sources available:
{sources_block}
Allowed citation tags: {allowed_tags}

Requirements:
- Keep the "## {title}" heading exactly as-is
- Add concrete operator frameworks or tactical execution steps based SOLELY on the unused sources above
- Never hallucinate claims not present in the sources
- Keep all existing [S#] tags and citations; add [S#] tags from allowed tags for newly added claims
- Maintain bullet list and bold insights (**text**)

Return ONLY the complete expanded section (heading + expanded body)."""

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
    """Generate an H1 headline following the Ship 30 headline principle.

    Tells the reader who it is for, what it is about, and why to read it,
    derived from the topic and the strongest supported claim.
    """
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
    """Build a section-by-section plan with word budgets targeting ~1,250 words.

    Structure:
      - Hook paragraph (~120 words, no heading)
      - 5 content-specific body sections (~240 words each = 1,200 words)
      - Actionable Takeaways (~120 words)
    """
    all_idx = _all_source_indices(sources)
    n_body = 5

    plans: List[SectionPlan] = []

    # Hook (no heading section) ~120 words
    hook_srcs = all_idx[:min(2, len(all_idx))]
    plans.append(SectionPlan(
        title="Hook",
        word_budget=120,
        source_indices=hook_srcs if hook_srcs else ([1] if all_idx else []),
        is_hook=True,
    ))

    # 5 Body section themes derived specifically from sources/content (~240 words each)
    themes = _derive_specific_themes(topic, sources, n_body)
    for i, theme in enumerate(themes):
        if all_idx:
            src1 = all_idx[i % len(all_idx)]
            src2 = all_idx[(i + 1) % len(all_idx)]
            srcs = [src1] if src1 == src2 else [src1, src2]
        else:
            srcs = []
        plans.append(SectionPlan(
            title=theme,
            word_budget=240,
            source_indices=srcs,
        ))

    # Actionable Takeaways ~120 words
    takeaway_srcs = all_idx[-min(3, len(all_idx)):] if all_idx else []
    plans.append(SectionPlan(
        title="Actionable Takeaways",
        word_budget=120,
        source_indices=takeaway_srcs,
        is_takeaway=True,
    ))

    logger.info("plan_outline: topic=%r → %d sections (total planned %d words)",
                topic, len(plans), sum(p.word_budget for p in plans))
    return plans


_ANGLE_PATTERNS: List[str] = [
    "Framing the {kw} problem",
    "What the data on {kw} shows",
    "Common pitfalls around {kw}",
    "Mechanics that make {kw} compound",
    "Where teams go wrong with {kw}",
    "Signals and metrics for {kw}",
    "A step-by-step approach to {kw}",
    "Making {kw} stick after launch",
]


def _topic_keyword(topic: str) -> str:
    """Pick the most content-bearing noun phrase from the topic string.

    Deterministic (no LLM): strips stopwords and ship-30 wrappers, keeps the
    first 1–2 content words. Used only to seed section headings.
    """
    stop = {
        "a", "an", "the", "for", "of", "and", "or", "to", "in", "on", "about",
        "with", "ideas", "insights", "featuring", "early", "stage", "startups",
        "essay", "ship", "30", "post", "article",
    }
    words = re.findall(r"[A-Za-z][A-Za-z-]+", topic.lower())
    core = [w for w in words if w not in stop and len(w) > 2]
    if not core:
        core = words or ["the subject"]
    return " ".join(core[:2])


_HEADING_STOP = {
    "a", "an", "the", "for", "of", "and", "or", "to", "in", "on", "about",
    "with", "by", "from", "into", "onto", "over", "that", "this", "these",
    "those", "it", "its", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "doing", "have", "has", "had", "having", "will",
    "would", "can", "could", "should", "shall", "may", "might", "must",
    "how", "what", "when", "where", "why", "who", "whom", "which",
    "think", "say", "says", "said", "need", "needs", "needed", "want",
    "wants", "wanted", "there", "their", "they", "them", "we", "us", "you",
    "your", "our", "my", "me", "mine", "really", "just", "very", "much",
    "many", "any", "some", "all", "every", "each", "every", "no", "not",
    "but", "also", "than", "then", "so", "if", "else", "while", "because",
    "like", "as", "at", "up", "out", "down", "off", "over", "under", "again",
    "startup", "startups", "company", "team", "teams", "user", "users",
    "ideas", "insights", "featuring", "approach", "approaches", "early",
    "stage", "ship", "30", "essay", "post", "article", "between",
    "instance", "example", "specific", "specifically", "particular",
    "generally", "typically", "actually", "often", "truly", "usually",
    "according", "according to", "mentioned", "mention", "mentions",
    "isn", "aren", "don", "doesn", "didn", "won", "wasn", "weren",
    "something", "someone", "anything", "anyone", "nothing", "none",
    "around", "across", "whole", "entire", "within", "without", "upon",
    "makes", "making", "made", "take", "takes", "took", "give", "gives",
    "given", "find", "finds", "found", "put", "puts",
}


def derive_heading_from_section(section_text: str, topic: str) -> str:
    """Derive a 3–8 word content-specific heading from a drafted section body.

    Deterministic (no LLM call): looks for the first sentence that contains an
    `[S#]` citation (= the first supported claim); otherwise the first non-empty
    sentence after the placeholder heading. Strips stop-words, caps 3–8 words,
    removes colons, and never emits the full multi-word topic string verbatim.

    The brief's "one short LLM call" variant can wrap this later; the fallback
    is the always-safe path and is what the pipeline uses by default.
    """
    text = section_text or ""
    # Strip the opening '## OLD' placeholder heading if present
    lines = [l for l in text.splitlines() if not l.lstrip().startswith("#")]
    body = "\n".join(lines).strip() or text.strip()
    # Find first [S#]-bearing sentence, else first sentence.
    sentences = re.split(r"(?<=[.!?])\s+", body)
    picked: str = ""
    for s in sentences:
        if re.search(r"\[S\d+\]", s):
            picked = s
            break
    if not picked and sentences:
        picked = sentences[0]
    if not picked:
        picked = topic or "key insight"

    # Pull content words (preserve order, dedup, drop stop-words).
    tokens = re.findall(r"[A-Za-z][A-Za-z-]+", picked)
    content: List[str] = []
    seen: set = set()
    for t in tokens:
        lower = t.lower()
        if lower in _HEADING_STOP:
            continue
        if lower in seen:
            continue
        seen.add(lower)
        content.append(t)
        if len(content) >= 6:
            break

    if len(content) < 3:
        # Pad with topic-adjacent nouns the fallback way: pull from topic itself.
        topic_tokens = [t for t in re.findall(r"[A-Za-z][A-Za-z-]+", topic or "")
                        if t.lower() not in _HEADING_STOP]
        for t in topic_tokens:
            if t.lower() in seen:
                continue
            seen.add(t.lower())
            content.append(t)
            if len(content) >= 5:
                break
    if len(content) < 3:
        content = (content + ["Key", "insight", "surfaces"])[:3]

    # Final shape: Title Case words, no colon, no full-topic-string match.
    heading = " ".join(w[0].upper() + w[1:] for w in content[:8])
    topic_norm = (topic or "").strip().lower()
    if topic_norm and len(topic_norm.split()) >= 2 and topic_norm in heading.lower():
        # Only drop topic words if the heading has slack above the 3-word floor.
        trial = heading
        for t in topic_norm.split():
            trial = re.sub(rf"\b{re.escape(t)}\b", "", trial, flags=re.I).strip()
        trial = re.sub(r"\s+", " ", trial).strip()
        if len(trial.split()) >= 3:
            heading = trial
    heading = heading.replace(":", "").strip()
    if not heading:
        heading = "Key insight surfaces"
    return heading


def _derive_specific_themes(topic: str, sources: List[Any], n: int = 5) -> List[str]:
    """Derive distinct, content-specific body headings per topic (D1 fix).

    Deterministic: no LLM call at the planning step; the per-section drafts can
    still refine content. The headings vary by topic because they interpolate a
    keyword drawn from the topic itself. Guarantees:
      - no heading is in the old hard-coded template list;
      - no two body headings are identical;
      - no heading contains the full (multi-word) topic string;
      - each heading is 3–10 words.
    """
    kw = _topic_keyword(topic) or "the subject"
    themes: List[str] = []
    topic_lower = topic.strip().lower()
    for pattern in _ANGLE_PATTERNS:
        if len(themes) >= n:
            break
        candidate = pattern.format(kw=kw).strip()
        # Guard: do not emit the full topic string verbatim as a heading.
        if len(topic_lower.split()) >= 2 and topic_lower in candidate.lower():
            continue
        if candidate in themes:
            continue
        themes.append(candidate)
    # Safety: if we somehow could not fill n unique themes, pad with
    # position-numbered variants rather than reusing one.
    i = 2
    while len(themes) < n:
        themes.append(f"Angle {i} on {kw}")
        i += 1
    return themes[:n]


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
            title=plan.title,
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
        # Ensure section starts cleanly with '## {title}'
        # If model outputted preamble or hook text before '##', strip it
        h2_idx = raw_text.find("##")
        if h2_idx != -1:
            raw_text = raw_text[h2_idx:].strip()
        elif not raw_text.startswith("##"):
            raw_text = f"## {plan.title}\n\n{raw_text}"

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
    # Find unused sources for this section
    used_set = set(section_plan.source_indices)
    unused_indices = [i for i in _all_source_indices(sources) if i not in used_set]
    if not unused_indices:
        unused_indices = section_plan.source_indices

    sources_block = _build_sources_block(sources, unused_indices)
    allowed_tags = ", ".join(f"[S{i}]" for i in unused_indices) or "[S1]"

    prompt = _EXPANSION_PROMPT.format(
        title=section_plan.title,
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
        allowed_tags=allowed_tags,
        sources_block=sources_block,
        word_budget=section_plan.word_budget,
    )
    resp = await provider.chat(
        [ChatMessage(role="user", content=prompt)],
        temperature=0.2,
        max_tokens=700,
    )
    repaired = resp.content.strip()
    return repaired if repaired else section_content


# ---------------------------------------------------------------------------
# 5. Main entry point
# ---------------------------------------------------------------------------


async def generate_essay(
    topic: str,
    sources: List[Any],
    provider: LLMProvider,
) -> EssayResult:
    """Full Ship 30 essay pipeline targeting ~1,250 words (1,000-1,500 bounds).

    Args:
        topic:    Essay topic (from user message).
        sources:  List of retrieved transcript chunks.
        provider: LLM provider to call for text generation.

    Returns:
        EssayResult with content, word_count, and ValidationReport.
    """
    if not sources:
        logger.warning("generate_essay: no sources provided, essay will be ungrounded")

    t_start = time.perf_counter()
    timings: List[Tuple[str, float]] = []

    # 1. Headline
    t_h0 = time.perf_counter()
    headline = await draft_headline(topic, sources, provider)
    timings.append(("Headline", (time.perf_counter() - t_h0) * 1000))

    # 2. Plan outline
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

    # 4. Replace each body section's placeholder heading with one derived
    # deterministically from the section's first supported claim (STEP 4).
    for i, plan in enumerate(outline):
        if plan.is_hook or plan.is_takeaway:
            continue
        content_heading = derive_heading_from_section(drafted[i], topic=topic)
        if content_heading:
            # Replace the first '## <anything>' line with the new heading.
            drafted[i] = re.sub(
                r"^##\s+[^\n]+",
                f"## {content_heading}",
                drafted[i],
                count=1,
                flags=re.M,
            )
            if not drafted[i].lstrip().startswith("#"):
                drafted[i] = f"## {content_heading}\n\n" + drafted[i].lstrip()

    # Ensure body-section headings are unique after derivation.
    seen_headings: set = set()
    for i, plan in enumerate(outline):
        if plan.is_hook or plan.is_takeaway:
            continue
        m = re.match(r"\s*##\s+(.+)", drafted[i])
        if not m:
            continue
        h = m.group(1).strip()
        if h.lower() in seen_headings:
            # Append a short disambiguator pulled from the first non-stop token
            # after the current heading content.
            extra = f" Angle {i}"
            new_h = (h + extra).strip()
            drafted[i] = drafted[i].replace(f"## {h}", f"## {new_h}", 1)
            h = new_h
        seen_headings.add(h.lower())

    # Assemble
    essay_md = assemble_essay(headline, drafted)

    # 5. Enforce section word count budgets (80%-125%)
    body_budget = 240
    min_budget = int(body_budget * 0.80)  # 192 words
    max_budget = int(body_budget * 1.25)  # 300 words

    body_indices = [
        i for i, p in enumerate(outline)
        if not p.is_hook and not p.is_takeaway
    ]

    # Assemble after drafting
    essay_md = assemble_essay(headline, drafted)
    current_wc = count_body_words(essay_md)

    # R3: canonical length range comes from the rules metadata.
    from app.skills.validator import load_rules_config as _load_rules
    _meta = _load_rules().get("metadata", {})
    LEN_MIN = _meta.get("min_word_count", 1100)
    LEN_MAX = _meta.get("max_word_count", 1400)
    LEN_TRIM = _meta.get("trim_target", 1350)

    # If above max, trim excess from longest body sections down to <=trim_target.
    t_trim0 = time.perf_counter()
    if current_wc > LEN_MAX:
        logger.info("Essay word count %d > %d: trimming to <=%d", current_wc, LEN_MAX, LEN_TRIM)
        drafted = trim_essay_sections(drafted, outline, target_max=LEN_TRIM)
        essay_md = assemble_essay(headline, drafted)
        current_wc = count_body_words(essay_md)
    timings.append(("Trimming / Budget", (time.perf_counter() - t_trim0) * 1000))

    # R3 expansion: if below min, run up to 2 expansion passes that may only
    # add sentences supported by unused source passages (expand_section
    # already restricts allowed_tags to unused sources). After each pass we
    # re-run the quote-deletion / citation-normalization / support checks.
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

    # STEP 2: delete sentences with unverified direct quotes BEFORE the first
    # validation pass so fabricated quotes never reach the user.
    from app.agent.verify import strip_unverified_quote_sentences
    essay_md, pre_quotes_deleted = strip_unverified_quote_sentences(essay_md, sources)
    if pre_quotes_deleted:
        logger.warning("ship30 pre-validate: deleted %d unverified-quote sentence(s)", pre_quotes_deleted)

    # 6. Validate
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

    # 7. ONE repair pass on failing sections (structure & citations)
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

    # Reassemble after repairs
    essay_md = assemble_essay(headline, drafted)

    # STEP 2: enforce the "no unverified direct quote in a stored essay" policy.
    # Any sentence containing a ≥6-word quoted span that isn't an exact
    # (normalized) substring of a cited chunk is DELETED before storage.
    from app.agent.verify import strip_unverified_quote_sentences
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
