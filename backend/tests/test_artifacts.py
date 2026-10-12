"""Tests for the /artifacts API endpoints and artifact validation."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.db import get_db_session
from app.main import app
from app.models import Artifact
from fastapi.testclient import TestClient


def make_mock_db(artifact_obj=None):
    """Create a mock AsyncSession using dependency_overrides pattern."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.delete = AsyncMock()

    async def fake_refresh(instance):
        if not getattr(instance, "id", None):
            instance.id = uuid.uuid4()
        if not getattr(instance, "created_at", None):
            instance.created_at = datetime.now(UTC)

    mock_db.refresh = AsyncMock(side_effect=fake_refresh)

    def execute_side_effect(stmt):
        res = MagicMock()
        res.scalar_one_or_none.return_value = artifact_obj
        res.scalars.return_value.all.return_value = [artifact_obj] if artifact_obj else []
        return res

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    return mock_db


def _override_with(mock_db):
    async def _override():
        yield mock_db
    return _override


def test_get_artifact_success():
    """Verify GET /artifacts/{id} returns artifact details when found."""
    art_id = uuid.uuid4()
    sess_id = uuid.uuid4()
    mock_art = Artifact(
        id=art_id,
        session_id=sess_id,
        type="html",
        title="Test One-Pager",
        content="<h1>Grounded One-Pager</h1>",
        created_at=datetime.now(UTC),
    )
    mock_db = make_mock_db(artifact_obj=mock_art)
    app.dependency_overrides[get_db_session] = _override_with(mock_db)
    try:
        client = TestClient(app)
        res = client.get(f"/artifacts/{art_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == str(art_id)
        assert data["title"] == "Test One-Pager"
        assert data["type"] == "html"
        assert data["content"] == "<h1>Grounded One-Pager</h1>"
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_get_artifact_not_found_404():
    """Verify GET /artifacts/{id} returns 404 when artifact does not exist."""
    fake_id = uuid.uuid4()
    mock_db = make_mock_db(artifact_obj=None)
    app.dependency_overrides[get_db_session] = _override_with(mock_db)
    try:
        client = TestClient(app)
        res = client.get(f"/artifacts/{fake_id}")
        assert res.status_code == 404
        data = res.json()
        assert data["error"]["code"] == "artifact_not_found"
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_create_artifact_success():
    """Verify POST /artifacts creates artifact and returns 201."""
    sess_id = uuid.uuid4()
    mock_db = make_mock_db()
    app.dependency_overrides[get_db_session] = _override_with(mock_db)
    try:
        client = TestClient(app)
        res = client.post(
            "/artifacts",
            json={
                "session_id": str(sess_id),
                "title": "Ship 30 Essay",
                "type": "markdown",
                "content": "# Compelling Essay\n\nGrounded content here.",
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["title"] == "Ship 30 Essay"
        assert data["type"] == "markdown"
        assert "id" in data
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_create_artifact_oversized_413():
    """Verify POST /artifacts with content > 200KB returns 413 artifact_too_large."""
    sess_id = uuid.uuid4()
    mock_db = make_mock_db()
    app.dependency_overrides[get_db_session] = _override_with(mock_db)
    try:
        client = TestClient(app)
        oversized_content = "A" * 200_001
        res = client.post(
            "/artifacts",
            json={
                "session_id": str(sess_id),
                "title": "Huge Artifact",
                "type": "html",
                "content": oversized_content,
            },
        )
        assert res.status_code == 413
        data = res.json()
        assert data["error"]["code"] == "artifact_too_large"
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_create_artifact_invalid_type_422():
    """Verify POST /artifacts with invalid type (not markdown or html) returns 422."""
    sess_id = uuid.uuid4()
    mock_db = make_mock_db()
    app.dependency_overrides[get_db_session] = _override_with(mock_db)
    try:
        client = TestClient(app)
        res = client.post(
            "/artifacts",
            json={
                "session_id": str(sess_id),
                "title": "Invalid Type",
                "type": "pdf",
                "content": "Some content",
            },
        )
        assert res.status_code == 422
        data = res.json()
        assert data["error"]["code"] == "invalid_artifact_type"
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.mark.asyncio
async def test_tool_create_artifact_invalid_type():
    """Verify create_artifact tool function raises AppException on invalid type."""
    from app.agent.tools import create_artifact
    from app.errors import AppException

    with pytest.raises(AppException) as exc_info:
        await create_artifact("Title", "Content", artifact_type="exe")
    assert exc_info.value.code == "invalid_artifact_type"


def test_normalize_artifact_type_aliases():
    """Verify alias normalization for html and markdown types."""
    from app.agent.tools import normalize_artifact_type

    # HTML aliases
    for alias in ["page", "webpage", "html page", "one-page", "one-pager", "htm", "HTML", "landing", "landing page"]:
        assert normalize_artifact_type(alias) == "html", f"Failed on html alias: {alias}"

    # Markdown aliases
    for alias in ["md", "doc", "document", "markdown", "MARKDOWN", "notes", "report"]:
        assert normalize_artifact_type(alias) == "markdown", f"Failed on markdown alias: {alias}"

    # Fallback default
    assert normalize_artifact_type("") == "html"
    assert normalize_artifact_type(None) == "html"


def test_derive_artifact_type_from_prompt():
    """Verify deterministic derivation of artifact type from user message."""
    from app.routers.chat import derive_artifact_type_from_prompt

    # HTML derivatives
    assert derive_artifact_type_from_prompt("Make a one-page HTML summary of that") == "html"
    assert derive_artifact_type_from_prompt("Create a landing page for PMs") == "html"
    assert derive_artifact_type_from_prompt("Turn this into a one-pager") == "html"
    assert derive_artifact_type_from_prompt("Format as a webpage") == "html"

    # Markdown derivatives
    assert derive_artifact_type_from_prompt("Make a markdown doc summarizing the takeaways") == "markdown"
    assert derive_artifact_type_from_prompt("Write a Ship 30 essay on PMF") == "markdown"
    assert derive_artifact_type_from_prompt("Give me a comparison table in markdown") == "markdown"
    assert derive_artifact_type_from_prompt("Summarize the discussion") == "markdown"


@pytest.mark.asyncio
async def test_tool_create_artifact_handler_normalizes_and_returns_artifact():
    """Verify in-process tool server create_artifact normalizes aliases and returns payload."""
    from app.agent.router import Intent
    from app.agent.tools import build_tools

    tools = build_tools(intent=Intent.ARTIFACT)
    assert len(tools) == 1
    create_art_tool = tools[0]

    # Call with alias 'page'
    res = await create_art_tool.handler({"title": "Test Page", "html": "<h1>Hello</h1>", "artifact_type": "page"})
    assert res.get("is_error") is not True
    assert "_artifact" in res
    assert res["_artifact"]["type"] == "html"
    assert res["_artifact"]["title"] == "Test Page"

    # Call with empty body returns error result for model retry
    err_res = await create_art_tool.handler({"title": "Empty Page", "html": ""})
    assert err_res.get("is_error") is True
    assert "cannot be empty" in err_res["content"][0]["text"]


def test_generate_deterministic_html_summary_zero_asterisks_and_zero_raw_tags():
    """Verify HTML artifacts contain zero literal ** outside code spans and zero raw [S#] tags."""
    import re

    from app.routers.chat import generate_deterministic_html_summary

    markdown_body = (
        "Key takeaways on activation [S1, S2, S5]:\n\n"
        "- **Define Activation Early**: Start with a core metric [S1].\n"
        "- **Team-Based Metrics**: Look at collaboration [S2, S5].\n\n"
        "Here is code with asterisks: `**bold in code**` and block:\n"
        "```python\n"
        "x = **not_valid_py**\n"
        "```\n"
    )
    citations = [
        {"n": 1, "guest": "Sean Ellis", "title": "Hacking Growth", "passage": "**Lenny Rachitsky** (00:00:00): Welcome to the show."},
        {"n": 2, "guest": "Ben Williams", "title": "PLG Juggernaut", "passage": "**Ben Williams** (01:19:28): First of all, what is activation?"},
        {"n": 5, "guest": "Elena Verna", "title": "Product-Led Sales", "passage": "**Elena Verna** (00:30:15): The activation rate is key."},
    ]

    html = generate_deterministic_html_summary(
        title="Activation Guide & Insights",
        markdown_text=markdown_body,
        citations=citations,
    )

    # Code spans / pre blocks can have ** but outside code spans must have zero literal **
    html_without_code = re.sub(r"(<code[^>]*>.*?</code>|<pre[^>]*>.*?</pre>)", "", html, flags=re.DOTALL)
    assert "**" not in html_without_code, f"Found literal ** outside code spans in HTML artifact:\n{html}"

    # Assert zero raw [S#] tags in entire HTML output
    assert not re.search(r"\[sS]\d+", html), f"Found raw [S#] citation tag in HTML artifact:\n{html}"
    assert not re.search(r"\[sS]\d+(?:,\s*[sS]\d+)+", html), f"Found raw grouped citation tag in HTML artifact:\n{html}"

    # Assert superscripts properly rendered
    assert '<a href="#source-S1">[1]</a>' in html
    assert '<a href="#source-S2">[2]</a>' in html
    assert '<a href="#source-S5">[5]</a>' in html

    # Assert code blocks preserved their asterisks inside code spans
    assert "**bold in code**" in html or "**not_valid_py**" in html


def test_generate_deterministic_html_summary_escapes_special_title_characters():
    """Verify HTML summary generator escapes <, >, &, \", ' in <title> and <h1>."""
    from app.routers.chat import generate_deterministic_html_summary

    hostile_title = '</title><script>alert("xss")</script>'
    html = generate_deterministic_html_summary(
        title=hostile_title,
        markdown_text="Safe content [S1].",
        citations=[{"n": 1, "guest": "Lenny", "title": "Ep 1", "passage": "Hello"}],
    )

    assert '</title><script>' not in html
    assert '<script>' not in html
    assert '&lt;/title&gt;&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;' in html


def test_generate_deterministic_markdown_summary_numeric_sorting_and_zero_raw_tags():
    """Verify Markdown artifact citations are sorted strictly numerically and have zero raw [S#] tags."""
    import re

    from app.routers.chat import generate_deterministic_markdown_summary

    markdown_body = "Activation metrics [S1] and retention [S3, S2] with growth loops [S5, S4]."
    # Unsorted citation input list (3, 1, 5, 2, 4)
    citations = [
        {"n": 3, "guest": "Guest 3", "title": "Ep 3"},
        {"n": 1, "guest": "Guest 1", "title": "Ep 1"},
        {"n": 5, "guest": "Guest 5", "title": "Ep 5"},
        {"n": 2, "guest": "Guest 2", "title": "Ep 2"},
        {"n": 4, "guest": "Guest 4", "title": "Ep 4"},
    ]

    md = generate_deterministic_markdown_summary(
        title="Sorted Retention Playbook",
        markdown_text=markdown_body,
        citations=citations,
    )

    # 1. Assert strict numeric order in ## Sources
    sources_section = md.split("## Sources")[-1]
    list_numbers = [int(m.group(1)) for m in re.finditer(r"^(\d+)\.", sources_section, re.MULTILINE)]
    assert list_numbers == [1, 2, 3, 4, 5], f"Citations not strictly numerically sorted: {list_numbers}"

    # 2. Assert zero raw [S..] tags in ## Sources
    assert not re.search(r"\[sS]\d+", sources_section), "Found raw [S#] tag in Markdown ## Sources section"

    # 3. Assert zero raw [S..] tags in entire markdown doc
    assert not re.search(r"\[sS]\d+", md), "Found raw [S#] tag in Markdown artifact content"

    # 4. Assert inline citations converted to markdown links
    assert "[1](#source-S1)" in md
    assert "[2](#source-S2)" in md
    assert "[3](#source-S3)" in md
    assert "[4](#source-S4)" in md
    assert "[5](#source-S5)" in md

