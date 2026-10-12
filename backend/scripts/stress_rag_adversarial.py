"""Adversarial stress-testing suite for Lenny Growth Assistant (Milestone 1 / P3b).

Empirically challenges backend/app/rag/parser.py and backend/app/rag/chunking.py
against edge cases, malformed data, unicode quirks, boundary conditions,
and offset preservation invariants.
"""

import sys
from pathlib import Path
from typing import Any

# Ensure backend directory is in sys.path
current_dir = Path(__file__).resolve().parent
backend_dir = current_dir.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.rag.chunking import (
    chunk_document,
    chunk_turns,
    split_long_turn,
    split_sentences,
)
from app.rag.parser import (
    SpeakerTurn,
    extract_speaker_turns,
    parse_transcript_file,
    parse_transcript_text,
)


class TestResult:
    def __init__(self, name: str, category: str):
        self.name = name
        self.category = category
        self.passed = True
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.details: dict[str, Any] = {}

    def fail(self, msg: str):
        self.passed = False
        self.failures.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)


def test_bom_handling() -> TestResult:
    """Test parser behavior with UTF-8 BOM."""
    res = TestResult("UTF-8 BOM Handling", "Parser")
    raw_with_bom = "\ufeff---\ntitle: \"BOM Test\"\nguest: \"Test Guest\"\n---\n\n**Lenny Rachitsky** (00:00:00):\nHello world.\n"
    doc = parse_transcript_text(raw_with_bom, slug="bom-test")
    
    if doc.title != "BOM Test":
        res.fail(f"BOM caused frontmatter failure: title is '{doc.title}', expected 'BOM Test'")
    if doc.guest != "Test Guest":
        res.fail(f"BOM caused guest failure: guest is '{doc.guest}', expected 'Test Guest'")
    if len(doc.turns) != 1:
        res.fail(f"BOM caused turns failure: found {len(doc.turns)} turns, expected 1")
    return res


def test_empty_and_whitespace_inputs() -> TestResult:
    """Test parser and chunker with empty and whitespace inputs."""
    res = TestResult("Empty & Whitespace Inputs", "Parser/Chunker")
    
    # Completely empty
    doc_empty = parse_transcript_text("", slug="empty")
    if doc_empty.turns:
        res.fail(f"Empty text produced {len(doc_empty.turns)} turns")
    chunks_empty = chunk_document(doc_empty)
    if chunks_empty:
        res.fail(f"Empty doc produced {len(chunks_empty)} chunks")
        
    # Only whitespace
    doc_ws = parse_transcript_text("   \n\t  \n  ", slug="whitespace")
    if doc_ws.turns:
        res.fail(f"Whitespace-only text produced {len(doc_ws.turns)} turns")
    chunks_ws = chunk_document(doc_ws)
    if chunks_ws:
        res.fail(f"Whitespace doc produced {len(chunks_ws)} chunks")
        
    # Frontmatter only
    fm_only = "---\ntitle: Only Frontmatter\nguest: Nobody\n---\n"
    doc_fm = parse_transcript_text(fm_only, slug="fm-only")
    if doc_fm.title != "Only Frontmatter":
        res.fail(f"Title parse failed on fm-only: {doc_fm.title}")
    if doc_fm.turns:
        res.fail(f"Turns produced on fm-only: {len(doc_fm.turns)}")
    chunks_fm = chunk_document(doc_fm)
    if chunks_fm:
        res.fail(f"Chunks produced on fm-only: {len(chunks_fm)}")
        
    # No frontmatter, just turns
    no_fm = "**Lenny Rachitsky** (00:00:00):\nHello without frontmatter."
    doc_no_fm = parse_transcript_text(no_fm, slug="no-fm")
    if len(doc_no_fm.turns) != 1:
        res.fail(f"No-frontmatter turns failed: {len(doc_no_fm.turns)}")
    chunks_no_fm = chunk_document(doc_no_fm)
    if len(chunks_no_fm) != 1:
        res.fail(f"No-frontmatter chunks failed: {len(chunks_no_fm)}")
        
    return res


def test_malformed_yaml_frontmatter() -> TestResult:
    """Test parser resilience against malformed YAML."""
    res = TestResult("Malformed YAML Resilience", "Parser")
    bad_yaml = "---\n: this is invalid yaml: [unclosed\n---\n\n**Lenny** (00:00:00):\nDialogue still exists.\n"
    try:
        doc = parse_transcript_text(bad_yaml, slug="bad-yaml")
        if len(doc.turns) != 1:
            res.fail(f"Malformed YAML dropped valid turns: found {len(doc.turns)}")
        if doc.turns[0].text != "Dialogue still exists.":
            res.fail(f"Unexpected turn text: {doc.turns[0].text}")
    except Exception as e:
        res.fail(f"Malformed YAML crashed parser with exception: {type(e).__name__}: {e}")
    return res


def test_inverted_offsets_on_unfiltered_empty_turns() -> TestResult:
    """Test if extract_speaker_turns with filter_empty=False produces inverted offsets."""
    res = TestResult("Unfiltered Empty Turn Offset Inversion", "Parser")
    text = (
        "**Lenny Rachitsky** (00:00:00):\n"
        "   \n"
        "**Guest** (00:00:10):\n"
        "Hello."
    )
    turns, dropped = extract_speaker_turns(text, filter_empty=False)
    if len(turns) != 2:
        res.fail(f"Expected 2 turns with filter_empty=False, got {len(turns)}")
        return res
    
    empty_turn = turns[0]
    if empty_turn.start_char > empty_turn.end_char:
        res.fail(
            f"CRITICAL: Inverted offsets on empty turn: start_char={empty_turn.start_char} > "
            f"end_char={empty_turn.end_char} (length={empty_turn.end_char - empty_turn.start_char})"
        )
    return res


def test_split_long_turn_duplicate_sentence_offset_bug() -> TestResult:
    """CRITICAL: Test offset calculation in split_long_turn when sentences repeat."""
    res = TestResult("Duplicate Sentence Offset Corruption in Monologue", "Chunking")
    
    # Construct a turn that exceeds max_tokens (e.g. 500 tokens)
    # where a sentence repeats at the beginning and end of a sub-group
    s1 = "We believed in extreme customer obsession and fast iteration cycles."
    s2 = "Our engineering teams shipped software multiple times every single day."
    s3 = "We believed in extreme customer obsession and fast iteration cycles."
    
    # Pad to exceed max_tokens
    filler = " ".join([f"Detailed analysis paragraph step {i} explaining product growth loops." for i in range(15)])
    
    text = f"{s1} {filler} {s2} {s3} {filler}"
    
    turn = SpeakerTurn(
        speaker="Guest",
        timestamp="00:01:00",
        text=text,
        start_char=100,
        end_char=100 + len(text),
        turn_start_char=50,
        turn_end_char=100 + len(text) + 20,
        turn_index=0,
    )
    
    # Split with max_tokens set low enough to force multiple sub-turns
    sub_turns = split_long_turn(turn, max_tokens=100)
    
    for idx, st in enumerate(sub_turns):
        # Invariant 1: start_char must be < end_char
        if st.start_char >= st.end_char:
            res.fail(f"Sub-turn {idx}: start_char ({st.start_char}) >= end_char ({st.end_char})")
            
        # Invariant 2: raw slice must contain the expected content
        # Note: turn.text offset relative to turn.start_char
        rel_start = st.start_char - turn.start_char
        rel_end = st.end_char - turn.start_char
        
        if rel_start < 0 or rel_end > len(turn.text):
            res.fail(f"Sub-turn {idx}: offsets out of bounds [0, {len(turn.text)}]: [{rel_start}, {rel_end}]")
            continue
            
        sliced_from_text = turn.text[rel_start:rel_end]
        
        # Check if first sentence is in sliced_from_text
        sents = split_sentences(st.text)
        if sents:
            first_sent = sents[0]
            last_sent = sents[-1]
            if not sliced_from_text.startswith(first_sent):
                res.fail(
                    f"Sub-turn {idx} offset mismatch: slice starts with '{sliced_from_text[:30]}...', "
                    f"expected '{first_sent[:30]}...'"
                )
            if not sliced_from_text.endswith(last_sent):
                res.fail(
                    f"Sub-turn {idx} offset mismatch: slice ends with '...{sliced_from_text[-30:]}', "
                    f"expected '...{last_sent[-30:]}'"
                )
                
    return res


def test_split_long_turn_identical_repeated_sentences() -> TestResult:
    """Test offset computation when turn consists of identical sentences."""
    res = TestResult("Identical Sentences Sub-Turn Offset Collapse", "Chunking")
    sent = "This is a recurring phrase."
    num_sents = 40  # ~40 * 7 = 280 tokens
    text = " ".join([sent] * num_sents)
    
    turn = SpeakerTurn(
        speaker="Speaker",
        timestamp="00:00:00",
        text=text,
        start_char=0,
        end_char=len(text),
        turn_start_char=0,
        turn_end_char=len(text),
        turn_index=0,
    )
    
    sub_turns = split_long_turn(turn, max_tokens=50)
    for idx, st in enumerate(sub_turns):
        rel_start = st.start_char
        rel_end = st.end_char
        sliced = text[rel_start:rel_end]
        st_sents = split_sentences(st.text)
        expected_len = len(" ".join(st_sents))
        
        if len(st_sents) > 1 and len(sliced) < expected_len:
            res.fail(
                f"Sub-turn {idx} offset collapsed! st.text has {len(st_sents)} sentences "
                f"({len(st.text)} chars), but slice text[start:end] is only {len(sliced)} chars: '{sliced}'"
            )
            break
            
    return res


def test_quote_sentence_splitting() -> TestResult:
    """Test if split_sentences handles dialogue with quotation marks."""
    res = TestResult("Quotation Mark Sentence Boundary Splitting", "Chunking")
    
    # Case 1: Period inside quotation mark
    text1 = 'He said, "This is the first sentence." Then he smiled. And she replied, "Yes indeed."'
    sents1 = split_sentences(text1)
    # Expected: 3 sentences
    if len(sents1) < 3:
        res.fail(
            f"Failed to split sentences ending in quotes: got {len(sents1)} sentences, expected 3. "
            f"Sentences: {sents1}"
        )
        
    # Case 2: Next sentence starts with quotation mark
    text2 = 'First sentence completed. "Is this the next sentence?" asked Lenny.'
    sents2 = split_sentences(text2)
    if len(sents2) < 2:
        res.fail(
            f"Failed to split when next sentence starts with quote: got {len(sents2)}, expected 2. "
            f"Sentences: {sents2}"
        )
        
    # Case 3: Curly/smart quotes
    text3 = 'Lenny noted, “This works well.” Afterwards we left.'
    sents3 = split_sentences(text3)
    if len(sents3) < 2:
        res.fail(
            f"Failed to split with curly quotes: got {len(sents3)}, expected 2. "
            f"Sentences: {sents3}"
        )
        
    return res


def test_abbreviation_protections() -> TestResult:
    """Test sentence splitting on various abbreviations and false positives."""
    res = TestResult("Abbreviation Protections & Edge Cases", "Chunking")
    
    # Case 1: Capitalized E.g. followed by Capital letter
    text_eg_cap = "We tested multiple options. E.g. Python was much faster than Ruby."
    sents_eg = split_sentences(text_eg_cap)
    # Should NOT split after 'E.g.'
    for s in sents_eg:
        if s == "E.g." or s.startswith("Python"):
            res.fail(f"Capitalized 'E.g.' was split mid-abbreviation: {sents_eg}")
            break
            
    # Case 2: Capitalized I.e. followed by Capital letter
    text_ie_cap = "We need high performance. I.e. Go or Rust is preferred."
    sents_ie = split_sentences(text_ie_cap)
    for s in sents_ie:
        if s == "I.e." or s.startswith("Go"):
            res.fail(f"Capitalized 'I.e.' was split mid-abbreviation: {sents_ie}")
            break
            
    # Case 3: U.S. followed by Capital letter
    text_us = "The team launched in the U.S. Market expansion happened fast."
    sents_us = split_sentences(text_us)
    # If it splits mid-U.S. or after U.S. when it shouldn't
    text_us_mid = "The U.S. Department of Justice investigated."
    sents_us_mid = split_sentences(text_us_mid)
    if len(sents_us_mid) > 1:
        res.fail(f"'U.S.' split mid-sentence: {sents_us_mid}")
        
    # Case 4: Inc. or Corp.
    text_inc = "We partnered with Stripe Inc. Before the launch date."
    sents_inc = split_sentences(text_inc)
    if len(sents_inc) > 1:
        res.fail(f"'Inc.' split mid-sentence: {sents_inc}")
        
    return res


def test_extreme_monologue_no_punctuation() -> TestResult:
    """Test chunker behavior when a 2,000 word monologue has NO punctuation."""
    res = TestResult("Extreme Unpunctuated Monologue (Run-on)", "Chunking")
    
    words = [f"word{i}" for i in range(1500)]  # ~1950 tokens
    text = " ".join(words)
    
    turn = SpeakerTurn(
        speaker="Monologue Speaker",
        timestamp="00:00:00",
        text=text,
        start_char=0,
        end_char=len(text),
        turn_start_char=0,
        turn_end_char=len(text),
        turn_index=0,
    )
    
    chunks = chunk_turns([turn], min_tokens=350, max_tokens=450)
    
    if len(chunks) == 1:
        c = chunks[0]
        if c.token_count > 1000:
            res.fail(
                f"Chunker failed to constrain unpunctuated monologue: produced 1 chunk with "
                f"{c.token_count} tokens (max target was 450)"
            )
    return res


def test_one_turn_overlap_stability() -> TestResult:
    """Test 1-turn overlap across various dialogue patterns."""
    res = TestResult("1-Turn Overlap Invariant Verification", "Chunking")
    
    # Scenario A: Standard multi-turn dialogue with moderate turns
    turns_a = [
        SpeakerTurn(
            speaker=f"Speaker {i % 2}",
            timestamp=f"00:0{i}:00",
            text=f"Turn {i}: " + " ".join([f"topic_{i}_{j}" for j in range(70)]),  # ~90 tokens each
            start_char=i * 600,
            end_char=i * 600 + 500,
            turn_start_char=i * 600,
            turn_end_char=(i + 1) * 600,
            turn_index=i,
        )
        for i in range(10)
    ]
    chunks_a = chunk_turns(turns_a, min_tokens=200, max_tokens=300)
    
    overlap_violations = []
    for k in range(len(chunks_a) - 1):
        c_curr = chunks_a[k]
        c_next = chunks_a[k + 1]
        
        # Check if the last turn of c_curr is in c_next
        last_turn_curr = c_curr.turns[-1]
        first_turn_next = c_next.turns[0]
        
        if last_turn_curr.turn_index != first_turn_next.turn_index:
            overlap_violations.append(
                f"Chunk {k} ends at turn {last_turn_curr.turn_index}, but Chunk {k+1} starts at turn {first_turn_next.turn_index}"
            )
            
    if overlap_violations:
        res.fail(f"1-turn overlap broken in multi-turn dialogue: {overlap_violations}")
        
    # Scenario B: Single long monologue turns (each turn >= 400 tokens)
    turns_b = [
        SpeakerTurn(
            speaker="Lenny Rachitsky",
            timestamp="00:00:00",
            text="Short question about strategy?",
            start_char=0,
            end_char=30,
            turn_start_char=0,
            turn_end_char=35,
            turn_index=0,
        ),
        SpeakerTurn(
            speaker="Guest",
            timestamp="00:00:10",
            text="Long answer sentence one. " + " ".join(["detailed content"] * 300) + ". End of turn.",
            start_char=40,
            end_char=2000,
            turn_start_char=35,
            turn_end_char=2000,
            turn_index=1,
        ),
        SpeakerTurn(
            speaker="Lenny Rachitsky",
            timestamp="00:05:00",
            text="Another long followup question. " + " ".join(["detailed followup"] * 300) + ". End.",
            start_char=2010,
            end_char=4000,
            turn_start_char=2000,
            turn_end_char=4000,
            turn_index=2,
        ),
    ]
    chunks_b = chunk_turns(turns_b, min_tokens=350, max_tokens=450)
    
    # In Scenario B, check if overlap exists between chunks
    overlaps_found = 0
    for k in range(len(chunks_b) - 1):
        c_curr = chunks_b[k]
        c_next = chunks_b[k + 1]
        shared = [t for t in c_curr.turns if t in c_next.turns]
        if shared:
            overlaps_found += 1
            
    if len(chunks_b) > 1 and overlaps_found == 0:
        res.warn(
            f"Zero overlap between chunks in long monologue scenario! Total chunks: {len(chunks_b)}, overlaps: 0"
        )
        
    return res


def test_unicode_and_special_characters() -> TestResult:
    """Test unicode encoding, emojis, CJK, zero-width spaces, and RTL."""
    res = TestResult("Unicode & Special Characters Stress", "Parser/Chunker")
    
    text = (
        "---\n"
        "title: \"Unicode Stress Test: 🚀 日本語 & العربية\"\n"
        "guest: \"Renée O'Connor 👩‍💻\"\n"
        "---\n\n"
        "**Lenny Rachitsky** (00:00:00):\n"
        "Let's test emojis 🎉, accents é à ü, and zero-width spaces \u200b here.\n\n"
        "**Renée O'Connor 👩‍💻** (00:00:15):\n"
        "In Tokyo (東京), we saw 100% growth! In Cairo (القاهرة), it was 80%. Here's an em-dash — and ellipsis…\n"
    )
    
    doc = parse_transcript_text(text, slug="unicode-test")
    if doc.guest != "Renée O'Connor 👩‍💻":
        res.fail(f"Guest unicode corrupted: '{doc.guest}'")
    if len(doc.turns) != 2:
        res.fail(f"Turns count mismatch: expected 2, got {len(doc.turns)}")
        return res
        
    # Check offset preservation on unicode
    turn0 = doc.turns[0]
    extracted0 = text[turn0.start_char : turn0.end_char]
    if extracted0 != turn0.text:
        res.fail(f"Turn 0 unicode offset drift: extracted '{extracted0}', expected '{turn0.text}'")
        
    turn1 = doc.turns[1]
    extracted1 = text[turn1.start_char : turn1.end_char]
    if extracted1 != turn1.text:
        res.fail(f"Turn 1 unicode offset drift: extracted '{extracted1}', expected '{turn1.text}'")
        
    chunks = chunk_document(doc, min_tokens=10, max_tokens=100)
    for c in chunks:
        if c.start_char >= c.end_char:
            res.fail(f"Chunk offsets inverted: start={c.start_char}, end={c.end_char}")
            
    return res


def test_real_corpus_invariants() -> TestResult:
    """Run all 50 real podcast transcripts through parser and chunker, verifying invariants."""
    res = TestResult("Real Corpus Invariants (All 50 Podcasts)", "Corpus")
    podcasts_dir = backend_dir.parent / "data" / "lenny-source" / "podcasts"
    if not podcasts_dir.exists():
        res.fail(f"Corpus directory not found: {podcasts_dir}")
        return res
        
    files = sorted(podcasts_dir.glob("*.md"))
    if len(files) != 50:
        res.fail(f"Expected 50 podcast files, found {len(files)}")
        return res
        
    total_turns = 0
    total_chunks = 0
    drift_count = 0
    overlap_breaks = 0
    terminal_punct_failures = 0
    
    for f in files:
        raw = f.read_text(encoding="utf-8")
        doc = parse_transcript_file(f)
        total_turns += len(doc.turns)
        
        # Verify turn offsets against raw file
        for turn in doc.turns:
            extracted = raw[turn.start_char : turn.end_char]
            if extracted != turn.text:
                drift_count += 1
                
        # Chunk document
        chunks = chunk_document(doc)
        total_chunks += len(chunks)
        
        # Verify chunk invariants
        for idx, chunk in enumerate(chunks):
            # Invariant 1: start < end
            if chunk.start_char >= chunk.end_char:
                res.fail(f"{f.name} chunk {idx}: start_char {chunk.start_char} >= end_char {chunk.end_char}")
                
            # Invariant 2: chunk ends with valid sentence punctuation
            last_char = chunk.text.strip()[-1]
            if last_char not in [".", "!", "?", '"', "'", "”", "’", "…"]:
                terminal_punct_failures += 1
                
        # Verify 1-turn overlap across consecutive chunks
        for idx in range(len(chunks) - 1):
            c_curr = chunks[idx]
            c_next = chunks[idx + 1]
            # When consecutive chunks have multiple turns each:
            # Does c_next contain c_curr.turns[-1]?
            if len(c_curr.turns) > 1 and len(c_next.turns) > 1:
                curr_last = c_curr.turns[-1]
                next_first = c_next.turns[0]
                if curr_last.turn_index != next_first.turn_index:
                    overlap_breaks += 1
                    
    if drift_count > 0:
        res.fail(f"Turn text vs raw_text offset drift detected in {drift_count} turns!")
    if overlap_breaks > 0:
        res.warn(f"Overlap discontinuities detected across {overlap_breaks} multi-turn chunk boundaries.")
    if terminal_punct_failures > 0:
        res.warn(f"Chunks ending without sentence punctuation: {terminal_punct_failures}")
        
    res.details = {
        "files_analyzed": len(files),
        "total_turns": total_turns,
        "total_chunks": total_chunks,
        "drift_count": drift_count,
        "overlap_breaks": overlap_breaks,
        "terminal_punct_failures": terminal_punct_failures,
    }
    return res


def run_all_stress_tests() -> list[TestResult]:
    """Execute all adversarial tests and print structured summary."""
    tests = [
        test_bom_handling,
        test_empty_and_whitespace_inputs,
        test_malformed_yaml_frontmatter,
        test_inverted_offsets_on_unfiltered_empty_turns,
        test_split_long_turn_duplicate_sentence_offset_bug,
        test_split_long_turn_identical_repeated_sentences,
        test_quote_sentence_splitting,
        test_abbreviation_protections,
        test_extreme_monologue_no_punctuation,
        test_one_turn_overlap_stability,
        test_unicode_and_special_characters,
        test_real_corpus_invariants,
    ]
    
    results = []
    print("=" * 80)
    print("STARTING ADVERSARIAL STRESS TEST SUITE: PARSER & CHUNKER")
    print("=" * 80)
    
    for t in tests:
        res = t()
        status = "PASS" if res.passed else "FAIL"
        print(f"[{status}] {res.category}: {res.name}")
        for f in res.failures:
            print(f"       -> FAILURE: {f}")
        for w in res.warnings:
            print(f"       -> WARNING: {w}")
        if res.details:
            print(f"       -> DETAILS: {res.details}")
        results.append(res)
        
    print("=" * 80)
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r.passed)
    failed_tests = total_tests - passed_tests
    print(f"SUMMARY: {passed_tests}/{total_tests} passed, {failed_tests} failed.")
    print("=" * 80)
    return results


if __name__ == "__main__":
    results = run_all_stress_tests()
    failed = [r for r in results if not r.passed]
    if failed:
        sys.exit(1)
    sys.exit(0)
