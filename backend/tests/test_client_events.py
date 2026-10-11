"""Tests for /client-events endpoint and artifact creation logging."""

import json
import logging
import uuid
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app

client = TestClient(app)


def test_client_events_records_event_and_logs_json(caplog):
    """POST /client-events logs single structured JSON line and returns 204."""
    with caplog.at_level(logging.INFO, logger="client_events"):
        payload = {
            "type": "artifact_render_error",
            "artifact_id": str(uuid.uuid4()),
            "reason": "DOMPurify rendering exception: invalid markup",
        }
        response = client.post("/client-events", json=payload)
        assert response.status_code == 204

        # Check caplog for structured JSON line
        matching = [
            rec for rec in caplog.records
            if rec.name == "client_events" and "client_event" in rec.message
        ]
        assert len(matching) >= 1
        logged_data = json.loads(matching[0].message)
        assert logged_data["event"] == "client_event"
        assert logged_data["type"] == payload["type"]
        assert logged_data["artifact_id"] == payload["artifact_id"]
        assert logged_data["reason"] == payload["reason"]


def test_client_events_validation_error_on_missing_fields():
    """POST /client-events returns 422 if required fields are missing."""
    response = client.post("/client-events", json={"artifact_id": "test"})
    assert response.status_code == 422


def test_artifact_creation_logs_type_and_bytes(caplog):
    """POST /artifacts logs creation with type and byte size."""
    with caplog.at_level(logging.INFO):
        with patch("app.routers.artifacts.get_db_session") as mock_db_dep:
            mock_session = AsyncMock()
            app.dependency_overrides[mock_db_dep] = lambda: mock_session

            # Also mock the database session directly
            with patch("app.db.async_session_factory") as mock_factory:
                mock_sess = AsyncMock()
                mock_factory.return_value.__aenter__.return_value = mock_sess

                body = {
                    "session_id": str(uuid.uuid4()),
                    "type": "markdown",
                    "title": "Observability Test Artifact",
                    "content": "# Test content with exact bytes",
                }
                response = client.post("/artifacts", json=body)
                assert response.status_code == 201

                expected_bytes = len(body["content"].encode("utf-8"))
                matching_logs = [
                    rec.message for rec in caplog.records
                    if "Artifact created:" in rec.message
                ]
                assert len(matching_logs) >= 1
                assert f"type=markdown bytes={expected_bytes}" in matching_logs[0]

        app.dependency_overrides.clear()
