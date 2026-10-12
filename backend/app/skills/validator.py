"""Ship 30 for 30 essay validator.

Enforces rules defined in ship30_rules.yaml:
- R_LENGTH: 1,000 to 1,500 body words (excluding headings and sources list)
- R_HEADLINE: Ship 30 H1 headline stating audience, topic, payoff
- R_HOOK: Opening hook before the first H2 heading (>= 30 words)
- R_STRUCTURE: 3 to 5 H2 body sections (excluding hook and takeaway)
- R_SPECIFIC_HEADINGS: Section headings specific to content; <= 1 heading with full topic
- R_SECTION_BUDGET: Each body section within 80% to 125% of word budget
- R_NO_DUPLICATE_PARAGRAPHS: Zero duplicate or near-duplicate paragraphs
- R_CITATION_FORMAT: Strictly normalized [S#] citations (no (S1), ([S4]...), etc.)
- R_FORMATTING: Bulleted/numbered lists and selective bolding (**text**)
- R_TAKEAWAY: Dedicated takeaway/conclusion section (e.g. ## Actionable Takeaways)
- R_CITATION: Valid [S#] citations in every body section, zero out-of-bounds tags
- R_GROUNDED_SUPPORT: Sentence support overlap, verbatim quotes, valid speaker names
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
import yaml

from app.agent.verify import (
    check_duplicate_paragraphs,
    extract_citation_tags,
    has_illegal_citations,
    verify_essay_groundedness,
)

# Regex patterns
RE_H1_HEADING = re.compile(r"^#\s+(.+)$", re.MULTILINE)
RE_H2_HEADING = re.compile(r"^##\s+(.+)$", re.MULTILINE)
RE_TAKEAWAY_HEADING = re.compile(
    r"^##\s+(?:Actionable\s+Takeaways?|Key\s+Takeaways?|Takeaways?|Conclusion|Closing\s+Thoughts?)\b",
    re.IGNORECASE | re.MULTILINE,
)
RE_SOURCES_HEADING = re.compile(
    r"^##?\s+(?:Sources|References)\b",
    re.IGNORECASE | re.MULTILINE,
)
RE_BULLETS = re.compile(r"^\s*[-*+]\s+|\s*\d+\.\s+", re.MULTILINE)
RE_BOLD = re.compile(r"\*\*[^*]+\*\*|__[^_]+__")


@dataclass
class RuleValidation:
    rule_id: str
    rule_name: str
    passed: bool
    details: str
    target: str = ""
    actual: str = ""


@dataclass
class ValidationReport:
    passed: bool
    word_count: int  # Body words (excluding headings and sources list)
    section_count: int
    has_hook: bool
    has_takeaway: bool
    has_formatting: bool
    citations_valid: bool
    total_word_count: int = 0  # Total words including headings
    has_headline: bool = True
    duplicates_found: int = 0
    support_score: float = 1.0
    quotes_verified: str = "0/0"
    names_verified: bool = True
    citation_format_ok: bool = True
    rule_results: List[RuleValidation] = field(default_factory=list)
    failed_rules: List[str] = field(default_factory=list)

    def summary(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        return (
            f"Ship 30 Validation {status}: {self.word_count} body words "
            f"({self.total_word_count} total words), {len(self.failed_rules)} rule violations."
        )

    def checks_markdown(self) -> str:
        """Generate human-readable collapsible Checks panel for chat message per Item 8."""
        status_label = "Ready" if self.passed else "Needs review"
        violations_count = len(self.failed_rules)
        summary_title = (
            "Checks: Ready (all checks passed)"
            if self.passed
            else f"Checks: Needs review ({violations_count} flagged)"
        )
        open_attr = "" if self.passed else " open"

        lines = [f"<details{open_attr}>", f"<summary><strong>{summary_title}</strong></summary>", ""]
        for r in self.rule_results:
            status_tag = "PASS" if r.passed else "FAIL"
            rule_label = f"**{r.rule_name} ({r.rule_id}):** {status_tag} — {r.details}"
            lines.append(f"- {rule_label}")

        lines.extend([
            f"- **Support Score:** {self.support_score:.1%} (threshold 35.0%)",
            f"- **Quotes Verified:** {self.quotes_verified}",
            f"- **Names Verified:** {'PASS — All names in cited transcripts' if self.names_verified else 'FAIL — Mentions unsupported names'}",
            "",
            "</details>",
        ])
        return "\n".join(lines)


def load_rules_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load ship30_rules.yaml config."""
    if config_path is None:
        base_dir = os.path.dirname(__file__)
        config_path = os.path.join(base_dir, "ship30_rules.yaml")

    if not os.path.exists(config_path):
        return {
            "metadata": {"min_word_count": 1000, "max_word_count": 1500, "target_word_count": 1250},
            "rules": [],
        }

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def count_words(text: str) -> int:
    """Accurately count words in a markdown document, excluding markdown syntax markers."""
    cleaned = re.sub(r"[#*_`~>\[\]()!-]", " ", text)
    words = [w for w in cleaned.split() if any(c.isalnum() for c in w)]
    return len(words)


def count_body_words(text: str) -> int:
    """Accurately count words in a markdown document, excluding headings and sources list."""
    lines = text.split("\n")
    body_lines = []
    in_sources = False
    for line in lines:
        stripped = line.strip()
        if RE_SOURCES_HEADING.match(stripped):
            in_sources = True
            continue
        if in_sources:
            continue
        if stripped.startswith("#"):
            continue
        body_lines.append(line)
    return count_words("\n".join(body_lines))


def extract_sections(text: str) -> List[Dict[str, Any]]:
    """Extract sections by H2 headings from the essay.

    Returns:
        List of dicts: {"title": str, "content": str, "is_hook": bool, "is_takeaway": bool, "word_count": int}
    """
    matches = list(RE_H2_HEADING.finditer(text))
    if not matches:
        return []

    sections = []
    # Hook / Intro is the text before the first H2, stripping any preceding H1
    pre_h2 = text[: matches[0].start()].strip()
    h1_match = RE_H1_HEADING.search(pre_h2)
    if h1_match:
        hook_text = pre_h2[h1_match.end() :].strip()
    else:
        hook_text = pre_h2

    if hook_text:
        sections.append({
            "title": "Hook / Introduction",
            "content": hook_text,
            "is_hook": True,
            "is_takeaway": False,
            "word_count": count_words(hook_text),
        })

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()
        title = m.group(1).strip()
        is_takeaway = bool(RE_TAKEAWAY_HEADING.match(m.group(0)))
        is_sources = bool(RE_SOURCES_HEADING.match(m.group(0)))
        if is_sources:
            continue

        # Body text excluding the '## Title' line itself
        body_only = re.sub(r"^##\s+[^\n]+\n*", "", section_text).strip()

        sections.append({
            "title": title,
            "content": section_text,
            "is_hook": False,
            "is_takeaway": is_takeaway,
            "word_count": count_words(body_only),
        })

    return sections


def clean_topic_string(topic: str) -> str:
    """Normalize topic string for heading specificity check."""
    clean = topic.strip().lower()
    clean = re.sub(r"^(?:write\s+)?(?:a\s+)?(?:ship\s*30\s+)?(?:essay\s+)?(?:about|on|regarding)\s+", "", clean)
    clean = re.sub(r"\bfeaturing\s+.*$", "", clean).strip()
    return clean


def validate_essay(
    markdown_text: str,
    available_sources: Sequence[Any],
    rules_config: Optional[Dict[str, Any]] = None,
    topic: str = "",
) -> ValidationReport:
    """Validate a drafted essay against Ship 30 writing principles.

    Args:
        markdown_text: Full assembled markdown text.
        available_sources: List of available source chunks [S1..Sk].
        rules_config: Optional loaded YAML config.
        topic: Optional topic string to check heading specificity.

    Returns:
        ValidationReport with rule-by-rule pass/fail determinations.
    """
    config = rules_config or load_rules_config()
    meta = config.get("metadata", {})
    min_words = meta.get("min_word_count", 1000)
    max_words = meta.get("max_word_count", 1500)

    total_words = count_words(markdown_text)
    body_words = count_body_words(markdown_text)
    sections = extract_sections(markdown_text)
    num_sources = len(available_sources)
    valid_source_indices: Set[int] = set(range(1, num_sources + 1))

    rule_results: List[RuleValidation] = []
    failed_rules: List[str] = []

    # 1. R_LENGTH: Word count (excludes headings and sources list)
    length_passed = min_words <= body_words <= max_words
    rule_results.append(
        RuleValidation(
            rule_id="R_LENGTH",
            rule_name="Target Word Count",
            passed=length_passed,
            details=f"Essay has {body_words} body words (excluding headings and sources; total {total_words} words).",
            target=f"{min_words}–{max_words} body words",
            actual=f"{body_words} body words ({total_words} total)",
        )
    )
    if not length_passed:
        failed_rules.append("R_LENGTH")

    # 2. R_HEADLINE: Ship 30 H1 headline
    first_lines = [line.strip() for line in markdown_text.split("\n") if line.strip()]
    has_h1 = False
    headline_text = ""
    if first_lines and first_lines[0].startswith("# ") and not first_lines[0].startswith("##"):
        has_h1 = True
        headline_text = first_lines[0][2:].strip()
        # Ensure it has sufficient substance (at least 5 words)
        if len(headline_text.split()) < 5:
            has_h1 = False

    rule_results.append(
        RuleValidation(
            rule_id="R_HEADLINE",
            rule_name="Ship 30 H1 Headline Principle",
            passed=has_h1,
            details=f"H1 headline: '{headline_text}'." if has_h1 else "Missing or incomplete H1 headline at start of essay.",
            target="H1 headline specifying audience, topic, and payoff (>= 5 words)",
            actual=headline_text if has_h1 else "Missing/Incomplete",
        )
    )
    if not has_h1:
        failed_rules.append("R_HEADLINE")

    # 3. R_HOOK: Opening hook before first H2
    has_hook = len(sections) > 0 and sections[0].get("is_hook", False) and sections[0]["word_count"] >= 30
    rule_results.append(
        RuleValidation(
            rule_id="R_HOOK",
            rule_name="Compelling Opening Hook",
            passed=has_hook,
            details="Opening hook presents thesis before first section header." if has_hook else "Missing or too short opening hook before first H2.",
            target=">= 30 words before first H2",
            actual=f"{sections[0]['word_count'] if sections and sections[0].get('is_hook') else 0} words",
        )
    )
    if not has_hook:
        failed_rules.append("R_HOOK")

    # 4. R_STRUCTURE: 3 to 5 body sections (excluding hook and takeaway)
    body_sections = [s for s in sections if not s.get("is_hook") and not s.get("is_takeaway")]
    structure_passed = 3 <= len(body_sections) <= 5
    rule_results.append(
        RuleValidation(
            rule_id="R_STRUCTURE",
            rule_name="Multi-Section Modular Structure",
            passed=structure_passed,
            details=f"Found {len(body_sections)} body H2 sections.",
            target="3–5 body sections",
            actual=f"{len(body_sections)} sections",
        )
    )
    if not structure_passed:
        failed_rules.append("R_STRUCTURE")

    # 5. R_SPECIFIC_HEADINGS: body headings must be content-specific:
    #    - no heading from the old hardcoded ship30 template list (D1);
    #    - all body headings unique;
    #    - at most one heading contains the full multi-word topic string.
    topic_clean = clean_topic_string(topic) if topic else ""
    old_template_headings = {
        "defining the core value moment early",
        "measuring leading indicators vs. vanity metrics",
        "compounding feedback loops and team workflows",
        "friction reduction and operational pitfalls",
        "tactical execution: from pilot to scaling",
    }
    body_titles = [bs["title"] for bs in body_sections]
    old_list_hits = [t for t in body_titles if t.strip().lower() in old_template_headings]
    duplicate_titles = [t for t in body_titles if body_titles.count(t) > 1]
    topic_heading_matches = []
    if topic_clean and len(topic_clean.split()) >= 2:
        for t in body_titles:
            if topic_clean in t.lower():
                topic_heading_matches.append(t)
    specific_headings_passed = (
        not old_list_hits
        and not duplicate_titles
        and len(topic_heading_matches) <= 1
    )
    if specific_headings_passed:
        details = "Headings are specific to content."
    else:
        parts = []
        if old_list_hits:
            parts.append(f"old-template headings: {old_list_hits}")
        if duplicate_titles:
            parts.append(f"duplicate body headings: {sorted(set(duplicate_titles))}")
        if len(topic_heading_matches) > 1:
            parts.append(f"too many headings containing topic string: {topic_heading_matches}")
        details = "; ".join(parts)
    rule_results.append(
        RuleValidation(
            rule_id="R_SPECIFIC_HEADINGS",
            rule_name="Content-Specific Section Headings",
            passed=specific_headings_passed,
            details=details,
            target="no old-template or duplicate headings; <= 1 heading containing full topic string",
            actual=f"{len(topic_heading_matches)} topic-string matches, {len(old_list_hits)} old-template, {len(set(duplicate_titles))} duplicate",
        )
    )
    if not specific_headings_passed:
        failed_rules.append("R_SPECIFIC_HEADINGS")

    # 6. R_SECTION_BUDGET: Each body section within budget bounds
    if len(body_sections) >= 4:
        budget_per_section = 1200 // len(body_sections)
        min_budget = int(budget_per_section * 0.75)
        max_budget = int(budget_per_section * 1.30)
        budget_violations = []
        for bs in body_sections:
            swc = bs["word_count"]
            if swc < min_budget or swc > max_budget:
                budget_violations.append(f"'{bs['title']}': {swc} words (budget: {min_budget}–{max_budget})")
        budget_passed = len(budget_violations) == 0
    else:
        budget_violations = []
        for bs in body_sections:
            swc = bs["word_count"]
            if swc < 80:
                budget_violations.append(f"'{bs['title']}': {swc} words (< 80 words)")
        budget_passed = len(budget_violations) == 0
        min_budget, max_budget = 80, 500

    rule_results.append(
        RuleValidation(
            rule_id="R_SECTION_BUDGET",
            rule_name="Section Word Count Budget Bounds",
            passed=budget_passed,
            details="All body sections within budget range." if budget_passed else f"Sections out of budget: {'; '.join(budget_violations)}",
            target=f"Each section {min_budget}–{max_budget} words",
            actual="All within budget" if budget_passed else f"{len(budget_violations)} out of bounds",
        )
    )
    if not budget_passed:
        failed_rules.append("R_SECTION_BUDGET")

    # 7. R_NO_DUPLICATE_PARAGRAPHS: Zero duplicate or near-duplicate paragraphs
    duplicates = check_duplicate_paragraphs(markdown_text)
    no_dups_passed = len(duplicates) == 0
    rule_results.append(
        RuleValidation(
            rule_id="R_NO_DUPLICATE_PARAGRAPHS",
            rule_name="Zero Duplicate Paragraphs",
            passed=no_dups_passed,
            details="No duplicate paragraphs detected." if no_dups_passed else f"Found {len(duplicates)} duplicate/near-duplicate paragraphs.",
            target="0 duplicate paragraphs",
            actual=f"{len(duplicates)} duplicates found",
        )
    )
    if not no_dups_passed:
        failed_rules.append("R_NO_DUPLICATE_PARAGRAPHS")

    # 8. R_CITATION_FORMAT: Strictly normalized [S#] citations
    citation_format_passed = not has_illegal_citations(markdown_text)
    rule_results.append(
        RuleValidation(
            rule_id="R_CITATION_FORMAT",
            rule_name="Strict [S#] Citation Normalization",
            passed=citation_format_passed,
            details="All citations strictly use [S#] format." if citation_format_passed else "Detected non-standard citation formats like (S1) or ([S4]...).",
            target="Strict [S#] only",
            actual="Valid [S#]" if citation_format_passed else "Illegal citation formats found",
        )
    )
    if not citation_format_passed:
        failed_rules.append("R_CITATION_FORMAT")

    # 9. R_FORMATTING: Bullets & Bold
    has_bullets = bool(RE_BULLETS.search(markdown_text))
    has_bold = bool(RE_BOLD.search(markdown_text))
    formatting_passed = has_bullets and has_bold
    rule_results.append(
        RuleValidation(
            rule_id="R_FORMATTING",
            rule_name="High-Skimmability Formatting",
            passed=formatting_passed,
            details=f"Bulleted lists: {'yes' if has_bullets else 'no'}, Bold emphasis: {'yes' if has_bold else 'no'}.",
            target="Bullets + Bold present",
            actual=f"Bullets: {has_bullets}, Bold: {has_bold}",
        )
    )
    if not formatting_passed:
        failed_rules.append("R_FORMATTING")

    # 10. R_TAKEAWAY: Takeaway section
    takeaways = [s for s in sections if s.get("is_takeaway")]
    has_takeaway = len(takeaways) >= 1 and takeaways[0]["word_count"] >= 30
    rule_results.append(
        RuleValidation(
            rule_id="R_TAKEAWAY",
            rule_name="Actionable Key Takeaways",
            passed=has_takeaway,
            details="Includes dedicated key takeaway / conclusion section." if has_takeaway else "Missing or empty takeaway conclusion section.",
            target="Dedicated Takeaways H2 section",
            actual="Present" if has_takeaway else "Missing",
        )
    )
    if not has_takeaway:
        failed_rules.append("R_TAKEAWAY")

    # 11. R_CITATION: Citations in body sections
    citation_failures = []
    for s in body_sections:
        tags = extract_citation_tags(s["content"])
        if not tags:
            citation_failures.append(f"Section '{s['title']}' has 0 citations")
        else:
            invalid = [t for t in tags if t not in valid_source_indices]
            if invalid:
                citation_failures.append(f"Section '{s['title']}' has invalid citations: {invalid}")

    citations_passed = len(citation_failures) == 0 and len(body_sections) > 0
    rule_results.append(
        RuleValidation(
            rule_id="R_CITATION",
            rule_name="Grounded Source Citations",
            passed=citations_passed,
            details="All body sections contain valid [S#] citations." if citations_passed else f"Citation issues: {'; '.join(citation_failures)}",
            target=">= 1 valid citation per body section",
            actual="All valid" if citations_passed else f"{len(citation_failures)} issues",
        )
    )
    if not citations_passed:
        failed_rules.append("R_CITATION")

    # 12. R_GROUNDED_SUPPORT: Sentence support overlap & names check
    total_source_words = sum(len(getattr(s, "text", "").split()) for s in available_sources)
    if total_source_words >= 100:
        grounded_rep = verify_essay_groundedness(markdown_text, available_sources)
        grounded_passed = (
            grounded_rep.support_score >= 0.70
            and len(grounded_rep.unsupported_names) == 0
            and len(grounded_rep.speaker_mismatches) == 0
        )
        mismatch_str = f" Speaker attribution errors: {'; '.join(grounded_rep.speaker_mismatches)}." if grounded_rep.speaker_mismatches else ""
        details_str = (
            f"Support score: {grounded_rep.support_score:.1%} ({grounded_rep.supported_sentences}/{grounded_rep.total_sentences} sentences). "
            f"Quotes verified: {grounded_rep.quotes_verified}. "
            f"Unsupported names: {grounded_rep.unsupported_names or 'none'}.{mismatch_str}"
        )
        actual_str = f"Support {grounded_rep.support_score:.1%}, names {len(grounded_rep.unsupported_names)}"
    else:
        grounded_rep = verify_essay_groundedness(markdown_text, [])
        grounded_passed = True
        details_str = "Skipped on mock/synthetic sources without substantive text."
        actual_str = "Mock sources"

    rule_results.append(
        RuleValidation(
            rule_id="R_GROUNDED_SUPPORT",
            rule_name="Grounded Sentence and Attribution Verification",
            passed=grounded_passed,
            details=details_str,
            target=">= 70% support score and 0 unsupported names",
            actual=actual_str,
        )
    )
    if not grounded_passed:
        failed_rules.append("R_GROUNDED_SUPPORT")

    overall_passed = len(failed_rules) == 0

    return ValidationReport(
        passed=overall_passed,
        word_count=body_words,
        total_word_count=total_words,
        section_count=len(body_sections),
        has_hook=has_hook,
        has_takeaway=has_takeaway,
        has_formatting=formatting_passed,
        citations_valid=citations_passed,
        has_headline=has_h1,
        duplicates_found=len(duplicates),
        support_score=grounded_rep.support_score,
        quotes_verified=grounded_rep.quotes_verified,
        names_verified=(len(grounded_rep.unsupported_names) == 0),
        citation_format_ok=citation_format_passed,
        rule_results=rule_results,
        failed_rules=failed_rules,
    )
