"""Unit tests for citation verification, tag extraction, validation, and refusal detection."""

import uuid

from app.agent.prompts import EXACT_REFUSAL_MESSAGE
from app.agent.verify import (
    check_unsupported_names,
    clean_heading_profanity,
    extract_citation_tags,
    is_refusal_response,
    normalize_citations,
    resolve_citations,
    strip_invalid_tags,
    verify_citations,
    verify_speaker_attribution,
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


# --- Suite 7: Unsupported Name Attribution Detection ---

def test_unsupported_names_supported_guest():
    """Verify supported guest present in sources is not flagged as unsupported."""
    source = make_mock_source(1, title="Elena Verna Masterclass", guest="Elena Verna")
    ans = "Elena Verna discusses growth loops and product-led growth [S1]."
    unsupported = check_unsupported_names(ans, [source])
    assert unsupported == []


def test_unsupported_names_host_ignored():
    """Verify podcast host Lenny Rachitsky is never flagged as an unsupported guest."""
    source = make_mock_source(1, title="Product Leadership", guest="Casey Winters")
    ans = "Lenny Rachitsky asked Casey Winters about scaling product teams [S1]."
    unsupported = check_unsupported_names(ans, [source])
    assert unsupported == []


def test_unsupported_names_unsupported_guest_flagged():
    """Verify guest in roster not present in sources is identified as unsupported."""
    source = make_mock_source(1, title="Sean Ellis on Growth", guest="Sean Ellis")
    ans = "Hila Qu explains that retention depends on customer activation [S1]."
    unsupported = check_unsupported_names(ans, [source])
    assert "Hila Qu" in unsupported


def test_unsupported_names_partial_match():
    """Verify partial surname/distinctive name match for roster guest is detected."""
    source = make_mock_source(1, title="General Product Strategy", guest="Marty Cagan")
    ans = "According to Verna, product-led sales works best with high self-serve volume [S1]."
    unsupported = check_unsupported_names(ans, [source])
    assert "Elena Verna" in unsupported


def test_unsupported_names_supported_in_passage():
    """Verify name appearing in source text (even if not guest field) is accepted."""
    source = make_mock_source(1, title="Interview", guest="Unknown")
    source.text = "Rahul Vohra shared the Superhuman product-market fit engine."
    ans = "Rahul Vohra designed the 40% very disappointed PMF metric [S1]."
    unsupported = check_unsupported_names(ans, [source])
    assert unsupported == []


def test_unsupported_names_custom_roster():
    """Verify check_unsupported_names works with a custom roster set."""
    custom_roster = {"Alice Wonder", "Bob Builder"}
    source = make_mock_source(1, title="Title", guest="Charlie")
    ans = "Alice Wonder suggested building in public."
    unsupported = check_unsupported_names(ans, [source], known_roster=custom_roster)
    assert unsupported == ["Alice Wonder"]


# --- Suite 8: Addendum Round 2 Defect Regression Tests ---

def test_citation_normalization_exact_evidence_strings():
    """Verify bare S3/S4, paren citations, and comma-separated brackets normalize to [S#]."""
    text1 = "Users flow through the doors. S3 and activate in the fourth week. S4"
    norm1 = normalize_citations(text1)
    assert norm1 == "Users flow through the doors. [S3] and activate in the fourth week. [S4]"

    text2 = "Elena Verna discusses growth loops [S3, S4, S5]."
    norm2 = normalize_citations(text2)
    assert norm2 == "Elena Verna discusses growth loops [S3][S4][S5]."

    text3 = "As Sean Ellis notes ([S4], 00:48:00) during the conversation."
    norm3 = normalize_citations(text3)
    assert norm3 == "As Sean Ellis notes [S4] during the conversation."

    text4 = "According to Hila Qu (S1), activation drives retention."
    norm4 = normalize_citations(text4)
    assert norm4 == "According to Hila Qu [S1], activation drives retention."


def test_speaker_attribution_corrects_lenny_to_sean_ellis():
    """Regression: Quote spoken by Sean Ellis attributed to Lenny Rachitsky must be corrected."""
    chunk_text = (
        "Lenny Rachitsky (01:02:45):\nWhat is the key metric?\n\n"
        "Sean Ellis (01:02:58):\n"
        "when do I think they've had a good enough experience with the product to really know it?\n"
    )
    source = make_mock_source(1, title="Sean Ellis on Growth", guest="Sean Ellis")
    source.text = chunk_text

    essay_text = (
        'As Lenny Rachitsky emphasized, "when do I think they\'ve had a good enough experience with the product to really know it?" [S1].'
    )

    corrected, mismatches = verify_speaker_attribution(essay_text, [source])
    assert len(mismatches) == 1
    assert "Sean Ellis" in mismatches[0]
    assert "Lenny Rachitsky" in mismatches[0]
    assert "Sean Ellis emphasized" in corrected
    assert "Lenny Rachitsky" not in corrected


def test_clean_heading_profanity_rewrites_law_of_shitty_clickthroughs():
    """Verify profanity/slang in headings is rewritten while preserved in body text in quotes."""
    essay_text = (
        "# Growth Playbook\n\n"
        "## The Law of Shitty Clickthroughs\n\n"
        'Andrew Chen coined the "Law of Shitty Clickthroughs" to describe diminishing returns.'
    )
    cleaned = clean_heading_profanity(essay_text)
    assert "## Feedback Loops and Diminishing Returns" in cleaned
    assert 'Andrew Chen coined the "Law of Shitty Clickthroughs"' in cleaned

