"""Unit tests for citation verification, tag extraction, validation, and refusal detection."""

import uuid
import pytest

from app.agent.prompts import EXACT_REFUSAL_MESSAGE
from app.agent.verify import (
    VerificationResult,
    extract_citation_tags,
    is_refusal_response,
    resolve_citations,
    strip_invalid_tags,
    verify_citations,
)
from app.rag.retrieval import RetrievalResult
from app.schemas import CitationItem


def make_mock_source(
    idx: int,
    title: str = "Elena Verna on PLG",
    guest: str | None = "Elena Verna",
    chunk_id: uuid.UUID | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id or uuid.uuid4(),
        text=f"Passage text for source {idx} regarding activation loops.",
        score=0.91,
        document_slug=f"elena-verna-ep-{idx}",
        title=title,
        guest=guest,
        speaker=guest,
        start_char=100 * idx,
        end_char=100 * idx + 95,
        chunk_index=idx,
    )


# --- Suite 1: Tag Extraction ---

def test_extract_single_tag():
    assert extract_citation_tags("Growth loops matter [S1].") == [1]


def test_extract_multiple_distinct_tags():
    assert extract_citation_tags("Point A [S1] Point B [S2].") == [1, 2]


def test_extract_repeated_tags():
    assert extract_citation_tags("Point [S1] and again [S1].") == [1, 1]


def test_extract_multi_digit_tags():
    assert extract_citation_tags("Point [S12] and [S45].") == [12, 45]


def test_extract_case_insensitivity():
    assert extract_citation_tags("Point [s1] and [S2].") == [1, 2]


def test_extract_whitespace_within_brackets():
    assert extract_citation_tags("Point [ S1 ] and [  s2  ].") == [1, 2]


def test_extract_adjacent_brackets():
    assert extract_citation_tags("Point [S1][S2].") == [1, 2]


def test_extract_composite_bracket():
    assert extract_citation_tags("Point [S1, S2] and [s3, s4].") == [1, 2, 3, 4]


def test_extract_ignores_non_source_brackets():
    assert extract_citation_tags("In [2024], growth [S1] occurred in [Section 3].") == [1]


def test_extract_ignores_malformed_tags():
    assert extract_citation_tags("Malformed: [S] [SX] [S-1] [S1.2].") == []


def test_extract_empty_string():
    assert extract_citation_tags("") == []


# --- Suite 2: Validation & Tag Filtering / Text Cleaning ---

def test_strip_invalid_tags_from_text():
    # Only tag 1 is valid, 99 is invalid
    text = "Real claim [S1]. Fake claim [S99]."
    cleaned = strip_invalid_tags(text, {1})
    assert cleaned == "Real claim [S1]. Fake claim."


def test_strip_only_invalid_leaves_valid():
    text = "Keep this [S1] and remove that [S50]."
    cleaned = strip_invalid_tags(text, {1})
    assert cleaned == "Keep this [S1] and remove that."


def test_strip_normalizes_whitespace_and_punctuation():
    text = "End of claim [S99]."
    cleaned = strip_invalid_tags(text, set())
    assert cleaned == "End of claim."
    assert "  " not in cleaned
    assert " ." not in cleaned


def test_strip_composite_tags_partial_valid():
    text = "Combined claims [S1, S99]."
    cleaned = strip_invalid_tags(text, {1})
    assert cleaned == "Combined claims [S1]."


# --- Suite 3: Citation Resolution ---

def test_resolve_citations_matches_retrieval_result():
    source1 = make_mock_source(1, title="Mastering Onboarding", guest="Casey Winters")
    citations = resolve_citations([1], [source1])
    assert len(citations) == 1
    c = citations[0]
    assert isinstance(c, CitationItem)
    assert c.n == 1
    assert c.chunk_id == source1.chunk_id
    assert c.doc_slug == source1.document_slug
    assert c.title == "Mastering Onboarding"
    assert c.guest == "Casey Winters"
    assert c.passage == source1.text


def test_zero_fabrication_from_model_text():
    source1 = make_mock_source(1, title="Real Title", guest="Real Guest")
    # Even if model text hallucinated a different title/guest, resolved citation uses source1
    citations = resolve_citations([1], [source1])
    assert citations[0].title == "Real Title"
    assert citations[0].guest == "Real Guest"


def test_deduplication_of_repeated_tags():
    source1 = make_mock_source(1)
    citations = resolve_citations([1, 1, 1], [source1])
    assert len(citations) == 1
    assert citations[0].n == 1


def test_preserves_appearance_order():
    source1 = make_mock_source(1)
    source2 = make_mock_source(2)
    citations = resolve_citations([2, 1], [source1, source2])
    assert len(citations) == 2
    assert citations[0].n == 2
    assert citations[1].n == 1


def test_handles_guest_as_none():
    source1 = make_mock_source(1, guest=None)
    citations = resolve_citations([1], [source1])
    assert len(citations) == 1
    assert citations[0].guest is None


# --- Suite 4: Refusal Detection ---

def test_exact_refusal_sentence():
    assert is_refusal_response(EXACT_REFUSAL_MESSAGE) is True


def test_refusal_with_whitespace_and_newlines():
    assert is_refusal_response(f"  \n  {EXACT_REFUSAL_MESSAGE}  \n  ") is True


def test_refusal_case_insensitive():
    assert is_refusal_response(EXACT_REFUSAL_MESSAGE.lower()) is True


def test_refusal_missing_trailing_period():
    assert is_refusal_response("I don't have information about that in the transcripts") is True


def test_refusal_quoted():
    assert is_refusal_response(f'"{EXACT_REFUSAL_MESSAGE}"') is True
    assert is_refusal_response(f"'{EXACT_REFUSAL_MESSAGE}'") is True


def test_substantive_answer_not_refusal():
    assert is_refusal_response("Retention is driven by activation [S1].") is False


def test_substantive_quote_mentioning_refusal_not_refusal():
    ans = "Some say I don't have information about that in the transcripts, but Lenny explained [S1]."
    assert is_refusal_response(ans) is False


# --- Suite 5: Retry Logic ---

def test_valid_grounded_answer_no_retry():
    source = make_mock_source(1)
    result = verify_citations("Retention is driven by activation [S1].", [source])
    assert result.needs_retry is False
    assert len(result.citations) == 1


def test_uncited_answer_triggers_retry():
    source = make_mock_source(1)
    result = verify_citations("Retention is driven by activation.", [source])
    assert result.needs_retry is True
    assert len(result.citations) == 0


def test_only_invalid_tags_triggers_retry():
    source = make_mock_source(1)
    # Citing S99 when only 1 source exists
    result = verify_citations("Retention is driven by activation [S99].", [source])
    assert result.needs_retry is True
    assert len(result.citations) == 0
    assert result.invalid_tags == [99]


def test_mixed_tags_with_at_least_one_valid_no_retry():
    source = make_mock_source(1)
    result = verify_citations("Retention is driven by activation [S1] and pricing is hard [S99].", [source])
    assert result.needs_retry is False
    assert len(result.citations) == 1
    assert result.valid_tags == [1]
    assert result.invalid_tags == [99]


def test_refusal_response_never_retries():
    result = verify_citations(EXACT_REFUSAL_MESSAGE, [])
    assert result.is_refusal is True
    assert result.needs_retry is False
    assert len(result.citations) == 0


def test_empty_string_triggers_retry():
    result = verify_citations("", [])
    assert result.needs_retry is True


# --- Suite 6: Full Verification Pipeline ---

def test_pipeline_happy_path():
    s1 = make_mock_source(1, title="Episode 1")
    s2 = make_mock_source(2, title="Episode 2")
    ans = "According to Episode 1, activation matters [S1]. Furthermore, churn hurts [S2]."
    res = verify_citations(ans, [s1, s2])

    assert res.is_refusal is False
    assert res.needs_retry is False
    assert res.valid_tags == [1, 2]
    assert res.invalid_tags == []
    assert len(res.citations) == 2
    assert res.citations[0].title == "Episode 1"
    assert res.citations[1].title == "Episode 2"
    assert res.cleaned_text == ans


def test_pipeline_hallucinated_tags_stripped_retry_false_if_valid_remains():
    s1 = make_mock_source(1)
    ans = "Activation is key [S1]. Also something else [S55]."
    res = verify_citations(ans, [s1])

    assert res.needs_retry is False
    assert res.valid_tags == [1]
    assert res.invalid_tags == [55]
    assert len(res.citations) == 1
    assert "[S55]" not in res.cleaned_text
    assert "[S1]" in res.cleaned_text


def test_pipeline_all_hallucinated_tags_stripped_retry_true():
    s1 = make_mock_source(1)
    ans = "Activation is key [S55]. Also something else [S99]."
    res = verify_citations(ans, [s1])

    assert res.needs_retry is True
    assert res.valid_tags == []
    assert res.invalid_tags == [55, 99]
    assert len(res.citations) == 0
    assert "[S55]" not in res.cleaned_text
    assert "[S99]" not in res.cleaned_text


def test_pipeline_empty_sources_list():
    ans = "Some claim [S1]."
    res = verify_citations(ans, [])

    assert res.needs_retry is True
    assert res.valid_tags == []
    assert res.invalid_tags == [1]
    assert len(res.citations) == 0


def test_pipeline_markdown_formatting_preserved():
    s1 = make_mock_source(1)
    markdown_ans = (
        "### Key Takeaways\n\n"
        "- First point about activation [S1].\n"
        "- Second point that was phantom [S99].\n\n"
        "Summary paragraph."
    )
    res = verify_citations(markdown_ans, [s1])

    assert res.needs_retry is False
    assert "### Key Takeaways" in res.cleaned_text
    assert "- First point about activation [S1]." in res.cleaned_text
    assert "- Second point that was phantom." in res.cleaned_text
    assert "[S99]" not in res.cleaned_text
