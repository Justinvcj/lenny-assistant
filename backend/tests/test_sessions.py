"""Tests for the /sessions API endpoints."""

import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.db import get_db_session
from app.main import app


def make_mock_db(session_obj=None, sessions_list=None):
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
        if not getattr(instance, "updated_at", None):
            instance.updated_at = datetime.now(timezone.utc)
        if not getattr(instance, "messages", None):
            instance.messages = []

    mock_db.refresh = AsyncMock(side_effect=fake_refresh)

    def execute_side_effect(stmt):
        stmt_str = str(stmt).lower()
        res = MagicMock()
        # GET /sessions/{id} — scalar_one_or_none
        if "sessions" in stmt_str and "where" in stmt_str:
            res.scalar_one_or_none.return_value = session_obj
            res.scalars.return_value.all.return_value = []
        else:
            # list sessions
            res.scalars.return_value.all.return_value = sessions_list or []
            res.scalar_one_or_none.return_value = None
        return res

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    return mock_db


def _override_with(mock_db):
    async def _override():
        yield mock_db
    return _override


def test_get_nonexistent_session_404():
    """Verify getting a non-existent session returns 404 with session_not_found code."""
    fake_id = uuid.uuid4()
    mock_db = make_mock_db(session_obj=None)
    app.dependency_overrides[get_db_session] = _override_with(mock_db)
    try:
        client = TestClient(app)
        response = client.get(f"/sessions/{fake_id}")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "session_not_found"
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_delete_nonexistent_session_404():
    """Verify deleting a non-existent session returns 404."""
    fake_id = uuid.uuid4()
    mock_db = make_mock_db(session_obj=None)
    app.dependency_overrides[get_db_session] = _override_with(mock_db)
    try:
        client = TestClient(app)
        response = client.delete(f"/sessions/{fake_id}")
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "session_not_found"
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_invalid_uuid_returns_422():
    """Verify invalid UUID returns 422 standard validation error."""
    client = TestClient(app)
    response = client.get("/sessions/not-a-valid-uuid")
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "validation_error"


def test_create_session_success():
    """Verify creating a session returns 201 with session details."""
    mock_db = make_mock_db()
    app.dependency_overrides[get_db_session] = _override_with(mock_db)
    try:
        client = TestClient(app)
        response = client.post("/sessions", json={"title": "Test Chat"})
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Chat"
        assert "llm_provider" in data
        assert "llm_model" in data
    finally:
        app.dependency_overrides.pop(get_db_session, None)
