"""Ship 30 for 30 essay validator.

Enforces rules defined in ship30_rules.yaml:
- R_LENGTH: 1,000 to 1,500 words (target ~1,250 words)
- R_HOOK: Opening hook before the first H2 heading
- R_STRUCTURE: 3 to 5 H2 sections (excluding final takeaway)
- R_FORMATTING: Bulleted/numbered lists and selective bolding (**text**)
- R_TAKEAWAY: Dedicated takeaway/conclusion section (e.g. ## Key Takeaways)
- R_CITATION: Valid [S#] citations in every body section, zero out-of-bounds tags
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set
import yaml

from app.agent.verify import extract_citation_tags

# Regex patterns
RE_H2_HEADING = re.compile(r"^##\s+(.+)$", re.MULTILINE)
RE_TAKEAWAY_HEADING = re.compile(
    r"^##\s+(?:Actionable\s+Takeaways?|Key\s+Takeaways?|Takeaways?|Conclusion|Closing\s+Thoughts?)\b",
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
    word_count: int
    section_count: int
    has_hook: bool
    has_takeaway: bool
    has_formatting: bool
    citations_valid: bool
    rule_results: List[RuleValidation] = field(default_factory=list)
    failed_rules: List[str] = field(default_factory=list)

    def summary(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        return f"Ship 30 Validation {status}: {self.word_count} words, {len(self.failed_rules)} rule violations."


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
    """Accurately count words in a markdown document, excluding markdown headings/markers."""
    # Strip markdown syntax symbols but keep words
    cleaned = re.sub(r"[#*_`~>\[\]()!-]", " ", text)
    words = [w for w in cleaned.split() if any(c.isalnum() for c in w)]
    return len(words)


def extract_sections(text: str) -> List[Dict[str, Any]]:
    """Extract sections by H2 headings from the essay.

    Returns:
        List of dicts: {"title": str, "content": str, "is_takeaway": bool, "word_count": int}
    """
    matches = list(RE_H2_HEADING.finditer(text))
    if not matches:
        return []

    sections = []
    # Hook / Intro is the text before the first H2
    hook_text = text[: matches[0].start()].strip()
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

        sections.append({
            "title": title,
            "content": section_text,
            "is_hook": False,
            "is_takeaway": is_takeaway,
            "word_count": count_words(section_text),
        })

    return sections


def validate_essay(
    markdown_text: str,
    available_sources: Sequence[Any],
    rules_config: Optional[Dict[str, Any]] = None,
) -> ValidationReport:
    """Validate a drafted essay against Ship 30 writing principles.

    Args:
        markdown_text: Full assembled markdown text.
        available_sources: List of available source chunks [S1..Sk].
        rules_config: Optional loaded YAML config.

    Returns:
        ValidationReport with rule-by-rule pass/fail determinations.
    """
    config = rules_config or load_rules_config()
    meta = config.get("metadata", {})
    min_words = meta.get("min_word_count", 1000)
    max_words = meta.get("max_word_count", 1500)

    total_words = count_words(markdown_text)
    sections = extract_sections(markdown_text)
    num_sources = len(available_sources)
    valid_source_indices: Set[int] = set(range(1, num_sources + 1))

    rule_results: List[RuleValidation] = []
    failed_rules: List[str] = []

    # 1. R_LENGTH: Word count
    length_passed = min_words <= total_words <= max_words
    rule_results.append(
        RuleValidation(
            rule_id="R_LENGTH",
            rule_name="Target Word Count",
            passed=length_passed,
            details=f"Essay has {total_words} words.",
            target=f"{min_words}–{max_words} words",
            actual=f"{total_words} words",
        )
    )
    if not length_passed:
        failed_rules.append("R_LENGTH")

    # 2. R_HOOK: Opening hook before first H2
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

    # 3. R_STRUCTURE: 3 to 5 body sections (excluding hook and takeaway)
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

    # 4. R_FORMATTING: Bullets & Bold
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

    # 5. R_TAKEAWAY: Takeaway section
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

    # 6. R_CITATION: Citations in body sections
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

    overall_passed = len(failed_rules) == 0

    return ValidationReport(
        passed=overall_passed,
        word_count=total_words,
        section_count=len(body_sections),
        has_hook=has_hook,
        has_takeaway=has_takeaway,
        has_formatting=formatting_passed,
        citations_valid=citations_passed,
        rule_results=rule_results,
        failed_rules=failed_rules,
    )
