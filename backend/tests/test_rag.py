"""Unit tests for transcript parser and chunker using isolated fixture strings."""

from datetime import date
import uuid

from app.models import Chunk, Document
from app.rag.parser import (
    SpeakerTurn,
    compute_content_hash,
    parse_transcript,
    parse_transcript_text,
)
from app.rag.chunking import (
    ChunkDraft,
    chunk_document,
    chunk_turns,
    determine_primary_speaker,
    estimate_tokens,
    split_long_turn,
    split_sentences,
)


# --- Test Fixtures ---

FIXTURE_STANDARD_PODCAST = """---
title: "The grief, loneliness, and burnout sweeping through tech | Molly Graham"
date: "2026-09-27"
type: "podcast"
guest: "Molly Graham"
post_url: "https://www.lennysnewsletter.com/p/the-grief-loneliness"
description: "Molly Graham discusses burnout, giving away Legos, and leadership in tech."
word_count: 18220
---

**Lenny Rachitsky** (00:00:00):
So, we've been chatting about your famous giveaway, your Legos career advice.

**Molly Graham** (00:00:09):
The narrative right now is literally like, okay, we hired this new employee.

**Lenny** (00:00:26):
Here's the big question, Molly. Are there any Legos you should not give away?
"""

FIXTURE_WITH_ANOMALIES = """---
title: "Sam Lessin Interview"
date: "2026-05-10"
type: "podcast"
guest: "Sam Lessin"
---

**Sam Lessin** (00:01:00):
You know what's great?

**Area 51, An Uncensored History**:
The Top Secret Military Base. Not very Erudite, great book.

**Lenny Rachitsky** (00:01:30):
**Sam Lessin** (00:02:30):
That is an awesome book.
"""

FIXTURE_LONG_TURN_PODCAST = """---
title: "Deep Dive on Scaled Architecture | Alex Architect"
date: "2026-07-20"
guest: "Alex Architect"
---

**Lenny Rachitsky** (00:00:00):
Alex, tell us how your team scaled the distributed engine under extreme load.

**Alex Architect** (00:00:20):
First, we decoupled all write operations from read replicas to eliminate locking bottlenecks across database clusters. In doing so, we observed that network latency dropped by over forty percent within the first two weeks of continuous deployment. Furthermore, every engineering team adopted strict asynchronous event processing using persistent queues, ensuring that downstream consumer slowdowns never degraded client ingestion endpoints. Additionally, our observability pipeline was completely rewritten to aggregate high-cardinality telemetry in memory before flushing compacted summaries to durable storage, drastically reducing storage costs. Over time, these architectural principles allowed us to sustain tenfold traffic spikes with zero user-visible degradation or operational alerts. We also implemented proactive backpressure controls at every ingress gateway to reject malformed requests early. Finally, comprehensive chaos engineering experiments proved that individual pod terminations caused no transaction failures across any active customer sessions.
"""


# --- Parser Tests ---

def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("   \n\t  ") == 0
    assert estimate_tokens("hello world") == 3  # round(2 * 1.3) = 3
    assert estimate_tokens(" ".join(["word"] * 100)) == 130


def test_split_sentences():
    text = (
        "Hello Dr. Becky! How are you today? We are comparing Python vs. Go. "
        "That is, i.e. when performance matters. E.g. high throughput servers! Next sentence."
    )
    sentences = split_sentences(text)
    assert len(sentences) == 6
    assert sentences[0] == "Hello Dr. Becky!"
    assert sentences[1] == "How are you today?"
    assert sentences[2] == "We are comparing Python vs. Go."
    assert sentences[3] == "That is, i.e. when performance matters."
    assert sentences[4] == "E.g. high throughput servers!"
    assert sentences[5] == "Next sentence."


def test_parse_frontmatter_and_metadata():
    doc = parse_transcript(
        content=FIXTURE_STANDARD_PODCAST,
        source_path="data/podcasts/molly-graham.md",
        slug="molly-graham",
    )
    assert doc.slug == "molly-graham"
    assert doc.title == "The grief, loneliness, and burnout sweeping through tech | Molly Graham"
    assert doc.guest == "Molly Graham"
    assert doc.published_at == date(2026, 9, 27)
    assert doc.source_path == "data/podcasts/molly-graham.md"
    assert doc.metadata["post_url"] == "https://www.lennysnewsletter.com/p/the-grief-loneliness"
    assert doc.metadata["word_count"] == 18220
    assert doc.metadata["type"] == "podcast"


def test_parse_speaker_turns_and_offsets():
    doc = parse_transcript_text(FIXTURE_STANDARD_PODCAST, slug="molly-graham")
    turns = doc.turns
    assert len(turns) == 3

    assert turns[0].speaker == "Lenny Rachitsky"
    assert turns[0].timestamp == "00:00:00"
    assert turns[0].text == "So, we've been chatting about your famous giveaway, your Legos career advice."

    assert turns[1].speaker == "Molly Graham"
    assert turns[1].timestamp == "00:00:09"

    # Lenny host normalization check: "**Lenny**" -> "Lenny Rachitsky"
    assert turns[2].speaker == "Lenny Rachitsky"
    assert turns[2].timestamp == "00:00:26"

    # Verbatim offset verification: raw_text[start_char:end_char] == turn.text
    for turn in turns:
        assert turn.start_char < turn.end_char
        assert turn.turn_start_char < turn.turn_end_char
        assert turn.turn_start_char <= turn.start_char
        assert turn.end_char <= turn.turn_end_char
        extracted = FIXTURE_STANDARD_PODCAST[turn.start_char : turn.end_char]
        assert extracted == turn.text


def test_parse_anomalies_and_empty_turns():
    doc = parse_transcript_text(FIXTURE_WITH_ANOMALIES, slug="sam-lessin")
    # Empty turn at 00:01:30 should be dropped
    # **Area 51, An Uncensored History**: should remain part of Sam Lessin's turn (not a separate turn)
    assert len(doc.turns) == 2
    assert doc.metadata["empty_turns_dropped"] == 1

    first_turn = doc.turns[0]
    assert first_turn.speaker == "Sam Lessin"
    assert "Area 51, An Uncensored History" in first_turn.text

    second_turn = doc.turns[1]
    assert second_turn.speaker == "Sam Lessin"
    assert second_turn.timestamp == "00:02:30"
    assert second_turn.text == "That is an awesome book."


def test_deterministic_content_hash():
    crlf_content = "Line 1\r\nLine 2\r\nLine 3"
    lf_content = "Line 1\nLine 2\nLine 3"
    hash_crlf = compute_content_hash(crlf_content)
    hash_lf = compute_content_hash(lf_content)
    assert hash_crlf == hash_lf

    diff_content = "Line 1\nLine 2\nLine 4"
    assert compute_content_hash(diff_content) != hash_lf


def test_to_document_model():
    doc = parse_transcript_text(FIXTURE_STANDARD_PODCAST, source_path="data/test.md", slug="test-slug")
    custom_id = uuid.uuid4()
    model = doc.to_document_model(doc_id=custom_id)
    assert isinstance(model, Document)
    assert model.id == custom_id
    assert model.slug == "test-slug"
    assert model.title == doc.title
    assert model.guest == "Molly Graham"
    assert model.published_at == date(2026, 9, 27)
    assert model.source_path == "data/test.md"
    assert model.content_hash == doc.content_hash
    assert model.metadata_["type"] == "podcast"


# --- Chunker Tests ---

def test_chunk_grouping_and_target_size():
    # Construct 5 short turns (~50 tokens each)
    turns = [
        SpeakerTurn(
            speaker=f"Speaker {i}",
            timestamp=f"00:0{i}:00",
            text=f"This is an informative utterance number {i} discussing product strategies and user retention frameworks in modern software companies.",
            start_char=i * 200 + 50,
            end_char=(i + 1) * 200,
            turn_start_char=i * 200,
            turn_end_char=(i + 1) * 200,
            turn_index=i,
        )
        for i in range(5)
    ]
    chunks = chunk_turns(turns, min_tokens=50, max_tokens=100, target_tokens=80)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.token_count > 0
        assert chunk.chunk_index is not None
        assert chunk.start_char < chunk.end_char
        assert chunk.speaker in [f"Speaker {i}" for i in range(5)]


def test_chunk_one_turn_overlap():
    turns = [
        SpeakerTurn(
            speaker="Lenny Rachitsky",
            timestamp="00:00:00",
            text="Sentence one about product activation loops and early retention signals.",
            start_char=30,
            end_char=100,
            turn_start_char=0,
            turn_end_char=100,
            turn_index=0,
        ),
        SpeakerTurn(
            speaker="Guest",
            timestamp="00:01:00",
            text="Sentence two explaining the viral coefficient and organic referral growth.",
            start_char=130,
            end_char=200,
            turn_start_char=100,
            turn_end_char=200,
            turn_index=1,
        ),
        SpeakerTurn(
            speaker="Lenny Rachitsky",
            timestamp="00:02:00",
            text="Sentence three inquiring about how churn dynamics change across different cohorts.",
            start_char=230,
            end_char=310,
            turn_start_char=200,
            turn_end_char=310,
            turn_index=2,
        ),
        SpeakerTurn(
            speaker="Guest",
            timestamp="00:03:00",
            text="Sentence four concluding our detailed analysis of customer lifetime value curves.",
            start_char=340,
            end_char=420,
            turn_start_char=310,
            turn_end_char=420,
            turn_index=3,
        ),
    ]

    # Use tight window so 2 turns fit in each chunk
    chunks = chunk_turns(turns, min_tokens=20, max_tokens=30, target_tokens=25)
    assert len(chunks) >= 2
    # The last turn of Chunk 0 should be the first turn of Chunk 1
    chunk_0_last_turn = chunks[0].turns[-1]
    chunk_1_first_turn = chunks[1].turns[0]
    assert chunk_0_last_turn.speaker == chunk_1_first_turn.speaker
    assert chunk_0_last_turn.text == chunk_1_first_turn.text


def test_chunk_long_turn_sentence_split_preservation():
    doc = parse_transcript_text(FIXTURE_LONG_TURN_PODCAST, slug="alex")
    # Alex's turn is ~180 tokens; set max_tokens=60 to force sentence-boundary splitting
    chunks = chunk_document(doc, min_tokens=40, max_tokens=60)
    assert len(chunks) >= 3

    # Verify sentence preservation: no chunk should end mid-sentence
    for c in chunks:
        stripped = c.text.strip()
        assert stripped[-1] in [".", "!", "?"], f"Chunk ended without terminal punctuation: {stripped[-30:]}"


def test_primary_speaker_assignment():
    turns = [
        SpeakerTurn(
            speaker="Lenny Rachitsky",
            timestamp="00:00:00",
            text="Quick question.",
            start_char=0,
            end_char=15,
            turn_start_char=0,
            turn_end_char=15,
            turn_index=0,
        ),
        SpeakerTurn(
            speaker="Expert Guest",
            timestamp="00:00:10",
            text="A very long and exhaustive answer with lots of details about growth engines and product execution.",
            start_char=16,
            end_char=120,
            turn_start_char=16,
            turn_end_char=120,
            turn_index=1,
        ),
    ]
    primary = determine_primary_speaker(turns)
    assert primary == "Expert Guest"


def test_to_chunk_model():
    turns = [
        SpeakerTurn(
            speaker="Lenny Rachitsky",
            timestamp="00:00:00",
            text="Hello world.",
            start_char=30,
            end_char=42,
            turn_start_char=0,
            turn_end_char=42,
            turn_index=0,
        )
    ]
    draft = ChunkDraft(
        chunk_index=0,
        text="**Lenny Rachitsky** (00:00:00):\nHello world.",
        token_count=6,
        speaker="Lenny Rachitsky",
        start_char=0,
        end_char=42,
        turns=turns,
    )
    doc_id = uuid.uuid4()
    custom_chunk_id = uuid.uuid4()
    dummy_embedding = [0.1] * 768

    model = draft.to_chunk_model(
        document_id=doc_id,
        embedding=dummy_embedding,
        chunk_id=custom_chunk_id,
    )
    assert isinstance(model, Chunk)
    assert model.id == custom_chunk_id
    assert model.document_id == doc_id
    assert model.chunk_index == 0
    assert model.token_count == 6
    assert model.speaker == "Lenny Rachitsky"
    assert model.start_char == 0
    assert model.end_char == 42
    assert model.embedding == dummy_embedding


def test_tail_chunk_merging():
    # 3 turns: 2 medium turns followed by a tiny 5-token outro turn
    turns = [
        SpeakerTurn(
            speaker="Lenny Rachitsky",
            timestamp="00:00:00",
            text="First substantial topic with lots of insightful discussion points.",
            start_char=0,
            end_char=70,
            turn_start_char=0,
            turn_end_char=70,
            turn_index=0,
        ),
        SpeakerTurn(
            speaker="Guest",
            timestamp="00:01:00",
            text="Second substantial topic continuing the comprehensive technical explanation.",
            start_char=70,
            end_char=150,
            turn_start_char=70,
            turn_end_char=150,
            turn_index=1,
        ),
        SpeakerTurn(
            speaker="Lenny Rachitsky",
            timestamp="00:02:00",
            text="Thanks for listening everyone. Bye!",
            start_char=150,
            end_char=190,
            turn_start_char=150,
            turn_end_char=190,
            turn_index=2,
        ),
    ]
    # Set max_tokens high enough to hold all 3 turns, but test that tail merges properly
    chunks = chunk_turns(turns, min_tokens=10, max_tokens=100)
    assert len(chunks) == 1
    assert "Thanks for listening everyone. Bye!" in chunks[0].text


# --- Regression Tests from Milestone 1 Review ---

FIXTURE_BOM_PODCAST = (
    "\ufeff---\n"
    "title: \"BOM Handling Episode\"\n"
    "guest: \"BOM Guest\"\n"
    "date: \"2026-09-01\"\n"
    "---\n\n"
    "**Lenny Rachitsky** (00:00:00):\n"
    "Welcome to the podcast.\n"
)

FIXTURE_REPEATING_SENTENCES = (
    "This is a recurring phrase. " * 30
)


def _create_synthetic_turn(idx: int, tokens: int, speaker: str = "Guest") -> SpeakerTurn:
    """Helper to generate a synthetic SpeakerTurn with predictable token sizing."""
    words = " ".join([f"topic_{idx}_{w}" for w in range(int(tokens / 1.3))])
    text = f"Turn {idx}. " + words + "."
    return SpeakerTurn(
        speaker=speaker,
        timestamp=f"00:0{idx}:00",
        text=text,
        start_char=idx * 1000,
        end_char=idx * 1000 + len(text),
        turn_start_char=idx * 1000,
        turn_end_char=(idx + 1) * 1000,
        turn_index=idx,
    )


def test_regression_bom_handling():
    """Ensure UTF-8 byte order mark does not cause frontmatter extraction to drop metadata."""
    doc = parse_transcript_text(FIXTURE_BOM_PODCAST, slug="bom-episode")
    assert doc.title == "BOM Handling Episode"
    assert doc.guest == "BOM Guest"
    assert len(doc.turns) == 1
    assert doc.turns[0].speaker == "Lenny Rachitsky"


def test_regression_quote_and_abbreviation_splitting():
    """Ensure sentences ending or starting with quotation marks split cleanly, and abbreviations are preserved."""
    # Dialogue quote at sentence end
    text1 = 'He said, "This is the first sentence." Then he smiled. And she replied, "Yes indeed."'
    sents1 = split_sentences(text1)
    assert len(sents1) == 3
    assert sents1[0] == 'He said, "This is the first sentence."'
    assert sents1[1] == "Then he smiled."
    assert sents1[2] == 'And she replied, "Yes indeed."'

    # Dialogue quote at sentence start
    text2 = 'First sentence completed. "Is this the next sentence?" asked Lenny.'
    sents2 = split_sentences(text2)
    assert len(sents2) == 2
    assert sents2[0] == "First sentence completed."
    assert sents2[1] == '"Is this the next sentence?" asked Lenny.'

    # Smart / curly quotes
    text3 = 'Lenny noted, “This works well.” Afterwards we left.'
    sents3 = split_sentences(text3)
    assert len(sents3) == 2
    assert sents3[0] == "Lenny noted, “This works well.”"
    assert sents3[1] == "Afterwards we left."

    # Capitalized E.g. and I.e. followed by capitalized words
    text4 = "We tested multiple options. E.g. Python was much faster than Ruby."
    sents4 = split_sentences(text4)
    assert len(sents4) == 2
    assert sents4[0] == "We tested multiple options."
    assert sents4[1] == "E.g. Python was much faster than Ruby."

    text5 = "We need high performance. I.e. Go or Rust is preferred."
    sents5 = split_sentences(text5)
    assert len(sents5) == 2
    assert sents5[0] == "We need high performance."
    assert sents5[1] == "I.e. Go or Rust is preferred."

    # Geographic / corporate abbreviations
    text6 = "The U.S. Department of Justice investigated."
    sents6 = split_sentences(text6)
    assert len(sents6) == 1

    text7 = "We partnered with Stripe Inc. Before the launch date."
    sents7 = split_sentences(text7)
    assert len(sents7) == 1


def test_regression_repeating_sentences_offset_preservation():
    """Ensure split_long_turn does not collapse offsets when identical sentences repeat."""
    raw_text = FIXTURE_REPEATING_SENTENCES.strip()
    turn = SpeakerTurn(
        speaker="Guest",
        timestamp="00:00:00",
        text=raw_text,
        start_char=50,
        end_char=50 + len(raw_text),
        turn_start_char=0,
        turn_end_char=50 + len(raw_text),
        turn_index=0,
    )
    sub_turns = split_long_turn(turn, max_tokens=60)
    assert len(sub_turns) > 1

    for idx, st in enumerate(sub_turns):
        assert st.start_char < st.end_char
        rel_start = st.start_char - turn.start_char
        rel_end = st.end_char - turn.start_char
        sliced = raw_text[rel_start:rel_end]
        assert sliced == st.text, (
            f"Subturn {idx} slice mismatch: sliced '{sliced}' ({len(sliced)} chars) vs "
            f"expected '{st.text}' ({len(st.text)} chars)"
        )


def test_regression_consecutive_chunks_one_turn_overlap_and_no_redundant_subsets():
    """Ensure 1-turn overlap is strictly maintained without zero-overlap breaks or redundant subset chunks."""
    turns = [
        _create_synthetic_turn(0, 100),
        _create_synthetic_turn(1, 150),
        _create_synthetic_turn(2, 332),  # Substantive turn (~330 tokens)
        _create_synthetic_turn(3, 200),
        _create_synthetic_turn(4, 200),
    ]

    chunks = chunk_turns(turns, min_tokens=350, max_tokens=450)
    assert len(chunks) >= 2

    # Invariant 1: Exactly 1-turn overlap across every adjacent pair
    for k in range(len(chunks) - 1):
        c1 = chunks[k]
        c2 = chunks[k + 1]
        s1 = set(t.start_char for t in c1.turns)
        s2 = set(t.start_char for t in c2.turns)
        overlap = s1.intersection(s2)
        assert len(overlap) == 1, (
            f"Zero or multiple overlap between Chunk {k} and {k+1}: got {len(overlap)} overlapping turns! "
            f"Chunk {k} turns={[t.turn_index for t in c1.turns]}, Chunk {k+1} turns={[t.turn_index for t in c2.turns]}"
        )

    # Invariant 2: No chunk is a redundant subset of the immediately preceding chunk
    for k in range(1, len(chunks)):
        prev_s = set(t.start_char for t in chunks[k - 1].turns)
        curr_s = set(t.start_char for t in chunks[k].turns)
        assert not curr_s.issubset(prev_s), (
            f"Chunk {k} (turns={[t.turn_index for t in chunks[k].turns]}) is a redundant subset of Chunk {k-1}"
        )

