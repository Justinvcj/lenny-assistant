"""R3 essay length control.

- One canonical target range (1,100–1,400) is used by validator, rules file and
  chat message. The validator FAILS R_LENGTH outside that range.
- Essays below the review_floor (1,000) surface a "Needs review: shorter than
  target" marker in `R_LENGTH.details` (upstream expansion already attempted).
- The rules metadata exposes `review_floor` and `trim_target`.
"""
from __future__ import annotations

from app.skills.validator import load_rules_config, validate_essay


def _fake_essay(target_body_words: int, headline="How to Nail Early Growth Fast: Audience Topic Payoff Promise") -> str:
    """Build a syntactically valid Ship 30 essay of approx target_body_words."""
    # Hook (~55 words) + 3 body sections + takeaways. Body size scales with
    # body_filler. Each body section includes [S1] citations and simple
    # formatting so unrelated rules pass.
    body_section_target = max(50, (target_body_words - 55 - 60) // 3)
    filler_sent = (
        "In practice this means that the signal becomes consistent across teams "
        "and the leader can observe durable behaviour change on the ground [S1]. "
    )
    sent_wc = len(filler_sent.split())
    repeats_per_section = max(1, body_section_target // sent_wc)

    hook = (
        "Early growth is the compounding of small wins — a chain of tiny activations "
        "that stack into one habitual loop for the first ten users of the product and the next "
        "hundred that follow them. "
    ) * 1  # ~ 40 words

    sections = []
    for i in range(1, 4):
        text = f"## Pillar {i}: Habit Signals\n\n"
        text += "- Observed signal [S1]\n- Repeated behaviour [S1]\n\n"
        text += "**Key:** " + (filler_sent * repeats_per_section).strip() + "\n"
        sections.append(text)

    takeaway = (
        "## Actionable Takeaways\n\n"
        "- Watch durable behaviour, not vanity metrics [S1].\n"
        "- Ship a single loop before the next feature [S1].\n"
        "- Share what you learn with the team [S1]."
    )
    return f"# {headline}\n\n{hook}\n\n" + "\n\n".join(sections) + "\n\n" + takeaway


class _FakeChunk:
    """Minimal RetrievalResult-like for validate_essay's groundedness pass."""
    def __init__(self, n=1):
        self.text = (
            "In practice this means that the signal becomes consistent across teams "
            "and the leader can observe durable behaviour change on the ground."
        )
        self.title = "Episode"
        self.guest = "Hila Qu"
        self.speaker = "Hila Qu"
        self.chunk_id = f"c{n}"


def _fake_sources():
    return [_FakeChunk(1)]


def test_rules_metadata_has_canonical_1100_1400_range_and_floor():
    cfg = load_rules_config()
    md = cfg["metadata"]
    assert md["min_word_count"] == 1100
    assert md["max_word_count"] == 1400
    assert md["review_floor"] == 1000
    assert md["trim_target"] == 1350


def _length_rule(report):
    return next(r for r in report.rule_results if r.rule_id == "R_LENGTH")


def test_validator_passes_r_length_at_1200_body_words():
    report = validate_essay(_fake_essay(1200), _fake_sources(), topic="early growth")
    rule = _length_rule(report)
    assert rule.passed, (
        f"expected R_LENGTH pass at 1200 body words, got: {rule.details}"
    )
    assert "1100" in rule.target and "1400" in rule.target


def test_validator_fails_r_length_between_floor_and_min():
    report = validate_essay(_fake_essay(1100), _fake_sources(), topic="early growth")
    rule = _length_rule(report)
    # Body-word floor is 1000 and min is 1100. Build an essay in [1000,1099].
    body_wc = report.word_count
    assert 1000 <= body_wc < 1100, f"test fixture produced {body_wc} body words"
    assert not rule.passed
    assert "below minimum" in rule.details.lower()


def test_validator_marks_needs_review_below_floor():
    report = validate_essay(_fake_essay(900), _fake_sources(), topic="early growth")
    rule = _length_rule(report)
    body_wc = report.word_count
    assert body_wc < 1000, f"test fixture produced {body_wc} body words (want <1000)"
    assert not rule.passed
    assert "Needs review" in rule.details
    assert "shorter than target" in rule.details


def test_validator_fails_r_length_above_max():
    report = validate_essay(_fake_essay(1600), _fake_sources(), topic="early growth")
    rule = _length_rule(report)
    assert not rule.passed
    assert "longer than max" in rule.details


def test_validator_chat_message_shows_canonical_range():
    """The R_LENGTH target string shown to the user must mention 1100–1400."""
    report = validate_essay(_fake_essay(1200), _fake_sources(), topic="early growth")
    panel = report.checks_markdown()
    assert "1100" in panel or "1,100" in panel
    assert "1400" in panel or "1,400" in panel
