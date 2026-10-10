"""Empirical Invariant Challenger Suite for Milestone 1 (P3b - Parser & Chunker).

Adversarially audits all 50 real podcast transcripts against strict invariants:
1. Verbatim turn slicing: raw_text[turn.start_char : turn.end_char] == turn.text.
2. Terminal punctuation: No chunk ends mid-sentence.
3. 1-turn overlap: Consecutive chunks in each document share exactly 1 turn overlap.
4. Token bound: 0 chunks exceed 600 tokens.
5. Primary speaker attribution accuracy.
"""

from pathlib import Path
import re
import sys
from typing import Dict, List, Tuple

import pytest

from app.rag.chunking import (
    ChunkDraft,
    chunk_document,
    determine_primary_speaker,
    estimate_tokens,
)
from app.rag.parser import (
    ParsedDocument,
    SpeakerTurn,
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
    total_turns = sum(len(doc.turns) for _, doc, _ in parsed_corpus)
    total_empty_dropped = sum(doc.metadata.get("empty_turns_dropped", 0) for _, doc, _ in parsed_corpus)
    total_chunks = sum(len(chunks) for _, _, chunks in parsed_corpus)

    print(f"\n[CORPUS AUDIT] Files: {len(parsed_corpus)}, Turns: {total_turns}, Dropped Empty: {total_empty_dropped}, Chunks: {total_chunks}")
    assert len(parsed_corpus) == 50
    assert total_turns == 12034, f"Expected 12034 valid turns, got {total_turns}"
    assert total_empty_dropped == 55, f"Expected 55 empty turns dropped, got {total_empty_dropped}"
    assert total_chunks == 3888, f"Expected 3888 chunks, got {total_chunks}"


def test_invariant_1_turn_slicing_verbatim(parsed_corpus):
    """Assert raw_text[turn.start_char : turn.end_char] == turn.text for all turns."""
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

    print(f"\n[INVARIANT 1 AUDIT] Checked {total_turns_checked} turns. Mismatches: {len(mismatches)}")
    assert len(mismatches) == 0, f"Found {len(mismatches)} turn slicing mismatches: {mismatches[:5]}"


def test_invariant_2_terminal_punctuation_no_mid_sentence_cuts(parsed_corpus):
    """Assert that no chunk ends mid-sentence (check terminal punctuation)."""
    # Acceptable terminal punctuation characters
    # Includes standard terminal punctuation (. ! ?), closing quotes (" ” ’ '), closing parens/brackets, ellipses (… or ...), em-dash (— or --)
    TERMINAL_PUNCT_REGEX = re.compile(r'([.!?…—]|\.\.\.|["”’\')\]]+)$')

    non_conforming_chunks = []
    total_chunks_checked = 0
    terminal_char_counts: Dict[str, int] = {}

    for file_path, _, chunks in parsed_corpus:
        for chunk in chunks:
            total_chunks_checked += 1
            text = chunk.text.strip()
            last_char = text[-1] if text else ""
            last_3 = text[-3:] if len(text) >= 3 else text

            terminal_char_counts[last_char] = terminal_char_counts.get(last_char, 0) + 1

            if not TERMINAL_PUNCT_REGEX.search(text):
                non_conforming_chunks.append({
                    "file": file_path.name,
                    "chunk_index": chunk.chunk_index,
                    "speaker": chunk.speaker,
                    "last_char": repr(last_char),
                    "last_30_chars": repr(text[-30:]),
                })

    print(f"\n[INVARIANT 2 AUDIT] Checked {total_chunks_checked} chunks. Non-conforming: {len(non_conforming_chunks)}")
    print(f"Terminal char distribution: {terminal_char_counts}")

    if non_conforming_chunks:
        print("Sample non-conforming chunks:")
        for nc in non_conforming_chunks[:10]:
            print(f"  {nc['file']} chunk {nc['chunk_index']}: ending with {nc['last_char']} in {nc['last_30_chars']}")

    assert len(non_conforming_chunks) == 0, (
        f"Found {len(non_conforming_chunks)} chunks ending without terminal punctuation: {non_conforming_chunks[:5]}"
    )


def test_invariant_3_consecutive_chunk_one_turn_overlap(parsed_corpus):
    """Assert every pair of adjacent chunks shares exactly 1 turn overlap."""
    overlap_violations = []
    total_adj_pairs_checked = 0

    for file_path, _, chunks in parsed_corpus:
        for i in range(len(chunks) - 1):
            total_adj_pairs_checked += 1
            c1 = chunks[i]
            c2 = chunks[i + 1]

            # Compare turn identity
            # The last turn of c1 must match the first turn of c2
            last_turn_c1 = c1.turns[-1]
            first_turn_c2 = c2.turns[0]

            match_by_object = (last_turn_c1 is first_turn_c2)
            match_by_data = (
                last_turn_c1.start_char == first_turn_c2.start_char
                and last_turn_c1.end_char == first_turn_c2.end_char
                and last_turn_c1.speaker == first_turn_c2.speaker
                and last_turn_c1.text == first_turn_c2.text
            )

            # Check overlap count between c1.turns and c2.turns
            # How many turns in c1 are also in c2?
            c1_turn_starts = set(t.start_char for t in c1.turns)
            c2_turn_starts = set(t.start_char for t in c2.turns)
            overlap_turns = c1_turn_starts.intersection(c2_turn_starts)

            if not match_by_data or len(overlap_turns) != 1:
                overlap_violations.append({
                    "file": file_path.name,
                    "chunk_i": c1.chunk_index,
                    "chunk_next": c2.chunk_index,
                    "match_by_data": match_by_data,
                    "overlap_count": len(overlap_turns),
                    "c1_last_start": last_turn_c1.start_char,
                    "c2_first_start": first_turn_c2.start_char,
                })

    print(f"\n[INVARIANT 3 AUDIT] Checked {total_adj_pairs_checked} adjacent chunk pairs. Violations: {len(overlap_violations)}")
    if overlap_violations:
        print("Sample overlap violations:")
        for ov in overlap_violations[:10]:
            print(f"  {ov['file']} chunks {ov['chunk_i']} -> {ov['chunk_next']}: overlap count={ov['overlap_count']}, match_by_data={ov['match_by_data']}")

    assert len(overlap_violations) == 0, f"Found {len(overlap_violations)} overlap violations: {overlap_violations[:5]}"


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

    print(f"\n[INVARIANT 4 AUDIT] Checked {total_chunks_checked} chunks. Min tokens: {min_tokens}, Max tokens: {max_tokens}, Exceeding 600: {len(exceeding_chunks)}")
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
