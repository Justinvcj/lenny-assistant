"""Citation extraction, validation, and verification engine for Lenny Growth Assistant.

Extracts [S#] tags from assistant answers, strips out-of-bounds tags,
resolves trusted citations from retrieval records, detects refusals,
and determines if a non-refusal answer needs a retry due to missing citations.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from pydantic import BaseModel, Field

from app.agent.prompts import EXACT_REFUSAL_MESSAGE
from app.rag.retrieval import RetrievalResult
from app.schemas import CitationItem

# Canonical refusal sentence per SPEC and PROMPTS.md
EXACT_REFUSAL_SENTENCE = EXACT_REFUSAL_MESSAGE

# Regex for matching individual citation tags: [S1], [s2], [ S3 ]
TAG_REGEX = re.compile(r"\[\s*[sS](\d+)\s*\]")

# Regex for matching any bracket containing S-prefixed citation tags
# e.g. [S1], [s2], [ S3 ], [S1, S2], [s1, s3]
ANY_CITATION_BRACKET_REGEX = re.compile(r"\[\s*[sS]\d+\s*(?:,\s*[sS]\d+\s*)*\]")


class VerificationResult(BaseModel):
    """Result of citation verification and tag validation."""

    cleaned_text: str = Field(
        ...,
        description="Assistant response text with invalid citation tags stripped.",
    )
    citations: List[CitationItem] = Field(
        default_factory=list,
        description="Ordered, deduplicated CitationItem list resolved from sources.",
    )
    valid_tags: List[int] = Field(
        default_factory=list,
        description="Source numbers found in text that mapped to valid retrieved sources.",
    )
    invalid_tags: List[int] = Field(
        default_factory=list,
        description="Out-of-bounds or invalid source numbers found in text.",
    )
    is_refusal: bool = Field(
        default=False,
        description="True if the response is an intentional refusal.",
    )
    needs_retry: bool = Field(
        default=False,
        description="True if a non-refusal answer contains zero valid citations or unsupported names.",
    )
    unsupported_names: List[str] = Field(
        default_factory=list,
        description="Names of guests mentioned in the answer not supported by cited sources.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="User-facing warnings (e.g. mentions name not in cited transcripts).",
    )


def extract_citation_tags(text: str) -> List[int]:
    """Extract all [S#] tag numbers from response text in order of appearance.

    Supports:
    - [S1], [S2], [s3], [ S4 ]
    - Grouped tags: [S1, S2], [s1, s3]
    - Adjacent brackets: [S1][S2]
    - Ignores non-source brackets: [2024], [Appendix], [SX], [S]
    """
    tags: List[int] = []
    if not text:
        return tags

    for match in ANY_CITATION_BRACKET_REGEX.finditer(text):
        bracket_content = match.group(0)
        numbers = re.findall(r"[sS](\d+)", bracket_content)
        for num_str in numbers:
            tags.append(int(num_str))

    return tags


def is_refusal_response(text: str) -> bool:
    """Check if the response matches the canonical refusal sentence.

    Normalizes whitespace, surrounding quotes, casing, and trailing punctuation.
    """
    if not text:
        return False

    normalized = text.strip().strip('"\'').strip().rstrip(".").lower()
    canonical_normalized = EXACT_REFUSAL_MESSAGE.rstrip(".").lower()
    return normalized == canonical_normalized


def strip_invalid_tags(text: str, valid_tag_set: Set[int]) -> str:
    """Remove out-of-bounds [S#] tags from text while preserving valid tags.

    Normalizes resulting double spaces and punctuation spacing.
    """
    if not text:
        return text

    def replace_bracket(match: re.Match) -> str:
        bracket_content = match.group(0)
        items = re.findall(r"([sS](\d+))", bracket_content)
        kept_numbers = [int(num_str) for _, num_str in items if int(num_str) in valid_tag_set]

        if not kept_numbers:
            return ""
        if len(kept_numbers) == 1:
            return f"[S{kept_numbers[0]}]"
        return "[" + ", ".join(f"S{num}" for num in kept_numbers) + "]"

    cleaned = ANY_CITATION_BRACKET_REGEX.sub(replace_bracket, text)
    # Clean up spaces before punctuation caused by stripping tags
    cleaned = re.sub(r"[ \t]+([.,;:!?])", r"\1", cleaned)
    # Collapse multiple horizontal whitespace into a single space
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def resolve_citations(
    valid_tags: Sequence[int],
    sources: Sequence[Any],
) -> List[CitationItem]:
    """Resolve CitationItem models from retrieved sources matching valid tags.

    Deduplicates citations while preserving order of first appearance.
    NEVER fabricates metadata from model text.
    """
    citations: List[CitationItem] = []
    seen_tags: Set[int] = set()

    for tag in valid_tags:
        if tag in seen_tags:
            continue
        seen_tags.add(tag)

        # 1-based indexing: S1 -> sources[0]
        source_idx = tag - 1
        if 0 <= source_idx < len(sources):
            src = sources[source_idx]
            if isinstance(src, dict):
                chunk_id = src.get("chunk_id")
                doc_slug = src.get("document_slug") or src.get("doc_slug") or ""
                title = src.get("title") or "Unknown"
                guest = src.get("guest")
                passage = src.get("text") or src.get("passage") or ""
            else:
                chunk_id = getattr(src, "chunk_id", None)
                doc_slug = getattr(src, "document_slug", getattr(src, "doc_slug", ""))
                title = getattr(src, "title", "Unknown")
                guest = getattr(src, "guest", None)
                passage = getattr(src, "text", getattr(src, "passage", ""))

            # Guarantee valid UUID
            if isinstance(chunk_id, str):
                parsed_chunk_id = uuid.UUID(chunk_id)
            elif isinstance(chunk_id, uuid.UUID):
                parsed_chunk_id = chunk_id
            else:
                parsed_chunk_id = uuid.uuid4()

            citations.append(
                CitationItem(
                    n=tag,
                    chunk_id=parsed_chunk_id,
                    doc_slug=doc_slug,
                    title=title,
                    guest=guest,
                    passage=passage,
                )
            )

    return citations


HOST_NAMES = {"lenny", "lenny rachitsky", "rachitsky"}

KNOWN_GUEST_ROSTER: Set[str] = {
    "Ada Chen Rekhi", "Adam Fishman", "Adam Grenier", "Adriel Frederick",
    "Aishwarya Naresh Reganti", "Kiriti Badam", "Albert Cheng", "Alexander Embiricos",
    "Alex Hardimen", "Alex Komoroske", "Alisa Cohn", "Ami Vora", "Amjad Masad",
    "Andrew Wilkinson", "Andy Johns", "Andy Raskin", "Anneka Gupta", "Annie Duke",
    "Annie Pearl", "Anton Osika", "Anuj Rathi", "Aparna Chennapragada", "April Dunford",
    "Archie Abrams", "Arielle Jackson", "Asha Sharma", "Austin Hay", "Ayo Omojola",
    "Bangaly Kaba", "Barbra Gago", "Ben Horowitz", "Benjamin Lauzier", "Benjamin Mann",
    "Ben Williams", "Bill Carr", "Bob Baxley", "Bob Moesta", "Boz", "Brandon Chu",
    "Brendan Foody", "Bret Taylor", "Brian Balfour", "Brian Chesky", "Brian Tolkin",
    "Cam Adams", "Camille Fournier", "Camille Hearst", "Camille Ricketts",
    "Carilu Dietrich", "Carole Robin", "Casey Winters", "Chandra Janakiraman",
    "Chip Conley", "Chip Huyen", "Chris Hutchins", "Christian Idiodi", "Christina Wodtke",
    "Christine Itwaru", "Christopher Lochhead", "Christopher Miller", "Claire Butler",
    "Claire Hughes Johnson", "Claire Vo", "Crystal W", "Dalton Caldwell",
    "Dan Hockenmaier", "Daniel Lereya", "Dan Shipper", "David Placek", "David Singleton",
    "Deb Liu", "Dhanji R. Prasanna", "Dharmesh Shah", "Dmitry Zlokazov", "Donna Lichaw",
    "Drew Houston", "Dr. Fei Fei Li", "Dylan Field", "Ebi Atawodi", "Edwin Chen",
    "Eeke de Milliano", "Elena Verna", "Eli Schwartz", "Elizabeth Stone", "Emilie Gerber",
    "Emily Kramer", "Eoghan McCabe", "Eric Ries", "Eric Simons", "Ethan Evans",
    "Ethan Smith", "Evan LaPointe", "Fareed Mosavat", "Farhan Thawar", "Fei Fei",
    "Garrett Lord", "Gaurav Misra", "Geoff Charles", "Geoffrey Moore", "Gergely",
    "Gia Laudi", "Gibson Biddle", "Gina Gotthilf", "Gokul Rajaram", "Graham Weaver",
    "Grant Lee", "Guillermo Rauch", "Gustaf Alstromer", "Gustav Söderström",
    "Hamel Husain", "Shreya Shankar", "Hamilton Helmer", "Hari Srinivasan",
    "Heidi Helfand", "Hila Qu", "Hilary Gridley", "Howie Liu", "Ian McAllister",
    "Inbal S", "Itamar Gilad", "Ivan Zhao", "Jackie Bavaro", "Jackson Shuttleworth",
    "Jag Duggal", "Jake Knapp", "John Zeratsky", "Janna Bastow", "Jason Droege",
    "Jason Feifer", "Jason Fried", "Jason M Lemkin", "Jason Shah", "Jeanne Grosser",
    "Jeffrey Pfeffer", "Jeff Weinstein", "Jen Abel", "Jeremy Henrickson",
    "Jerry Colonna", "Jessica Hische", "Jessica Livingston", "Jess Lachs",
    "Jiaona Zhang", "Joe Hudson", "John Cutler", "John Mark Nickels",
    "Jonathan Becker", "Jonathan Lowenhar", "Jonny Miller", "Josh Miller",
    "Judd Antin", "Jules Walter", "Julian Shapiro", "Julia Schottenstein",
    "Julie Zhuo", "Karina Nguyen", "Karri Saarinen", "Katie Dill", "Kayvon Beykpour",
    "Keith Coleman", "Jay Baxter", "Keith Yandell", "Kenneth Berger", "Ken Norton",
    "Kevin Aluwi", "Kevin Weil", "Kevin Yien", "Kim Scott", "Kristen Berman",
    "Krithika Shankarraman", "Kunal Shah", "Lane Shackleton", "Laura Modi",
    "Laura Schaffer", "Lauren Ipsen", "Lauryn Isford", "Logan Kilpatrick",
    "Luc Levesque", "Lulu Cheng Meservey", "Madhavan Ramanujam", "Maggie Crowley",
    "Manik Gupta", "Marc Benioff", "Marily Nika", "Marty Cagan", "Matt Abrahams",
    "Matt Dixon", "Matthew Dicks", "Matt LeMay", "Matt MacInnis", "Matt Mochary",
    "Matt Mullenweg", "Maya Prohovnik", "Mayur Kamat", "Megan Cook", "Melanie Perkins",
    "Melissa Perri", "Denise Tilles", "Melissa Tan", "Meltem Kuran", "Merci Grace",
    "Michael Truell", "Mihika Kapoor", "Mike Krieger", "Mike Maples Jr", "Molly Graham",
    "Nabeel S. Qureshi", "Nancy Duarte", "Nan Yu", "Naomi Gleit", "Naomi Ionita",
    "Nickey Skarstad", "Nick Turley", "Nicole Forsgren", "Nikhyl Singhal",
    "Nikita Bier", "Nikita Miller", "Nilan Peiris", "Nir Eyal", "Noah Weiss",
    "Noam Lovinsky", "Oji Udezue", "Paige Costello", "Patrick Campbell",
    "Paul Adams", "Paul Millerd", "Pete Kazanjy", "Peter Deng", "Petra Wille",
    "Phyl Terry", "Raaz Herzberg", "Rachel Lockett", "Rahul Vohra", "Ramesh Johari",
    "Ravi Mehta", "Ray Cao", "Richard Rumelt", "Robby Stein", "Roger Martin",
    "Ronny Kohavi", "Ryan Hoover", "Ryan J. Salva", "Ryan Singer", "Sachin Monga",
    "Sahil Mansuri", "Sam Schillace", "Sanchan Saxena", "Sander Schulhoff",
    "Sarah Tavel", "Scott Belsky", "Scott Wu", "Sean Ellis", "Seth Godin",
    "Shaun Clowes", "Shishir Mehrotra", "Shreyas Doshi", "Shweta Shriva",
    "Sri Batchu", "Stewart Butterfield", "Tamar Yehoshua", "Tanguy Crusson",
    "Teresa Torres", "Tim Holley", "Timothy Davis", "Tobi Lutke", "Todd Jackson",
    "Tom Conrad", "Tomer Cohen", "Tristan de Montebello", "Upasna Gautam",
    "Uri Levine", "Varun Mohan", "Varun Parmar", "Vikrama Dhiman", "Wes Kao",
    "Will Larson", "Yuhki Yamashata", "Yuriy Timen", "Zoelle Egner",
}

_DYNAMIC_GUEST_ROSTER: Optional[Set[str]] = None


async def load_guest_roster(db: Optional[Any] = None) -> Set[str]:
    """Load distinct guest names from documents table, falling back to static roster."""
    global _DYNAMIC_GUEST_ROSTER
    if _DYNAMIC_GUEST_ROSTER is not None:
        return _DYNAMIC_GUEST_ROSTER
    if db is not None:
        try:
            from sqlalchemy import distinct, select
            from app.models import Document
            stmt = select(distinct(Document.guest)).where(Document.guest.isnot(None))
            res = await db.execute(stmt)
            names = {r[0].strip() for r in res.all() if r[0] and r[0].strip()}
            if names:
                _DYNAMIC_GUEST_ROSTER = names
                return _DYNAMIC_GUEST_ROSTER
        except Exception:
            pass
    return KNOWN_GUEST_ROSTER


def check_unsupported_names(
    answer: str,
    sources: Sequence[Any],
    known_roster: Optional[Set[str]] = None,
) -> List[str]:
    """Identify person/guest names mentioned in answer that are not supported by cited sources.

    Checks known Lenny Podcast guests against the answer.
    A name is supported if it appears in any cited source (guest, title, or passage text)
    or is the host (Lenny Rachitsky).
    Supports full name and partial matches (first name or last name >= 4 characters).
    """
    if not answer:
        return []

    roster = known_roster if known_roster is not None else (_DYNAMIC_GUEST_ROSTER or KNOWN_GUEST_ROSTER)
    answer_lower = answer.lower()

    # Collect all supported tokens and names from cited sources
    supported_text_corpus: List[str] = ["lenny", "lenny rachitsky", "rachitsky"]
    for s in sources:
        if isinstance(s, dict):
            g = s.get("guest")
            t = s.get("title")
            txt = s.get("text") or s.get("passage") or ""
        else:
            g = getattr(s, "guest", None)
            t = getattr(s, "title", None)
            txt = getattr(s, "text", getattr(s, "passage", ""))
        if g:
            supported_text_corpus.append(str(g).lower())
        if t:
            supported_text_corpus.append(str(t).lower())
        if txt:
            supported_text_corpus.append(str(txt).lower())

    full_supported_corpus = " ".join(supported_text_corpus)

    unsupported: List[str] = []
    seen: Set[str] = set()

    for guest in roster:
        clean_guest = guest.strip()
        if not clean_guest or clean_guest.lower() in HOST_NAMES:
            continue

        guest_lower = clean_guest.lower()
        parts = [p.strip().lower() for p in clean_guest.split() if len(p.strip()) >= 3]

        # Check full name match in answer
        full_pattern = r"\b" + re.escape(guest_lower) + r"\b"
        if re.search(full_pattern, answer_lower):
            if guest_lower not in full_supported_corpus:
                if clean_guest not in seen:
                    unsupported.append(clean_guest)
                    seen.add(clean_guest)
            continue

        # Check partial match (distinctive name part >= 4 chars)
        for part in parts:
            if len(part) >= 4 and part not in ("with", "from", "live", "about", "what", "team", "growth"):
                part_pattern = r"\b" + re.escape(part) + r"\b"
                if re.search(part_pattern, answer_lower):
                    if part not in full_supported_corpus:
                        if clean_guest not in seen:
                            unsupported.append(clean_guest)
                            seen.add(clean_guest)
                            break

    return unsupported


def verify_citations(
    answer: str,
    sources: Sequence[Any],
    db: Optional[Any] = None,
) -> VerificationResult:
    """Full citation verification pipeline.

    1. Check for intentional refusal.
    2. Extract all citation tags.
    3. Segregate valid vs invalid tags against available sources.
    4. Strip invalid tags from answer text while preserving valid tags.
    5. Resolve CitationItem objects from retrieved sources.
    6. Check for unsupported person/guest names.
    7. Determine needs_retry flag.
    """
    clean_ans = answer.strip() if answer else ""

    # Check for intentional refusal
    if is_refusal_response(clean_ans):
        return VerificationResult(
            cleaned_text=clean_ans,
            citations=[],
            valid_tags=[],
            invalid_tags=[],
            is_refusal=True,
            needs_retry=False,
            unsupported_names=[],
            warnings=[],
        )

    # If answer is empty or whitespace
    if not clean_ans:
        return VerificationResult(
            cleaned_text="",
            citations=[],
            valid_tags=[],
            invalid_tags=[],
            is_refusal=False,
            needs_retry=True,
            unsupported_names=[],
            warnings=[],
        )

    # First normalize citations in incoming answer so bare S#, (S1), [S1, S2] are canonicalized
    normalized_ans = normalize_citations(clean_ans)

    # Extract all citation tags
    all_tags = extract_citation_tags(normalized_ans)
    k = len(sources)

    valid_tag_set = {n for n in all_tags if 1 <= n <= k}
    valid_tags = [n for n in all_tags if n in valid_tag_set]
    invalid_tags = [n for n in all_tags if n not in valid_tag_set]

    # Clean text by removing out-of-bounds tags
    cleaned_text = strip_invalid_tags(normalized_ans, valid_tag_set)

    # Resolve CitationItems from retrieved sources
    citations = resolve_citations(valid_tags, sources)

    # Check for unsupported guest names in substantive answers
    unsupported_names = check_unsupported_names(clean_ans, sources)
    warnings: List[str] = [f"Mentions {name}, who is not in the cited transcripts" for name in unsupported_names]

    # Substantive non-refusal answer with zero valid citations or unsupported names triggers retry
    needs_retry = (len(citations) == 0) or (len(unsupported_names) > 0)

    return VerificationResult(
        cleaned_text=cleaned_text,
        citations=citations,
        valid_tags=valid_tags,
        invalid_tags=invalid_tags,
        is_refusal=False,
        needs_retry=needs_retry,
        unsupported_names=unsupported_names,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Citation Normalization & Strict [S#] Formatting
# ---------------------------------------------------------------------------

RE_PAREN_CITATION = re.compile(
    r"\(\s*(\[?[sS]\d+\]?(?:\s*,\s*(?:\[?[sS]\d+\]?|\d{1,2}:\d{2}(?::\d{2})?))*)\s*\)"
)
RE_PAREN_SIMPLE = re.compile(r"\(\s*([sS]\d+(?:\s*,\s*[sS]\d+)*)\s*\)")
RE_ILLEGAL_CITATION = re.compile(
    r"\(\s*\[?[sS]\d+|\([sS]\d+\b|\[\s*[sS]\d+\s*,\s*[sS]\d+"
)


def normalize_citations(text: str) -> str:
    """Normalize all citation variants to strict [S#] or adjacent [S1][S2].

    Converts:
    - Bare S#: '...through the doors. S3' -> '...through the doors. [S3]'
               '...in the fourth week. S4' -> '...in the fourth week. [S4]'
               '...metrics. S1, S2' -> '...metrics. [S1][S2]'
    - (S1), (s1) -> [S1]
    - ([S4], 00:48:00), ([S1], [S5], 01:03:41) -> [S4], [S1][S5]
    - [S1, S2], [S3, S4, S5] -> [S1][S2], [S3][S4][S5]
    - ([S1]) -> [S1]
    """
    if not text:
        return text

    # 1. Clean parenthesized groups with timestamps or brackets
    def _replace_ts(m: re.Match) -> str:
        tags = re.findall(r"[sS](\d+)", m.group(0))
        return "".join(f"[S{t}]" for t in tags) if tags else m.group(0)

    text = re.sub(r"\(\s*\[?\s*[sS]\d+[^)]*?\d{1,2}:\d{2}(?::\d{2})?[^)]*?\)", _replace_ts, text)

    # 2. Clean bracketed comma lists: [S3, S4, S5], [S1, S2]
    def _replace_bracket_multi(m: re.Match) -> str:
        tags = re.findall(r"[sS](\d+)", m.group(0))
        return "".join(f"[S{t}]" for t in tags)

    text = re.sub(r"\[\s*[sS]\d+(?:\s*,\s*[sS]\d+)+\s*\]", _replace_bracket_multi, text)

    # 3. Clean simple (S1) or (S1, S2)
    def _replace_paren_simple(m: re.Match) -> str:
        tags = re.findall(r"[sS](\d+)", m.group(0))
        return "".join(f"[S{t}]" for t in tags) if tags else m.group(0)

    text = re.sub(r"\(\s*\[?\s*[sS]\d+(?:\s*,\s*\[?\s*[sS]\d+)*\s*\]?\s*\)", _replace_paren_simple, text)

    # 4. Clean bare S# after punctuation: '...through the doors. S3' -> '...through the doors. [S3]'
    def _replace_bare_after_punct(m: re.Match) -> str:
        punct = m.group(1)
        tags_str = m.group(2)
        tags = re.findall(r"[sS](\d+)", tags_str)
        if tags:
            return f"{punct} " + "".join(f"[S{t}]" for t in tags)
        return m.group(0)

    text = re.sub(
        r"([.!?])\s+([sS]\d+(?:\s*,\s*[sS]\d+)*)(?=[.!?\s]|$)",
        _replace_bare_after_punct,
        text,
    )

    # 5. Clean bare S# before punctuation: '...fourth week S4.' -> '...fourth week [S4].'
    def _replace_bare_before_punct(m: re.Match) -> str:
        word = m.group(1)
        if word.lower() in ("aws", "amazon"):
            return m.group(0)
        num = m.group(2)
        punct = m.group(3)
        return f"{word} [S{num}]{punct}"

    text = re.sub(
        r"\b([a-zA-Z0-9”\"’']+)\s+[sS](\d+)([.,;:!?])(?!\s*(?:bucket|storage|api)\b)",
        _replace_bare_before_punct,
        text,
    )

    # 6. Clean bare S# at very end of text
    text = re.sub(
        r"\b([a-zA-Z0-9”\"’']+)\s+[sS](\d+)\s*$",
        lambda m: m.group(0) if m.group(1).lower() in ("aws", "amazon") else f"{m.group(1)} [S{m.group(2)}]",
        text,
    )

    return text


def has_illegal_citations(text: str) -> bool:
    """Check if any unnormalized citations remain (e.g. (S1), ([S1]...))."""
    return bool(RE_ILLEGAL_CITATION.search(text))


# ---------------------------------------------------------------------------
# Sentence Support & Groundedness Analysis
# ---------------------------------------------------------------------------

STOP_WORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
    "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
    "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so",
    "some", "such", "than", "that", "that's", "the", "their", "theirs", "them",
    "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll",
    "they're", "they've", "this", "those", "through", "to", "too", "under", "until",
    "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves", "also", "just", "like"
}


def get_content_words(text: str) -> List[str]:
    """Tokenize and extract non-stop content words (lowercase alphanumeric, length > 1)."""
    clean = re.sub(r"\[sS]\d+\]", " ", text)
    tokens = re.findall(r"\b[a-zA-Z0-9_-]+\b", clean.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]


def sentence_overlap_score(sentence: str, chunk_text: str) -> float:
    """Compute share of sentence content words that appear in cited chunk."""
    s_words = set(get_content_words(sentence))
    if not s_words:
        return 1.0  # Empty of content words (e.g. transitional)
    c_words = set(get_content_words(chunk_text))
    return len(s_words & c_words) / len(s_words)


# Fact or advice indicator pattern
RE_FACT_OR_ADVICE = re.compile(
    r"\b(?:\d+|%|\$|should|must|need\s+to|needs\s+to|have\s+to|has\s+to)\b|"
    r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b"
)


def verify_direct_quotes(text: str, sources: Sequence[Any]) -> Tuple[str, int, int]:
    """Verify that 6+ word quotes in text appear verbatim in cited source passages.

    If non-verbatim, rewrites quote into a paraphrase without quotation marks.
    Returns (cleaned_text, valid_quotes_count, total_quotes_count).
    """
    total_quotes = 0
    valid_quotes = 0

    # Build corpus of normalized source texts
    normalized_sources = []
    for s in sources:
        txt = s.get("text") or s.get("passage") if isinstance(s, dict) else getattr(s, "text", getattr(s, "passage", ""))
        clean_txt = re.sub(r"[^\w\s]", " ", (txt or "").lower())
        normalized_sources.append(" ".join(clean_txt.split()))

    full_corpus = " ".join(normalized_sources)

    def _replace_quote(m: re.Match) -> str:
        nonlocal total_quotes, valid_quotes
        quote_body = m.group(1).strip()
        words = quote_body.split()
        if len(words) < 6:
            return m.group(0)

        total_quotes += 1
        clean_quote = re.sub(r"[^\w\s]", " ", quote_body.lower())
        norm_quote = " ".join(clean_quote.split())

        if norm_quote in full_corpus:
            valid_quotes += 1
            return m.group(0)
        else:
            # Paraphrase without quotes
            return quote_body

    pattern = re.compile(r'["“]([^"”\n]{25,})["”]')
    cleaned = pattern.sub(_replace_quote, text)
    return cleaned, valid_quotes, total_quotes


def extract_speaker_turns(sources: Sequence[Any]) -> List[Tuple[str, str, str]]:
    """Extract (speaker, timestamp_header, turn_body) from source passages."""
    turns: List[Tuple[str, str, str]] = []
    turn_re = re.compile(
        r"(?:^|\n)\*?\*?([A-Z][a-zA-Z\s.'-]+?)\*?\*?\s*\((?:\d{1,2}:)?\d{2}:\d{2}\):\s*",
    )
    for s in sources:
        txt = s.get("text") or s.get("passage") if isinstance(s, dict) else getattr(s, "text", getattr(s, "passage", ""))
        guest = s.get("guest") if isinstance(s, dict) else getattr(s, "guest", None)
        if not txt:
            continue
        matches = list(turn_re.finditer(txt))
        if not matches:
            if guest:
                turns.append((guest, "", txt))
            continue
        for i, m in enumerate(matches):
            speaker = m.group(1).strip()
            start_pos = m.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(txt)
            turn_body = txt[start_pos:end_pos].strip()
            turns.append((speaker, m.group(0), turn_body))
    return turns


def verify_speaker_attribution(text: str, sources: Sequence[Any]) -> Tuple[str, List[str]]:
    """Check that names next to quotes or claims match the guest or speaker of cited chunk.

    Host (Lenny) may only be credited for turns whose speaker label is Lenny.
    If an essay credits a quote or phrase to 'Lenny Rachitsky' that was spoken by another
    guest (e.g. 'Sean Ellis'), rewrites to the true speaker and records the mismatch.
    """
    turns = extract_speaker_turns(sources)
    if not turns:
        return text, []

    mismatches: List[str] = []
    corrected_text = text

    # Check all quotes of 3+ words (e.g. "when do I think they've had a good enough experience...")
    quote_re = re.compile(r'["“]([^"”\n]{15,})["”]')
    for q_match in quote_re.finditer(text):
        quote_body = q_match.group(1).strip()
        quote_clean = " ".join(re.sub(r"[^\w\s]", " ", quote_body.lower()).split())
        if len(quote_clean.split()) < 3:
            continue

        # Find matching speaker turn in sources
        actual_speaker = None
        for speaker, header, turn_body in turns:
            turn_clean = " ".join(re.sub(r"[^\w\s]", " ", turn_body.lower()).split())
            if quote_clean in turn_clean:
                actual_speaker = speaker
                break

        if not actual_speaker:
            continue

        # Look at the sentence block containing the quote
        start = max(0, text.rfind("\n", 0, q_match.start()))
        end = text.find("\n", q_match.end())
        if end == -1:
            end = len(text)
        sentence_block = text[start:end]

        # Check if another name (especially Lenny) is attributed in this sentence
        for wrong_name in ["Lenny Rachitsky", "Lenny", "Hila Qu", "Elena Verna", "Sean Ellis", "Ben Williams", "Brian Balfour"]:
            if wrong_name.lower() != actual_speaker.lower() and wrong_name.lower() in sentence_block.lower():
                if actual_speaker.lower() not in sentence_block.lower():
                    mismatches.append(
                        f"Speaker attribution mismatch: quote '{quote_body[:40]}...' spoken by {actual_speaker}, but attributed to {wrong_name}"
                    )
                    pat = re.compile(r"\b" + re.escape(wrong_name) + r"\b", re.IGNORECASE)
                    new_block = pat.sub(actual_speaker, sentence_block)
                    corrected_text = corrected_text.replace(sentence_block, new_block, 1)
                    break

    return corrected_text, mismatches


# ---------------------------------------------------------------------------
# Paragraph Deduplication
# ---------------------------------------------------------------------------


def normalize_paragraph_for_dedup(text: str) -> str:
    """Normalize paragraph content for duplicate detection."""
    clean = re.sub(r"^#+\s+", "", text)
    clean = re.sub(r"^\s*[-*+]\s+", "", clean)
    clean = re.sub(r"\[sS]\d+\]", "", clean)
    clean = re.sub(r"[#*_`~>\[\]()!-]", " ", clean)
    tokens = [w.lower() for w in clean.split() if any(c.isalnum() for c in w)]
    return " ".join(tokens)


def check_duplicate_paragraphs(text: str) -> List[Tuple[str, str, float]]:
    """Find identical or near-duplicate paragraphs (normalized word overlap >= 0.80)."""
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    seen: List[Tuple[str, str, Set[str]]] = []
    duplicates = []
    for p in paras:
        if p.startswith("#") or len(p.split()) < 10:
            continue
        norm = normalize_paragraph_for_dedup(p)
        words_set = set(norm.split())
        if not words_set:
            continue
        for prev_p, prev_norm, prev_set in seen:
            if norm == prev_norm:
                duplicates.append((prev_p, p, 1.0))
                break
            overlap = len(words_set & prev_set) / max(len(words_set), len(prev_set))
            if overlap >= 0.80:
                duplicates.append((prev_p, p, overlap))
                break
        else:
            seen.append((p, norm, words_set))
    return duplicates


def deduplicate_paragraphs(text: str) -> str:
    """Remove duplicate and near-duplicate paragraphs while preserving order and headings."""
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    seen_sets: List[Set[str]] = []
    kept_paras: List[str] = []

    for p in paras:
        if p.startswith("#") or len(p.split()) < 10:
            kept_paras.append(p)
            continue

        norm = normalize_paragraph_for_dedup(p)
        words_set = set(norm.split())
        if not words_set:
            kept_paras.append(p)
            continue

        is_dup = False
        for prev_set in seen_sets:
            overlap = len(words_set & prev_set) / max(len(words_set), len(prev_set))
            if overlap >= 0.80:
                is_dup = True
                break

        if not is_dup:
            seen_sets.append(words_set)
            kept_paras.append(p)

    return "\n\n".join(kept_paras)


@dataclass
class GroundednessReport:
    support_score: float
    supported_sentences: int
    total_sentences: int
    quotes_verified: str
    unsupported_names: List[str]
    citation_format_ok: bool
    duplicates_found: int
    cleaned_text: str
    speaker_mismatches: List[str] = field(default_factory=list)


def clean_heading_profanity(text: str) -> str:
    """Ensure H1/H2 headings do not contain profanity; keep terms in body text only."""
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        if line.startswith("#"):
            line = re.sub(
                r"\b(?:the\s+)?(?:law\s+of\s+)?[sS]hitty\s+[cC]lickthroughs?\b",
                "Feedback Loops and Diminishing Returns",
                line,
                flags=re.IGNORECASE,
            )
            line = re.sub(r"\b[sS]hitty\b", "Diminishing", line, flags=re.IGNORECASE)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def verify_essay_groundedness(
    essay_text: str,
    sources: Sequence[Any],
    threshold: float = 0.35,
) -> GroundednessReport:
    """Full groundedness verification for essays per Item 3 & 10.

    1. Normalizes all citations to [S#].
    2. Cleans profanity from headings (keeping terms in body in quotation marks).
    3. Verifies direct quotes against cited chunks (rewriting invalid quotes).
    4. Verifies speaker attribution (e.g. quote spoken by Sean Ellis credited to Lenny).
    5. Deduplicates duplicate/near-duplicate paragraphs.
    6. Evaluates sentence support for all sentences tagged with [S#].
    7. Checks unsupported person/guest names.
    """
    # 1. Normalize citations
    normalized = normalize_citations(essay_text)
    citation_format_ok = not has_illegal_citations(normalized)

    # 2. Heading profanity cleaning
    heading_cleaned = clean_heading_profanity(normalized)

    # 3. Quote verification
    quote_cleaned, valid_quotes, total_quotes = verify_direct_quotes(heading_cleaned, sources)
    quotes_str = f"{valid_quotes}/{total_quotes}" if total_quotes > 0 else "0/0"

    # 4. Speaker attribution verification
    attr_cleaned, speaker_mismatches = verify_speaker_attribution(quote_cleaned, sources)

    # 5. Deduplicate paragraphs
    duplicates = check_duplicate_paragraphs(attr_cleaned)
    deduped = deduplicate_paragraphs(attr_cleaned)

    # 6. Check sentence support
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", deduped) if s.strip() and not s.strip().startswith("#")]
    total_tagged = 0
    supported_tagged = 0

    # Build sources dictionary by 1-based index
    src_map = {}
    for idx, s in enumerate(sources, start=1):
        txt = s.get("text") or s.get("passage") if isinstance(s, dict) else getattr(s, "text", getattr(s, "passage", ""))
        src_map[idx] = txt or ""

    for s in sentences:
        tags = extract_citation_tags(s)
        if tags:
            total_tagged += 1
            is_supported = False
            for t in tags:
                chunk_txt = src_map.get(t, "")
                if chunk_txt and sentence_overlap_score(s, chunk_txt) >= threshold:
                    is_supported = True
                    break
            if is_supported:
                supported_tagged += 1

    support_score = (supported_tagged / total_tagged) if total_tagged > 0 else 1.0

    # 7. Unsupported names
    unsupported_names = check_unsupported_names(deduped, sources)

    return GroundednessReport(
        support_score=round(support_score, 4),
        supported_sentences=supported_tagged,
        total_sentences=total_tagged,
        quotes_verified=quotes_str,
        unsupported_names=unsupported_names,
        citation_format_ok=citation_format_ok,
        duplicates_found=len(duplicates),
        cleaned_text=deduped,
        speaker_mismatches=speaker_mismatches,
    )
