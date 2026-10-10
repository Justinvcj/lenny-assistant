"""Transcript parsing engine for Lenny Growth Assistant.

Extracts YAML frontmatter, deterministic SHA-256 content hashes,
and ordered speaker turns with exact character offsets.
"""

from dataclasses import dataclass
from datetime import date
import hashlib
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import uuid
import yaml

from app.models import Document

# Strict regex requiring parenthesized timestamp:
# prevents matching bold markdown titles like '**Area 51, An Uncensored History**:'
SPEAKER_TURN_REGEX = re.compile(r"^\*\*([^*]+)\*\*\s*\(([^)]+)\):\s*", re.MULTILINE)
FRONTMATTER_REGEX = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class SpeakerTurn:
    """Represents a single spoken utterance in a transcript."""

    speaker: str
    timestamp: str  # e.g. "00:00:00"
    text: str  # Spoken content, stripped
    start_char: int  # Start of spoken text in raw file
    end_char: int  # End of spoken text in raw file
    turn_start_char: int  # Start of '**Speaker** (timestamp):' in raw file
    turn_end_char: int  # End of entire turn before next turn header
    turn_index: int  # 0-based sequence index within document


@dataclass
class ParsedDocument:
    """Represents a fully parsed transcript document with metadata and turns."""

    slug: str
    title: str
    guest: Optional[str]
    published_at: Optional[date]
    source_path: str
    content_hash: str
    metadata: Dict[str, Any]
    turns: List[SpeakerTurn]
    raw_text: str

    def to_document_model(self, doc_id: Optional[uuid.UUID] = None) -> Document:
        """Convert to SQLAlchemy Document model."""
        return Document(
            id=doc_id or uuid.uuid4(),
            slug=self.slug,
            title=self.title,
            guest=self.guest,
            published_at=self.published_at,
            source_path=self.source_path,
            content_hash=self.content_hash,
            metadata_=self.metadata,
        )


# Alias for backward-compatibility with alternative naming
TranscriptDocument = ParsedDocument


def compute_content_hash(content: str | bytes) -> str:
    """Compute deterministic SHA-256 hash with CRLF->LF normalization."""
    if isinstance(content, str):
        normalized = content.replace("\r\n", "\n").encode("utf-8")
    else:
        normalized = content.replace(b"\r\n", b"\n")
    return hashlib.sha256(normalized).hexdigest()


def extract_frontmatter(raw_text: str) -> tuple[Dict[str, Any], int]:
    """Extract YAML frontmatter and character index where body begins.

    Returns:
        tuple of (metadata_dict, body_start_char_offset)
    """
    fm_match = FRONTMATTER_REGEX.match(raw_text)
    if not fm_match:
        return {}, 0

    fm_raw = fm_match.group(1)
    body_start = fm_match.end()
    try:
        data = yaml.safe_load(fm_raw)
        return data if isinstance(data, dict) else {}, body_start
    except Exception:
        return {}, body_start


def extract_speaker_turns(
    raw_text: str,
    body_start: int = 0,
    filter_empty: bool = True,
    normalize_host: bool = True,
) -> tuple[List[SpeakerTurn], int]:
    """Extract ordered speaker turns with verified character offsets.

    Args:
        raw_text: Complete file text (including frontmatter).
        body_start: Character offset where dialogue begins.
        filter_empty: If True, drops turns with empty text (e.g. sponsor breaks).
        normalize_host: If True, converts "Lenny" to "Lenny Rachitsky".

    Returns:
        tuple of (turns_list, dropped_empty_count)
    """
    matches = list(SPEAKER_TURN_REGEX.finditer(raw_text, pos=body_start))
    turns: List[SpeakerTurn] = []
    dropped_empty = 0

    for i, match in enumerate(matches):
        speaker = match.group(1).strip()
        timestamp = match.group(2).strip()

        if normalize_host and speaker == "Lenny":
            speaker = "Lenny Rachitsky"

        turn_start_char = match.start()
        header_end = match.end()
        turn_end_char = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)

        segment = raw_text[header_end:turn_end_char]
        text = segment.strip()

        if not text:
            if filter_empty:
                dropped_empty += 1
                continue

        leading_ws = len(segment) - len(segment.lstrip())
        trailing_ws = len(segment) - len(segment.rstrip())
        text_start_char = header_end + leading_ws
        text_end_char = turn_end_char - trailing_ws

        turn = SpeakerTurn(
            speaker=speaker,
            timestamp=timestamp,
            text=text,
            start_char=text_start_char,
            end_char=text_end_char,
            turn_start_char=turn_start_char,
            turn_end_char=turn_end_char,
            turn_index=len(turns),
        )
        turns.append(turn)

    return turns, dropped_empty


def parse_transcript_text(
    raw_text: str,
    source_path: str = "",
    slug: Optional[str] = None,
) -> ParsedDocument:
    """Parse transcript from in-memory string content."""
    fm, body_start = extract_frontmatter(raw_text)
    content_hash = compute_content_hash(raw_text)

    derived_slug = slug
    if not derived_slug:
        if source_path:
            derived_slug = Path(source_path).stem
        else:
            title_clean = fm.get("title", "untitled").lower()
            derived_slug = re.sub(r"[^a-z0-9]+", "-", title_clean).strip("-")

    title = str(fm.get("title") or derived_slug.replace("-", " ").title())
    guest = fm.get("guest")

    pub_date: Optional[date] = None
    raw_date = fm.get("date")
    if raw_date:
        try:
            pub_date = date.fromisoformat(str(raw_date))
        except (ValueError, TypeError):
            pub_date = None

    turns, dropped_empty = extract_speaker_turns(raw_text, body_start=body_start)

    metadata: Dict[str, Any] = {
        "description": fm.get("description"),
        "word_count": fm.get("word_count"),
        "post_url": fm.get("post_url"),
        "youtube_url": fm.get("youtube_url"),
        "channel": fm.get("channel"),
        "video_id": fm.get("video_id"),
        "type": fm.get("type", "podcast"),
        "turn_count": len(turns),
        "empty_turns_dropped": dropped_empty,
        "speakers": sorted(list(set(t.speaker for t in turns))),
    }

    return ParsedDocument(
        slug=derived_slug,
        title=title,
        guest=guest,
        published_at=pub_date,
        source_path=source_path,
        content_hash=content_hash,
        metadata=metadata,
        turns=turns,
        raw_text=raw_text,
    )


def parse_transcript(
    content: str,
    source_path: str = "",
    slug: Optional[str] = None,
) -> ParsedDocument:
    """Alias for parse_transcript_text accepting content= keyword argument."""
    return parse_transcript_text(raw_text=content, source_path=source_path, slug=slug)


def parse_transcript_file(
    file_path: Path | str,
    source_path_override: Optional[str] = None,
) -> ParsedDocument:
    """Parse transcript from a file path."""
    path = Path(file_path)
    raw_text = path.read_text(encoding="utf-8")
    display_path = source_path_override or str(path).replace("\\", "/")
    return parse_transcript_text(
        raw_text=raw_text,
        source_path=display_path,
        slug=path.stem,
    )
