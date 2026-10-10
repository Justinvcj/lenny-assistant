"""Tests for the /sessions API endpoints."""

import uuid
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_get_nonexistent_session_404():
    """Verify getting a non-existent session returns 404 with session_not_found code."""
    fake_id = uuid.uuid4()
    with patch("app.routers.sessions.get_db_session") as mock_db:
        mock_session = AsyncMock()
        mock_db.return_value = mock_session
        mock_session.execute.return_value.scalar_one_or_none.return_value = None

        response = client.get(f"/sessions/{fake_id}")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "session_not_found"


def test_delete_nonexistent_session_404():
    """Verify deleting a non-existent session returns 404."""
    fake_id = uuid.uuid4()
    with patch("app.routers.sessions.get_db_session") as mock_db:
        mock_session = AsyncMock()
        mock_db.return_value = mock_session
        mock_session.execute.return_value.scalar_one_or_none.return_value = None

        response = client.delete(f"/sessions/{fake_id}")
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "session_not_found"


def test_invalid_uuid_returns_422():
    """Verify invalid UUID returns 422 standard validation error."""
    response = client.get("/sessions/not-a-valid-uuid")
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "validation_error"


def test_create_session_success():
    """Verify creating a session returns 201 with session details."""
    session_id = uuid.uuid4()
    with patch("app.routers.sessions.get_db_session") as mock_db:
        mock_session = AsyncMock()
        mock_db.return_value = mock_session

        async def fake_refresh(instance):
            instance.id = session_id

        mock_session.refresh.side_effect = fake_refresh

        response = client.post("/sessions", json={"title": "Test Chat"})
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test Chat"
        assert "llm_provider" in data
        assert "llm_model" in data
