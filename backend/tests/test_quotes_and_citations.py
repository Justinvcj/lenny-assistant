"""Regression tests for D2/D3/D5: fabricated quotes, paraphrases, citation forms."""

from __future__ import annotations

from types import SimpleNamespace

from app.agent.verify import normalize_citations, verify_direct_quotes


def _chunk(text, guest="Sean Ellis", title="Sean Ellis Episode", slug="sean-ellis"):
    return SimpleNamespace(
        text=text, guest=guest, title=title, document_slug=slug,
        chunk_id="x", score=0.9, speaker=None, start_char=0,
        end_char=len(text), chunk_index=0,
    )


# ---------------------------------------------------------------------------
# D5: citation normalization
# ---------------------------------------------------------------------------


def test_norm_simple_paren():
    assert "[S1]" in normalize_citations("Growth matters (S1).")


def test_norm_timestamp_wrapper():
    assert normalize_citations("He said this ([S4], 00:48:00) early on.") == "He said this [S4] early on."


def test_norm_bracket_comma_list_collapses():
    assert "[S3][S4]" in normalize_citations("Both leaders agree [S3, S4].")


def test_norm_bare_after_punct():
    assert "[S3]" in normalize_citations("...through the doors. S3")


# ---------------------------------------------------------------------------
# D2 / D3: direct quote verification
# ---------------------------------------------------------------------------


def test_fabricated_quote_is_not_verified():
    """D2: a quoted string that exists in no chunk must count as unverified."""
    sources = [_chunk("real transcript content about activation and growth")]
    essay = (
        'Sean Ellis says, "activation is just so critical to any product strategy" '
        "and that matters [S1]."
    )
    cleaned, valid, total = verify_direct_quotes(essay, sources)
    assert total == 1
    assert valid == 0, f"Expected 0 verified, got {valid}/{total} — cleaned={cleaned!r}"


def test_paraphrase_quote_marks_stripped():
    """D3: paraphrase presented as verbatim loses its quote marks and the sentence
    may be kept only if the [S#] separately supports the claim."""
    sources = [_chunk(
        "like when do I think they've had a good enough experience with the "
        "product to really know it?"
    )]
    essay = (
        'Ellis asks, "When do we think they\'ve had a good enough experience '
        'to really know it?" [S1].'
    )
    cleaned, valid, total = verify_direct_quotes(essay, sources)
    # Not an exact verbatim match → quote marks must come off.
    assert '"When do we think' not in cleaned, cleaned
    assert '"' not in cleaned.replace("they've", "theys") or valid == 1


def test_verbatim_quote_is_kept():
    """Hila Qu's `do is better than show is better than tell` is verbatim and must pass."""
    sources = [_chunk(
        "The rule I live by is this: do is better than show is better than tell. "
        "That is my mantra.",
        guest="Hila Qu", title="Hila Qu Episode", slug="hila-qu",
    )]
    essay = 'Hila Qu reminds listeners: "do is better than show is better than tell" [S1].'
    cleaned, valid, total = verify_direct_quotes(essay, sources)
    assert valid == 1 and total == 1, f"Expected 1/1 verified, got {valid}/{total}"
    assert '"do is better than show is better than tell"' in cleaned
