import re
import pytest
from app.routers.chat import (
    clean_html_asterisks,
    generate_deterministic_html_summary,
    generate_deterministic_markdown_summary,
)


# ============================================================================
# R3: Artifact Title XSS Sanitization (Adversarial Stress Suite)
# ============================================================================

HOSTILE_TITLE_PAYLOADS = [
    "</title><script>alert(1)</script>",
    "</title><style>body { display: none; background: red; }</style>",
    "</title><svg onload=alert(1)>",
    "</title><svg/onload=alert(1)>",
    "</title><svg><desc><![CDATA[</desc><script>alert(1)</script>]]></svg>",
    '"><script>alert(1)</script>',
    '\'"><script>alert(1)</script>',
    "</TiTlE><ScRiPt>alert(1)</sCrIpT>",
    "</TITLE><SCRIPT>alert(1)</SCRIPT>",
    '</title><iframe src="javascript:alert(1)"></iframe>',
    "</title><img src=x onerror=alert(1)>",
    "</title><body onload=alert(1)>",
    '</title><base href="javascript:alert(1)//">',
    "＜/title＞＜script＞alert(1)＜/script＞",
    "\\u003c/title\\u003e\\u003cscript\\u003ealert(1)\\u003c/script\\u003e",
    "&lt;/title&gt;&lt;script&gt;alert(1)&lt;/script&gt;",
    "Growth Strategy & \"PMF\" <Playbook> '2026' `Metrics`",
    "A" * 5000 + "</title><script>alert(1)</script>",
]


@pytest.mark.parametrize("payload", HOSTILE_TITLE_PAYLOADS)
def test_backend_html_title_xss_adversarial(payload):
    """Verify backend HTML generator completely neutralizes aggressive title XSS payloads."""
    citations = [{"n": 1, "guest": "Lenny", "title": "Ep 1", "passage": "Sample text"}]
    html = generate_deterministic_html_summary(
        title=payload,
        markdown_text="Clean body content [S1].",
        citations=citations,
    )

    # 1. No unescaped script tag anywhere in generated HTML
    assert "<script" not in html.lower(), f"Unescaped <script found for payload: {payload}"
    assert "</script>" not in html.lower(), f"Unescaped </script> found for payload: {payload}"

    # 2. No unescaped iframe, svg, img tags from payload
    assert "<iframe" not in html.lower(), f"Unescaped <iframe found for payload: {payload}"
    assert "<svg" not in html.lower(), f"Unescaped <svg found for payload: {payload}"
    assert "<img" not in html.lower(), f"Unescaped <img found for payload: {payload}"

    # 3. Exactly one <title> and </title> in whole document
    title_opens = len(re.findall(r"<title>", html, re.IGNORECASE))
    title_closes = len(re.findall(r"</title>", html, re.IGNORECASE))
    assert title_opens == 1, f"Expected 1 <title>, got {title_opens} for payload: {payload}"
    assert title_closes == 1, f"Expected 1 </title>, got {title_closes} for payload: {payload}"

    # 4. Verified escaped representations in <title> and <h1>
    m = re.search(r"<title>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    assert m is not None
    inner_title = m.group(1)
    assert "<" not in inner_title, f"Raw < inside <title>: {inner_title}"
    assert ">" not in inner_title, f"Raw > inside <title>: {inner_title}"

    h1_m = re.search(r"<h1>(.*?)</h1>", html, re.DOTALL | re.IGNORECASE)
    assert h1_m is not None
    inner_h1 = h1_m.group(1)
    assert "<script" not in inner_h1.lower()


# ============================================================================
# R4: Markdown & HTML Artifact Cleanliness (Zero Literal ** and Zero Raw Tags)
# ============================================================================


def test_clean_html_asterisks_adversarial():
    """Verify clean_html_asterisks strips orphan/multiple ** while preserving code/pre/style."""
    cases = [
        # Multiple asterisks
        ("Multiple **** asterisks", "Multiple  asterisks"),
        ("Six ****** asterisks", "Six  asterisks"),
        # Five asterisks: ** + * + bold + ** + * -> * + <strong>bold</strong> + * (zero ** remaining)
        ("Five *****bold***** asterisks", "Five *<strong>bold</strong>* asterisks"),
        # Unpaired asterisks
        ("Unpaired **bold without closing", "Unpaired bold without closing"),
        ("Stray ** at end", "Stray  at end"),
        ("** Stray at start", " Stray at start"),
        # Bold inside quotes
        ('He said, "**This is critical**."', 'He said, "<strong>This is critical</strong>."'),
        ("Speaker: **Lenny Rachitsky** (00:00:00)", "Speaker: <strong>Lenny Rachitsky</strong> (00:00:00)"),
        # Complex punctuation adjacent
        ("(**parenthesized**)", "(<strong>parenthesized</strong>)"),
        ("[**bracketed**]", "[<strong>bracketed</strong>]"),
        ("**bold**! and **bold**?", "<strong>bold</strong>! and <strong>bold</strong>?"),
        # Inside code, pre, style blocks (must be preserved verbatim)
        ("<code>**code asterisks**</code>", "<code>**code asterisks**</code>"),
        ("<pre>**pre asterisks**\n**more**</pre>", "<pre>**pre asterisks**\n**more**</pre>"),
        ("<style>/* **style asterisks** */</style>", "<style>/* **style asterisks** */</style>"),
    ]

    for raw, expected in cases:
        cleaned = clean_html_asterisks(raw)
        assert cleaned == expected, f"Failed for '{raw}': got '{cleaned}', expected '{expected}'"


def test_html_summary_zero_literal_asterisks_and_zero_raw_tags_adversarial():
    """Verify HTML summary generator leaves ZERO literal ** outside code spans and ZERO raw tags."""
    complex_markdown = """
# Complex Summary

Here is a paragraph with **bold text** and stray ** unclosed asterisks.
Quotes: "**Grounded claim**" and parenthesized (**important insight**).
Speaker turned note: **Lenny Rachitsky** (00:02:15): How do you find PMF?

Multiple asterisks: **** and *****five***** in text.

Grouped citations in various formats:
- Standard grouped: [S1, S2, S3]
- Large numbers: [S10, S2]
- Spaces inside brackets: [   S1  ,   S2   ]
- Semicolons: [S1; S2; S4]
- Lowercase: [s1, s2]
- Parentheses form: (S1, S2)
- Nested parentheses: ([S1, S2])
- Trailing period: [S1, S2].
- Trailing comma: [S1, S2],
- Trailing colon: [S1, S2]:

Code blocks with asterisks:
`**bold inside code span**`
```python
x = **asterisks_in_code_block**
```
```
**preserved inside generic fenced block**
```
"""
    citations = [
        {"n": 1, "guest": "Sean Ellis", "title": "PMF", "passage": "**Lenny Rachitsky** (00:00:00): Welcome."},
        {"n": 2, "guest": "Elena Verna", "title": "Growth", "passage": "**Elena Verna** (00:15:20): Look at retention."},
        {"n": 3, "guest": "Ben Williams", "title": "PLG", "passage": "Standard passage without bold"},
        {"n": 4, "guest": "Brian Balfour", "title": "Loops", "passage": "**Brian** (00:10:00): Loops beat funnels."},
        {"n": 10, "guest": "Guest Ten", "title": "Ep 10", "passage": "**Speaker** (01:00:00): Final words."},
    ]

    html = generate_deterministic_html_summary(
        title="Adversarial Cleanliness Report",
        markdown_text=complex_markdown,
        citations=citations,
    )

    # 1. Assert ZERO literal ** outside code, pre, style blocks
    html_no_code = re.sub(r"(<code[^>]*>.*?</code>|<pre[^>]*>.*?</pre>|<style[^>]*>.*?</style>)", "", html, flags=re.DOTALL)
    assert "**" not in html_no_code, f"Found literal ** outside code spans in HTML:\n{html_no_code}"

    # 2. Assert code blocks preserved their asterisks
    assert "**bold inside code span**" in html
    assert "**asterisks_in_code_block**" in html
    assert "**preserved inside generic fenced block**" in html

    # 3. Assert ZERO raw [S..] or [s..] tags in HTML
    assert not re.search(r"\[\s*[sS]\d+", html), f"Found raw [S#] tag in HTML:\n{html}"
    assert not re.search(r"\(\s*[sS]\d+", html), f"Found raw (S#) tag in HTML:\n{html}"

    # 4. Verify all citations converted to superscripts
    for n in [1, 2, 3, 4, 10]:
        assert f'<a href="#source-S{n}">[{n}]</a>' in html

    # 5. Verify passage snippet inside sources list has ZERO literal **
    sources_section = html[html.find('<ol class="sources-list">'):]
    assert "**" not in sources_section, f"Found ** in sources section:\n{sources_section}"


def test_markdown_summary_zero_raw_tags_adversarial():
    """Verify Markdown summary generator leaves ZERO raw [S..] tags in body or ## Sources."""
    complex_markdown = """
Key findings across episodes [S1, S2, S3] and follow-up [S10, S2]:
- Note A with spaces: [   S1  ,   S2   ]
- Note B with semicolon: [S1; S3]
- Note C with parentheses: (S1, S2)
- Note D with trailing period: [S1, S2].
- Note E with lowercase: [s1, s3]
"""
    citations = [
        {"n": 1, "guest": "Sean Ellis", "title": "PMF"},
        {"n": 2, "guest": "Elena Verna", "title": "Growth"},
        {"n": 3, "guest": "Ben Williams", "title": "PLG"},
        {"n": 10, "guest": "Guest Ten", "title": "Ep 10"},
    ]

    md = generate_deterministic_markdown_summary(
        title="Markdown Cleanliness Test",
        markdown_text=complex_markdown,
        citations=citations,
    )

    # 1. Assert ZERO raw [S..] or [s..] tags in entire markdown doc
    assert not re.search(r"\[\s*[sS]\d+", md), f"Found raw [S#] tag in Markdown:\n{md}"
    assert not re.search(r"\(\s*\[?\s*[sS]\d+", md), f"Found raw (S#) tag in Markdown:\n{md}"

    # 2. Assert converted to markdown links
    assert "[1](#source-S1)" in md
    assert "[2](#source-S2)" in md
    assert "[3](#source-S3)" in md
    assert "[10](#source-S10)" in md

    # 3. Assert ## Sources section does NOT have [S#] tags before guest
    sources_text = md.split("## Sources")[-1]
    assert "[S1]" not in sources_text
    assert "[S2]" not in sources_text
    assert "[S3]" not in sources_text
    assert "[S10]" not in sources_text


# ============================================================================
# R5: Markdown & HTML Citation Index Sorting (Adversarial Stress Suite)
# ============================================================================


def test_markdown_and_html_citation_sorting_reversed_array():
    """Verify strictly numeric sorting when citations are in reversed order: [5, 4, 3, 2, 1]."""
    citations = [
        {"n": 5, "guest": "Guest 5", "title": "Ep 5", "passage": "Passage 5"},
        {"n": 4, "guest": "Guest 4", "title": "Ep 4", "passage": "Passage 4"},
        {"n": 3, "guest": "Guest 3", "title": "Ep 3", "passage": "Passage 3"},
        {"n": 2, "guest": "Guest 2", "title": "Ep 2", "passage": "Passage 2"},
        {"n": 1, "guest": "Guest 1", "title": "Ep 1", "passage": "Passage 1"},
    ]

    # Markdown test
    md = generate_deterministic_markdown_summary("Reversed Test", "Body [S1, S5]", citations)
    sources_section = md.split("## Sources")[-1]
    sources_text = sources_section
    md_numbers = [int(m.group(1)) for m in re.finditer(r"^(\d+)\.", sources_text, re.MULTILINE)]
    assert md_numbers == [1, 2, 3, 4, 5], f"Markdown sorting failed for reversed array: {md_numbers}"

    # HTML test
    html = generate_deterministic_html_summary("Reversed Test", "Body [S1, S5]", citations)
    html_numbers = [int(m.group(1)) for m in re.finditer(r'<li id="source-S(\d+)">', html)]
    assert html_numbers == [1, 2, 3, 4, 5], f"HTML sorting failed for reversed array: {html_numbers}"


def test_markdown_and_html_citation_sorting_random_shuffle():
    """Verify strictly numeric sorting when citations are randomly shuffled: [3, 1, 4, 2, 5]."""
    citations = [
        {"n": 3, "guest": "Guest 3", "title": "Ep 3"},
        {"n": 1, "guest": "Guest 1", "title": "Ep 1"},
        {"n": 4, "guest": "Guest 4", "title": "Ep 4"},
        {"n": 2, "guest": "Guest 2", "title": "Ep 2"},
        {"n": 5, "guest": "Guest 5", "title": "Ep 5"},
    ]

    # Markdown test
    md = generate_deterministic_markdown_summary("Shuffle Test", "Body [S1]", citations)
    sources_section = md.split("## Sources")[-1]
    md_numbers = [int(m.group(1)) for m in re.finditer(r"^(\d+)\.", sources_section, re.MULTILINE)]
    assert md_numbers == [1, 2, 3, 4, 5], f"Markdown sorting failed for shuffled array: {md_numbers}"

    # HTML test
    html = generate_deterministic_html_summary("Shuffle Test", "Body [S1]", citations)
    html_numbers = [int(m.group(1)) for m in re.finditer(r'<li id="source-S(\d+)">', html)]
    assert html_numbers == [1, 2, 3, 4, 5], f"HTML sorting failed for shuffled array: {html_numbers}"


def test_citation_sorting_multi_digit_numbers_strictly_numeric():
    """Verify numeric vs lexicographic sorting: [10, 2, 1, 20] must sort as 1, 2, 10, 20."""
    citations = [
        {"n": 10, "guest": "Guest 10", "title": "Ep 10"},
        {"n": 2, "guest": "Guest 2", "title": "Ep 2"},
        {"n": 1, "guest": "Guest 1", "title": "Ep 1"},
        {"n": 20, "guest": "Guest 20", "title": "Ep 20"},
    ]

    # Markdown test
    md = generate_deterministic_markdown_summary("Multi-digit Test", "Body [S1, S20]", citations)
    sources_section = md.split("## Sources")[-1]
    md_numbers = [int(m.group(1)) for m in re.finditer(r"^(\d+)\.", sources_section, re.MULTILINE)]
    assert md_numbers == [1, 2, 10, 20], f"Multi-digit sorting failed (lexicographic error?): {md_numbers}"

    # HTML test
    html = generate_deterministic_html_summary("Multi-digit Test", "Body [S1, S20]", citations)
    html_numbers = [int(m.group(1)) for m in re.finditer(r'<li id="source-S(\d+)">', html)]
    assert html_numbers == [1, 2, 10, 20], f"HTML multi-digit sorting failed: {html_numbers}"


def test_citation_sorting_with_string_numbers_and_objects():
    """Verify sorting handles string 'n' values like '5', '1', '10' and objects."""
    class CitationObj:
        def __init__(self, n, guest, title):
            self.n = n
            self.guest = guest
            self.title = title

    citations = [
        {"n": "5", "guest": "Guest 5", "title": "Ep 5"},
        CitationObj(n="1", guest="Guest 1", title="Ep 1"),
        {"n": "10", "guest": "Guest 10", "title": "Ep 10"},
        CitationObj(n=2, guest="Guest 2", title="Ep 2"),
    ]

    md = generate_deterministic_markdown_summary("Mixed Objects Test", "Body", citations)
    sources_section = md.split("## Sources")[-1]
    md_numbers = [int(m.group(1)) for m in re.finditer(r"^(\d+)\.", sources_section, re.MULTILINE)]
    assert md_numbers == [1, 2, 5, 10], f"Mixed object sorting failed: {md_numbers}"
