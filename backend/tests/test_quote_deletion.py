"""STEP 2 regression: fabricated quote sentences must be DELETED from the stored essay."""

from __future__ import annotations

from types import SimpleNamespace

from app.agent.verify import strip_unverified_quote_sentences


def _chunk(text, guest="Sean Ellis", slug="sean-ellis"):
    return SimpleNamespace(
        text=text, guest=guest, title=f"{guest} Episode", document_slug=slug,
        chunk_id="x", score=0.9, speaker=None,
        start_char=0, end_char=len(text), chunk_index=0,
    )


def test_fabricated_quote_sentence_is_deleted():
    sources = [_chunk("real content about activation that mentions the aha moment")]
    essay = (
        "Growth starts with activation.\n\n"
        'As Sean Ellis puts it, "activation is just so critical to any strategy" '
        "and that matters [S1].\n\n"
        "The second paragraph has a real supported claim [S1]."
    )
    cleaned, deleted = strip_unverified_quote_sentences(essay, sources)
    assert "activation is just so critical" not in cleaned, cleaned
    assert deleted >= 1
    assert "The second paragraph has a real supported claim" in cleaned


def test_verbatim_quote_sentence_is_kept():
    sources = [_chunk(
        "the rule I live by is this: do is better than show is better than tell",
        guest="Hila Qu", slug="hila-qu",
    )]
    essay = (
        'Hila Qu says: "do is better than show is better than tell" [S1].\n\n'
        "Next paragraph."
    )
    cleaned, deleted = strip_unverified_quote_sentences(essay, sources)
    assert "do is better than show is better than tell" in cleaned
    assert deleted == 0


def test_short_quote_is_not_touched():
    """< 6-word quoted span is not treated as a direct quote."""
    sources = [_chunk("some content")]
    essay = 'He called it a "big deal" [S1]. Second sentence [S1].'
    cleaned, deleted = strip_unverified_quote_sentences(essay, sources)
    assert cleaned.strip() == essay.strip()
    assert deleted == 0
