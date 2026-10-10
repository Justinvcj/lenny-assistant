"""Empirical Invariant Challenger Suite for Milestone 1 (P3b - Parser & Chunker).

Adversarially audits all 50 real podcast transcripts against strict invariants:
1. Verbatim turn slicing: raw_text[turn.start_char : turn.end_char] == turn.text.
2. Terminal punctuation: No chunk ends mid-sentence.
3. 1-turn overlap: Consecutive chunks in each document share exactly 1 turn overlap.
4. Token bound: 0 chunks exceed 600 tokens.
5. Primary speaker attribution accuracy.
"""

from collections import Counter
from pathlib import Path
import re
from typing import List, Tuple

import pytest

from app.rag.chunking import (
    ChunkDraft,
    chunk_document,
    determine_primary_speaker,
    estimate_tokens,
    split_long_turn,
)
from app.rag.parser import (
    ParsedDocument,
    parse_transcript_file,
)


def get_podcast_files() -> List[Path]:
    project_root = Path(__file__).resolve().parent.parent.parent
    podcasts_dir = project_root / "data" / "lenny-source" / "podcasts"
    files = sorted(podcasts_dir.glob("*.md"))
    assert len(files) == 50, f"Expected exactly 50 podcast transcripts, found {len(files)}"
    return files


@pytest.fixture(scope="module")
def parsed_corpus() -> List[Tuple[Path, ParsedDocument, List[ChunkDraft]]]:
    files = get_podcast_files()
    corpus = []
    for f in files:
        doc = parse_transcript_file(f)
        chunks = chunk_document(doc)
        corpus.append((f, doc, chunks))
    return corpus


def test_corpus_size_and_turns_count(parsed_corpus):
    """Verify corpus-wide document, turn, and chunk counts."""
    total_turns = sum(len(doc.turns) for _, doc, _ in parsed_corpus)
    total_empty_dropped = sum(doc.metadata.get("empty_turns_dropped", 0) for _, doc, _ in parsed_corpus)
    total_chunks = sum(len(chunks) for _, _, chunks in parsed_corpus)

    print(f"\n[CORPUS AUDIT] Files: {len(parsed_corpus)}, Turns: {total_turns}, Dropped Empty: {total_empty_dropped}, Chunks: {total_chunks}")
    assert len(parsed_corpus) == 50
    assert total_turns == 12034, f"Expected 12034 valid turns, got {total_turns}"
    assert total_empty_dropped == 55, f"Expected 55 empty turns dropped, got {total_empty_dropped}"
    assert total_chunks == 3899, f"Expected 3899 chunks, got {total_chunks}"


def test_invariant_1_turn_slicing_verbatim(parsed_corpus):
    """Assert raw_text[turn.start_char : turn.end_char] == turn.text for all 12,034 turns."""
    mismatches = []
    total_turns_checked = 0

    for file_path, doc, _ in parsed_corpus:
        raw_text = doc.raw_text
        for turn_idx, turn in enumerate(doc.turns):
            total_turns_checked += 1
            sliced = raw_text[turn.start_char : turn.end_char]
            if sliced != turn.text:
                mismatches.append({
                    "file": file_path.name,
                    "turn_idx": turn_idx,
                    "speaker": turn.speaker,
                    "expected_len": len(turn.text),
                    "sliced_len": len(sliced),
                    "expected_preview": turn.text[:50],
                    "sliced_preview": sliced[:50],
                })

            # Check bounding consistency
            assert turn.turn_start_char <= turn.start_char, f"turn_start_char > start_char in {file_path.name}:{turn_idx}"
            assert turn.end_char <= turn.turn_end_char, f"end_char > turn_end_char in {file_path.name}:{turn_idx}"
            assert turn.start_char < turn.end_char, f"start_char >= end_char in {file_path.name}:{turn_idx}"

    print(f"\n[INVARIANT 1 AUDIT] Checked {total_turns_checked} turns. Slicing mismatches: {len(mismatches)}")
    assert len(mismatches) == 0, f"Found {len(mismatches)} turn slicing mismatches: {mismatches[:5]}"


def test_invariant_2_terminal_punctuation_and_mid_sentence_cuts(parsed_corpus):
    """Assert that chunker never cuts mid-sentence, and audit trailing punctuation."""
    # Step 1: Verify split_long_turn sub-turns never end mid-sentence
    subturn_cuts = []
    for _, doc, _ in parsed_corpus:
        for turn in doc.turns:
            if estimate_tokens(turn.text) > 450:
                subs = split_long_turn(turn, max_tokens=400)
                for sub in subs:
                    stripped = sub.text.strip()
                    # Subturns must terminate at grammatical sentence punctuation
                    if not re.search(r'[.!?]["”’\')\]]?$', stripped):
                        subturn_cuts.append(stripped[-50:])

    assert len(subturn_cuts) == 0, f"Found {len(subturn_cuts)} mid-sentence cuts in split_long_turn: {subturn_cuts}"

    # Step 2: Audit all 3,888 chunks for terminal character patterns
    endings = Counter()
    non_standard_chunks = []
    for file_path, doc, chunks in parsed_corpus:
        for chunk in chunks:
            text = chunk.text.strip()
            last_char = text[-1] if text else ""
            endings[last_char] += 1

            # Standard terminal punctuation: . ! ? or closing quotes " ” ’ '
            if not re.search(r'([.!?]["”’\')\]]?|["”’\')\]])$', text):
                # Check whether this chunk's ending is a verbatim turn ending in doc.turns
                last_turn = chunk.turns[-1]
                is_verbatim_turn_end = any(
                    t.text == last_turn.text or t.text.endswith(last_turn.text) or t.end_char == last_turn.end_char
                    for t in doc.turns
                )
                non_standard_chunks.append({
                    "file": file_path.name,
                    "chunk_index": chunk.chunk_index,
                    "last_char": repr(last_char),
                    "last_30": repr(text[-30:]),
                    "is_verbatim_raw_turn": is_verbatim_turn_end,
                })

    print(f"\n[INVARIANT 2 AUDIT] Terminal character distribution: {dict(endings)}")
    print(f"Non-standard ending chunks (e.g. hyphen interruptions, transcript trailing words): {len(non_standard_chunks)}")

    # All non-standard endings must originate verbatim from raw transcript speaker turns (0 introduced by chunker)
    chunker_introduced_cuts = [c for c in non_standard_chunks if not c["is_verbatim_raw_turn"]]
    assert len(chunker_introduced_cuts) == 0, (
        f"Chunker introduced {len(chunker_introduced_cuts)} mid-sentence cuts: {chunker_introduced_cuts}"
    )


def test_invariant_3_consecutive_chunk_one_turn_overlap(parsed_corpus):
    """Audit 1-turn overlap across consecutive chunks.

    Exposes the 95 zero-overlap defect where chunk_end == i causes next_i = i + 1,
    skipping overlap and creating 76 redundant subset chunks.
    """
    overlap_zero_violations = []
    overlap_gt1_violations = []
    redundant_subset_chunks = []
    total_adj_pairs_checked = 0

    for file_path, _, chunks in parsed_corpus:
        for i in range(len(chunks) - 1):
            total_adj_pairs_checked += 1
            c1 = chunks[i]
            c2 = chunks[i + 1]

            c1_turn_starts = set(t.start_char for t in c1.turns)
            c2_turn_starts = set(t.start_char for t in c2.turns)
            overlap_turns = c1_turn_starts.intersection(c2_turn_starts)

            if len(overlap_turns) == 0:
                overlap_zero_violations.append({
                    "file": file_path.name,
                    "chunk_i": c1.chunk_index,
                    "chunk_next": c2.chunk_index,
                    "c1_turns_count": len(c1.turns),
                    "c2_turns_count": len(c2.turns),
                    "c1_tokens": c1.token_count,
                    "c2_tokens": c2.token_count,
                })

                if i > 0:
                    c0 = chunks[i - 1]
                    c0_turn_starts = set(t.start_char for t in c0.turns)
                    if c1_turn_starts.issubset(c0_turn_starts):
                        redundant_subset_chunks.append({
                            "file": file_path.name,
                            "chunk_index": c1.chunk_index,
                            "tokens": c1.token_count,
                        })

            elif len(overlap_turns) > 1:
                overlap_gt1_violations.append({
                    "file": file_path.name,
                    "chunk_i": c1.chunk_index,
                    "chunk_next": c2.chunk_index,
                    "overlap_count": len(overlap_turns),
                })

    print(f"\n[INVARIANT 3 AUDIT] Checked {total_adj_pairs_checked} adjacent chunk pairs across 50 documents.")
    print(f"  Exact 1-turn overlap pairs: {total_adj_pairs_checked - len(overlap_zero_violations) - len(overlap_gt1_violations)}")
    print(f"  Zero-overlap violations:    {len(overlap_zero_violations)} (across {len(set(v['file'] for v in overlap_zero_violations))} files)")
    print(f"  Redundant subset chunks:    {len(redundant_subset_chunks)}")
    print(f"  Overlap > 1 violations:     {len(overlap_gt1_violations)}")

    # CHALLENGER ASSERTION:
    # Consecutive chunks MUST share exactly 1 turn overlap.
    # If len(overlap_zero_violations) > 0, the chunker fails the 1-turn overlap invariant.
    assert len(overlap_zero_violations) == 0, (
        f"CRITICAL INVARIANT FAILURE: Found {len(overlap_zero_violations)} consecutive chunk pairs "
        f"with ZERO overlap across {len(set(v['file'] for v in overlap_zero_violations))} documents! "
        f"Sample violations: {overlap_zero_violations[:5]}"
    )


def test_invariant_4_token_counts_within_bounds(parsed_corpus):
    """Assert that 0 chunks exceed 600 tokens and token counts are non-zero."""
    total_chunks_checked = 0
    exceeding_chunks = []
    min_tokens = float("inf")
    max_tokens = float("-inf")
    zero_token_chunks = []

    for file_path, _, chunks in parsed_corpus:
        for chunk in chunks:
            total_chunks_checked += 1
            tok = chunk.token_count
            min_tokens = min(min_tokens, tok)
            max_tokens = max(max_tokens, tok)

            if tok > 600:
                exceeding_chunks.append({
                    "file": file_path.name,
                    "chunk_index": chunk.chunk_index,
                    "tokens": tok,
                })

            if tok <= 0:
                zero_token_chunks.append({
                    "file": file_path.name,
                    "chunk_index": chunk.chunk_index,
                    "tokens": tok,
                })

    print(f"\n[INVARIANT 4 AUDIT] Checked {total_chunks_checked} chunks. Min: {min_tokens}, Max: {max_tokens}, Exceeding 600: {len(exceeding_chunks)}")
    assert len(zero_token_chunks) == 0, f"Found {len(zero_token_chunks)} chunks with <= 0 tokens"
    assert len(exceeding_chunks) == 0, f"Found {len(exceeding_chunks)} chunks > 600 tokens: {exceeding_chunks[:5]}"
    assert max_tokens <= 600, f"Max token count {max_tokens} exceeds 600 ceiling"


def test_invariant_5_primary_speaker_attribution_accuracy(parsed_corpus):
    """Assert primary speaker attribution is non-empty, in the chunk turns, and matches max tokens."""
    total_chunks_checked = 0
    speaker_violations = []

    for file_path, _, chunks in parsed_corpus:
        for chunk in chunks:
            total_chunks_checked += 1
            calculated_speaker = determine_primary_speaker(chunk.turns)
            turn_speakers = set(t.speaker for t in chunk.turns)

            if chunk.speaker != calculated_speaker or chunk.speaker not in turn_speakers:
                speaker_violations.append({
                    "file": file_path.name,
                    "chunk_index": chunk.chunk_index,
                    "chunk_speaker": chunk.speaker,
                    "calculated": calculated_speaker,
                    "turn_speakers": list(turn_speakers),
                })

    print(f"\n[INVARIANT 5 AUDIT] Checked {total_chunks_checked} chunks. Attribution violations: {len(speaker_violations)}")
    assert len(speaker_violations) == 0, f"Found {len(speaker_violations)} speaker attribution violations: {speaker_violations[:5]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
