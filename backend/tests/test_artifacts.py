"""Tests for the /artifacts API endpoints and artifact validation."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
import pytest

from app.db import get_db_session
from app.main import app
from app.models import Artifact


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
            instance.created_at = datetime.now(timezone.utc)

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
        created_at=datetime.now(timezone.utc),
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
    from app.agent.tools import build_tools
    from app.agent.router import Intent

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
