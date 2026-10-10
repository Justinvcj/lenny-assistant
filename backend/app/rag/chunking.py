"""Speaker-turn aware transcript chunking engine for Lenny Growth Assistant.

Splits dialogue turns into ~350-450 token chunks with 1-turn overlap,
sentence boundary preservation, primary speaker detection, and exact
character offset tracking.
"""

from dataclasses import dataclass, field
import re
from typing import Dict, List, Optional
import uuid

from app.models import Chunk
from app.rag.parser import ParsedDocument, SpeakerTurn

# Negative lookbehinds for common abbreviations & honorifics (each pattern has fixed character length)
_ABBREVIATIONS = (
    r"(?<!Dr\.)(?<!Mr\.)(?<!Ms\.)(?<!Mrs\.)(?<!Prof\.)"
    r"(?<!vs\.)(?<!i\.e\.)(?<!I\.e\.)(?<!e\.g\.)(?<!E\.g\.)(?<!etc\.)"
    r"(?<!Jr\.)(?<!Sr\.)(?<!St\.)(?<!U\.S\.)(?<!Inc\.)(?<!Corp\.)(?<!Ltd\.)"
)
# Sentence boundary regex supporting:
# 1) Standard punctuation [.!?] not preceded by abbreviation
# 2) Punctuation inside closing quotes [.!?]["'”’]
# Followed by whitespace, and lookahead for optional opening quote and capitalized token
ABBREVIATION_SENTENCE_REGEX = re.compile(
    rf"(?:{_ABBREVIATIONS}(?<=[.!?])|(?<=[.!?][\"'”’]))\s+(?=[\"'“‘]?[A-Z0-9])"
)


@dataclass
class ChunkDraft:
    """In-memory representation of a chunk prior to embedding and DB persistence."""

    chunk_index: int
    text: str
    token_count: int
    speaker: str
    start_char: int
    end_char: int
    document_id: Optional[uuid.UUID] = None
    turns: List[SpeakerTurn] = field(default_factory=list)

    def to_chunk_model(
        self,
        document_id: Optional[uuid.UUID] = None,
        embedding: Optional[List[float]] = None,
        chunk_id: Optional[uuid.UUID] = None,
    ) -> Chunk:
        """Convert ChunkDraft to SQLAlchemy Chunk model."""
        target_doc_id = document_id or self.document_id
        if target_doc_id is None:
            raise ValueError("document_id must be provided to create a Chunk model instance")

        return Chunk(
            id=chunk_id or uuid.uuid4(),
            document_id=target_doc_id,
            chunk_index=self.chunk_index,
            text=self.text,
            token_count=self.token_count,
            speaker=self.speaker,
            start_char=self.start_char,
            end_char=self.end_char,
            embedding=embedding if embedding is not None else [],
        )


# Alias for compatibility
ChunkResult = ChunkDraft


def estimate_tokens(text: str) -> int:
    """Estimate token count using the documented word_count * 1.3 approximation.

    Args:
        text: Input text string.

    Returns:
        Estimated integer token count (0 for empty or whitespace-only text).
    """
    if not text or not text.strip():
        return 0
    words = len(text.strip().split())
    return int(round(words * 1.3))


def split_sentences(text: str) -> List[str]:
    """Split text into sentences while protecting abbreviations and honorifics.

    Args:
        text: Paragraph or spoken dialogue string.

    Returns:
        List of non-empty sentence strings.
    """
    if not text or not text.strip():
        return []
    sentences = ABBREVIATION_SENTENCE_REGEX.split(text.strip())
    return [s.strip() for s in sentences if s.strip()]


def _subdivide_oversized_sentence(sent: str, max_tokens: int = 400) -> List[str]:
    """Subdivide an unpunctuated run-on sentence exceeding max_tokens into word slices."""
    words_matches = list(re.finditer(r"\S+", sent))
    target_words = max(50, int(max_tokens / 1.3))
    if len(words_matches) <= target_words:
        return [sent]

    fragments: List[str] = []
    for i in range(0, len(words_matches), target_words):
        chunk_matches = words_matches[i : i + target_words]
        frag_start = chunk_matches[0].start()
        frag_end = chunk_matches[-1].end()
        fragments.append(sent[frag_start:frag_end])
    return fragments


def split_long_turn(turn: SpeakerTurn, max_tokens: int = 400) -> List[SpeakerTurn]:
    """Split a single speaker turn exceeding the target token limit into sub-turns.

    Preserves sentence boundaries and computes exact character offsets within the turn.

    Args:
        turn: Original SpeakerTurn exceeding max_tokens.
        max_tokens: Target ceiling for sub-turns (default 400).

    Returns:
        List of smaller SpeakerTurn instances.
    """
    raw_sentences = split_sentences(turn.text)
    if not raw_sentences:
        return []

    # Flatten run-on sentences if any individual sentence exceeds max_tokens
    sentences: List[str] = []
    for s in raw_sentences:
        if estimate_tokens(s) > max_tokens:
            sentences.extend(_subdivide_oversized_sentence(s, max_tokens=max_tokens))
        else:
            sentences.append(s)

    # Map each sentence sequentially to its exact character offset within turn.text
    sentence_spans = []
    search_pos = 0
    for s in sentences:
        s_start = turn.text.find(s, search_pos)
        if s_start == -1:
            s_start = search_pos
        s_end = s_start + len(s)
        sentence_spans.append((s, s_start, s_end))
        search_pos = s_end

    sub_turns: List[SpeakerTurn] = []
    curr_spans = []
    curr_tokens = 0

    for span in sentence_spans:
        s, s_start, s_end = span
        s_tokens = estimate_tokens(s)
        if curr_tokens + s_tokens > max_tokens and curr_spans:
            sub_text = " ".join(sp[0] for sp in curr_spans)
            sub_start_char = turn.start_char + curr_spans[0][1]
            sub_end_char = turn.start_char + curr_spans[-1][2]

            sub_turns.append(
                SpeakerTurn(
                    speaker=turn.speaker,
                    timestamp=turn.timestamp,
                    text=sub_text,
                    start_char=sub_start_char,
                    end_char=sub_end_char,
                    turn_start_char=turn.turn_start_char if len(sub_turns) == 0 else sub_start_char,
                    turn_end_char=sub_end_char,
                    turn_index=turn.turn_index,
                )
            )
            curr_spans = [span]
            curr_tokens = s_tokens
        else:
            curr_spans.append(span)
            curr_tokens += s_tokens

    if curr_spans:
        sub_text = " ".join(sp[0] for sp in curr_spans)
        sub_start_char = turn.start_char + curr_spans[0][1]
        sub_end_char = turn.start_char + curr_spans[-1][2]
        sub_turns.append(
            SpeakerTurn(
                speaker=turn.speaker,
                timestamp=turn.timestamp,
                text=sub_text,
                start_char=sub_start_char,
                end_char=sub_end_char,
                turn_start_char=turn.turn_start_char if len(sub_turns) == 0 else sub_start_char,
                turn_end_char=turn.turn_end_char,
                turn_index=turn.turn_index,
            )
        )

    return sub_turns


def format_chunk_text(turns: List[SpeakerTurn]) -> str:
    """Format dialogue turns into a consistent chunk text string with speaker headers.

    Args:
        turns: List of turns included in the chunk.

    Returns:
        Formatted multi-turn markdown dialogue.
    """
    formatted_parts: List[str] = []
    for turn in turns:
        if turn.timestamp:
            header = f"**{turn.speaker}** ({turn.timestamp}):"
        else:
            header = f"**{turn.speaker}**:"
        formatted_parts.append(f"{header}\n{turn.text}")
    return "\n\n".join(formatted_parts)


def determine_primary_speaker(turns: List[SpeakerTurn]) -> str:
    """Identify the primary speaker in a chunk based on total spoken tokens.

    Args:
        turns: List of turns included in the chunk.

    Returns:
        Speaker name who contributed the most tokens to this chunk.
    """
    speaker_tokens: Dict[str, int] = {}
    for turn in turns:
        tokens = estimate_tokens(turn.text)
        speaker_tokens[turn.speaker] = speaker_tokens.get(turn.speaker, 0) + tokens
    if not speaker_tokens:
        return "Unknown"
    return max(speaker_tokens.items(), key=lambda item: item[1])[0]


def chunk_turns(
    turns: List[SpeakerTurn],
    document_id: Optional[uuid.UUID] = None,
    min_tokens: int = 350,
    max_tokens: int = 450,
    target_tokens: Optional[int] = None,
) -> List[ChunkDraft]:
    """Chunk a sequence of speaker turns into overlapping, speaker-turn aware chunks.

    Maintains strict 1-turn overlap across all adjacent chunk pairs, eliminates
    redundant single-turn subset chunks, and enforces token limits.

    Args:
        turns: Ordered list of parsed SpeakerTurn objects.
        document_id: Optional document UUID to attach to drafts.
        min_tokens: Lower bound of preferred chunk token range (default 350).
        max_tokens: Upper bound of preferred chunk token range (default 450).
        target_tokens: Desired center of chunk token distribution (default 400).

    Returns:
        List of ChunkDraft objects.
    """
    if target_tokens is None:
        target_tokens = int(round((min_tokens + max_tokens) / 2))

    # Step 1: Filter empty turns (sponsor reads stripped from transcripts)
    valid_turns = [t for t in turns if t.text and t.text.strip()]
    if not valid_turns:
        return []

    # Step 2: Split any single turns exceeding turn_split_threshold into sentence sub-turns.
    # Dynamically derived from min_tokens / target_tokens to support custom ranges.
    turn_split_threshold = int(min_tokens * 0.85)  # e.g., ~297 tokens for min_tokens=350
    subturn_max = int(target_tokens * 0.62)        # e.g., ~248 tokens for target_tokens=400

    normalized_turns: List[SpeakerTurn] = []
    for turn in valid_turns:
        turn_tokens = estimate_tokens(turn.text)
        if turn_tokens > turn_split_threshold:
            normalized_turns.extend(split_long_turn(turn, max_tokens=subturn_max))
        else:
            normalized_turns.append(turn)

    chunks: List[ChunkDraft] = []
    i = 0
    n = len(normalized_turns)

    overshoot_floor = int(min_tokens * 0.7)
    overshoot_ceiling = max(max_tokens, int(max_tokens * 1.15))
    tail_threshold = max(20, min(150, int(min_tokens * 0.45)))
    tail_merge_ceiling = max(500, int(max_tokens * 1.25))

    # Step 3: Sliding window accumulation with strict 1-turn overlap
    while i < n:
        tok_sum = estimate_tokens(normalized_turns[i].text)
        j = i + 1

        # Strict forward progress & 1-turn overlap guarantee:
        # Every chunk in a multi-turn sequence must contain at least turn i + 1
        # to ensure it advances beyond the overlap turn and does not form a redundant single-turn subset.
        if j < n:
            tok_sum += estimate_tokens(normalized_turns[j].text)
            j += 1

        while j < n:
            next_tokens = estimate_tokens(normalized_turns[j].text)
            if tok_sum + next_tokens <= max_tokens:
                tok_sum += next_tokens
                j += 1
            else:
                # If chunk is still small (< overshoot_floor), permit slight overshoot up to overshoot_ceiling
                if tok_sum < overshoot_floor and (tok_sum + next_tokens <= overshoot_ceiling):
                    tok_sum += next_tokens
                    j += 1
                break

        chunk_end = j - 1
        chunk_turns_list = normalized_turns[i:j]

        # Step 4: Tail handling (merge small tail turn into previous chunk if <= tail_merge_ceiling)
        if chunk_end == n - 1 and len(chunks) > 0 and tok_sum < tail_threshold:
            # Exclude overlapping turn already in previous chunk to prevent duplicate dialogue
            additional_turns = [t for t in chunk_turns_list if t is not chunks[-1].turns[-1]]
            additional_tokens = sum(estimate_tokens(t.text) for t in additional_turns)
            if chunks[-1].token_count + additional_tokens <= tail_merge_ceiling:
                merged_turns = chunks[-1].turns + additional_turns
                merged_text = format_chunk_text(merged_turns)
                chunks[-1].turns = merged_turns
                chunks[-1].text = merged_text
                chunks[-1].token_count = estimate_tokens(merged_text)
                chunks[-1].speaker = determine_primary_speaker(merged_turns)
                chunks[-1].end_char = chunk_turns_list[-1].turn_end_char
                break

        formatted_text = format_chunk_text(chunk_turns_list)
        chunk_token_count = estimate_tokens(formatted_text)
        primary_speaker = determine_primary_speaker(chunk_turns_list)

        chunks.append(
            ChunkDraft(
                chunk_index=len(chunks),
                text=formatted_text,
                token_count=chunk_token_count,
                speaker=primary_speaker,
                start_char=chunk_turns_list[0].turn_start_char,
                end_char=chunk_turns_list[-1].turn_end_char,
                document_id=document_id,
                turns=chunk_turns_list,
            )
        )

        # Reached the end of document
        if chunk_end >= n - 1:
            break

        # 1-turn overlap: next chunk begins at the last turn of the current chunk
        # Because j >= i + 2 when j < n, chunk_end is strictly greater than i (chunk_end >= i + 1 > i)
        i = chunk_end

    # Step 5: Defense-in-depth filter for any redundant subset chunks
    pruned_chunks: List[ChunkDraft] = []
    for c in chunks:
        if pruned_chunks:
            prev_turn_starts = set(t.start_char for t in pruned_chunks[-1].turns)
            curr_turn_starts = set(t.start_char for t in c.turns)
            if curr_turn_starts.issubset(prev_turn_starts):
                continue
        pruned_chunks.append(c)

    for idx, c in enumerate(pruned_chunks):
        c.chunk_index = idx

    return pruned_chunks


def chunk_document(
    doc: ParsedDocument,
    document_id: Optional[uuid.UUID] = None,
    min_tokens: int = 350,
    max_tokens: int = 450,
) -> List[ChunkDraft]:
    """Convenience wrapper to chunk a ParsedDocument."""
    return chunk_turns(
        turns=doc.turns,
        document_id=document_id,
        min_tokens=min_tokens,
        max_tokens=max_tokens,
    )


def chunk_transcript(
    doc: ParsedDocument,
    document_id: Optional[uuid.UUID] = None,
    target_min: int = 350,
    target_max: int = 450,
) -> List[ChunkDraft]:
    """Alias for chunk_document supporting target_min/target_max parameter names."""
    return chunk_turns(
        turns=doc.turns,
        document_id=document_id,
        min_tokens=target_min,
        max_tokens=target_max,
    )
