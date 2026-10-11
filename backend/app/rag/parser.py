"""Transcript parsing engine for Lenny Growth Assistant.

Extracts YAML frontmatter, deterministic SHA-256 content hashes,
and ordered speaker turns with exact character offsets.
Supports the ChatPRD corpus (episodes/{slug}/transcript.md) and legacy formats.
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

# Speaker turn patterns
# 1. Standard pattern: matches **Speaker** (ts): or Speaker (ts): or continuation (ts):
SPEAKER_TURN_STD_REGEX = re.compile(
    r"^[ \t]*(?:(?:\*\*([^\n*]+)\*\*|([A-Za-z0-9\.\'\+\-][^\n:(]*?))[ \t]+)?\(([\d:]{4,8})\):[ \t]*",
    re.MULTILINE,
)
# 2. Bracketed timestamps: [ts] Speaker: (e.g. ryan-hoover)
SPEAKER_TURN_BRACKET_REGEX = re.compile(
    r"^[ \t]*\[([\d:]{4,8})\][ \t]+([^:\n]+):[ \t]*",
    re.MULTILINE,
)
# 3. Colon only turns without timestamps (e.g. adriel-frederick)
SPEAKER_TURN_COLON_REGEX = re.compile(
    r"^[ \t]*([A-Z][A-Za-z0-9\s\.\'\+\-]{1,40}):[ \t]*$",
    re.MULTILINE,
)

# Alias for backward-compatibility with tests referencing SPEAKER_TURN_REGEX
SPEAKER_TURN_REGEX = SPEAKER_TURN_STD_REGEX
FRONTMATTER_REGEX = re.compile(r"^\ufeff?---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class SpeakerTurn:
    """Represents a single spoken utterance in a transcript."""

    speaker: str
    timestamp: str  # e.g. "00:00:00"
    text: str  # Spoken content, stripped
    start_char: int  # Start of spoken text in raw file
    end_char: int  # End of spoken text in raw file
    turn_start_char: int  # Start of turn header in raw file
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
    clean_text = raw_text.lstrip("\ufeff")
    fm_match = FRONTMATTER_REGEX.match(clean_text)
    if not fm_match:
        return {}, 0

    fm_raw = fm_match.group(1)
    body_start = fm_match.end()
    try:
        data = yaml.safe_load(fm_raw)
        return data if isinstance(data, dict) else {}, body_start
    except Exception:
        return {}, body_start


def is_episode_file(path: Path | str, fm: Optional[Dict[str, Any]] = None) -> bool:
    """Check whether a markdown file is a genuine podcast episode transcript.

    Skips index files, readmes, scripts, and non-episode files like teaser_2021.
    """
    p = Path(path)
    if p.suffix.lower() != ".md":
        return False
    parts = [part.lower() for part in p.parts]
    if "index" in parts or "scripts" in parts or "docs" in parts:
        return False
    if p.name.lower() in ("readme.md", "claude.md", "license.md", "episodes.md"):
        return False
    if p.parent.name.lower() in ("teaser_2021", "teaser") or p.stem.lower() in ("teaser_2021", "teaser"):
        return False
    if fm is not None:
        guest = str(fm.get("guest") or "").strip().lower()
        title = str(fm.get("title") or "").strip()
        if guest in ("teaser_2021", "teaser") or not title:
            return False
    return True


def derive_slug(
    path: Path | str,
    fm: Optional[Dict[str, Any]] = None,
    explicit_slug: Optional[str] = None,
) -> str:
    """Derive stable, unique slug for an episode.

    For transcripts formatted as episodes/{slug}/transcript.md, uses parent folder name.
    For legacy transcripts formatted as podcasts/{slug}.md, uses stem.
    """
    if explicit_slug:
        return explicit_slug

    p = Path(path)
    if p.name.lower() == "transcript.md" or p.stem.lower() in ("transcript", "index"):
        slug = p.parent.name
    else:
        slug = p.stem

    if not slug or slug.lower() in ("transcript", "index", "untitled", ".", ""):
        title = (fm or {}).get("title", "untitled")
        slug = re.sub(r"[^a-z0-9]+", "-", str(title).lower()).strip("-")
    return slug


def extract_speaker_turns(
    raw_text: str,
    body_start: int = 0,
    filter_empty: bool = True,
    normalize_host: bool = True,
) -> tuple[List[SpeakerTurn], int]:
    """Extract ordered speaker turns with verified character offsets.

    Supports:
    1. Standard turns: Speaker (HH:MM:SS):, **Speaker** (HH:MM:SS):, and continuation (HH:MM:SS):
    2. Bracketed turns: [HH:MM:SS] Speaker:
    3. Un-timestamped turns: Speaker:

    Args:
        raw_text: Complete file text (including frontmatter).
        body_start: Character offset where dialogue begins.
        filter_empty: If True, drops turns with empty text (e.g. sponsor breaks).
        normalize_host: If True, converts "Lenny" to "Lenny Rachitsky".

    Returns:
        tuple of (turns_list, dropped_empty_count)
    """
    m_std = list(SPEAKER_TURN_STD_REGEX.finditer(raw_text, pos=body_start))
    m_brack = list(SPEAKER_TURN_BRACKET_REGEX.finditer(raw_text, pos=body_start))
    m_colon = list(SPEAKER_TURN_COLON_REGEX.finditer(raw_text, pos=body_start))

    if len(m_std) >= 5:
        mode = "std"
        matches = m_std
    elif len(m_brack) >= 5:
        mode = "brack"
        matches = m_brack
    elif len(m_colon) >= 5:
        mode = "colon"
        matches = m_colon
    elif len(m_std) > 0:
        mode = "std"
        matches = m_std
    elif len(m_brack) > 0:
        mode = "brack"
        matches = m_brack
    elif len(m_colon) > 0:
        mode = "colon"
        matches = m_colon
    else:
        return [], 0

    turns: List[SpeakerTurn] = []
    dropped_empty = 0
    current_speaker = "Lenny Rachitsky"

    for i, match in enumerate(matches):
        if mode == "std":
            speaker_match = (match.group(1) or match.group(2) or "").strip()
            timestamp = match.group(3).strip()
            if speaker_match:
                speaker = speaker_match
                current_speaker = speaker
            else:
                speaker = current_speaker
        elif mode == "brack":
            timestamp = match.group(1).strip()
            speaker = match.group(2).strip()
            current_speaker = speaker
        else:  # colon
            speaker = match.group(1).strip()
            timestamp = "00:00:00"
            current_speaker = speaker

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
    clean_text = raw_text.lstrip("\ufeff")
    fm, body_start = extract_frontmatter(clean_text)
    content_hash = compute_content_hash(clean_text)

    derived_slug = slug
    if not derived_slug:
        if source_path:
            derived_slug = derive_slug(source_path, fm)
        else:
            title_clean = fm.get("title", "untitled").lower()
            derived_slug = re.sub(r"[^a-z0-9]+", "-", title_clean).strip("-")

    title = str(fm.get("title") or derived_slug.replace("-", " ").title())
    guest = fm.get("guest")

    pub_date: Optional[date] = None
    raw_date = fm.get("publish_date") or fm.get("date")
    if raw_date:
        if isinstance(raw_date, date):
            pub_date = raw_date
        else:
            try:
                pub_date = date.fromisoformat(str(raw_date).strip())
            except (ValueError, TypeError):
                pub_date = None

    turns, dropped_empty = extract_speaker_turns(clean_text, body_start=body_start)

    metadata: Dict[str, Any] = {
        "description": fm.get("description"),
        "word_count": fm.get("word_count"),
        "post_url": fm.get("post_url"),
        "youtube_url": fm.get("youtube_url") or "",
        "video_id": fm.get("video_id"),
        "channel": fm.get("channel"),
        "duration": fm.get("duration"),
        "duration_seconds": fm.get("duration_seconds"),
        "view_count": fm.get("view_count"),
        "keywords": fm.get("keywords") or [],
        "spotify_url": fm.get("spotify_url"),
        "spotify_id": fm.get("spotify_id"),
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
        raw_text=clean_text,
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
    slug: Optional[str] = None,
) -> ParsedDocument:
    """Parse transcript from a file path."""
    path = Path(file_path)
    raw_text = path.read_text(encoding="utf-8-sig")
    display_path = source_path_override or str(path).replace("\\", "/")
    derived_slug = slug or derive_slug(path)
    return parse_transcript_text(
        raw_text=raw_text,
        source_path=display_path,
        slug=derived_slug,
    )
