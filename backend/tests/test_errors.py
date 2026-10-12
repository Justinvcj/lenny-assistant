"""Tests for global exception handling and error envelopes."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError, OperationalError

try:
    import psycopg
    HAS_PSYCOPG = True
except ImportError:
    HAS_PSYCOPG = False

from app.db import get_db_session
from app.errors import AppException
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_operational_error_global_handler_returns_503():
    """Verify that an OperationalError raised during a request returns HTTP 503 db_unavailable."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=OperationalError(
            statement="SELECT 1",
            params={},
            orig=Exception("connection to server at 'db' failed: Connection refused"),
        )
    )

    async def _override():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override
    try:
        response = client.get("/sessions")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "db_unavailable"
        assert data["error"]["message"] == "Database service is temporarily unavailable"
        assert data["error"]["status_code"] == 503
        # Ensure no internal error trace or connection details leak
        assert "Connection refused" not in response.text
        assert "SELECT 1" not in response.text
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_dbapi_error_global_handler_returns_503():
    """Verify that a general DBAPIError returns HTTP 503 with standard envelope."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=DBAPIError(
            statement="SELECT * FROM sessions",
            params={},
            orig=Exception("server closed the connection unexpectedly"),
        )
    )

    async def _override():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override
    try:
        response = client.get("/sessions")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data["error"]["code"] == "db_unavailable"
        assert data["error"]["message"] == "Database service is temporarily unavailable"
        assert data["error"]["status_code"] == 503
        assert "server closed the connection unexpectedly" not in response.text
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_post_sessions_db_disconnect_returns_503():
    """Verify that POST /sessions returns HTTP 503 when DB fails during commit."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock(
        side_effect=OperationalError(
            statement="INSERT INTO sessions ...",
            params={},
            orig=Exception("could not connect to server: Connection refused"),
        )
    )

    async def _override():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override
    try:
        response = client.post("/sessions", json={"title": "Test Session"})
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data["error"]["code"] == "db_unavailable"
        assert data["error"]["message"] == "Database service is temporarily unavailable"
        assert data["error"]["status_code"] == 503
        assert "Connection refused" not in response.text
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_post_chat_message_db_disconnect_returns_503():
    """Verify that POST /sessions/{id}/messages returns HTTP 503 when DB fails."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=OperationalError(
            statement="SELECT ...",
            params={},
            orig=Exception("terminating connection due to administrator command"),
        )
    )

    async def _override():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override
    try:
        fake_session_id = str(uuid.uuid4())
        response = client.post(
            f"/sessions/{fake_session_id}/messages",
            json={"content": "Hello Lenny"},
        )
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data["error"]["code"] == "db_unavailable"
        assert data["error"]["message"] == "Database service is temporarily unavailable"
        assert data["error"]["status_code"] == 503
        assert "administrator command" not in response.text
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_driver_psycopg_error_returns_503():
    """Verify that direct driver psycopg OperationalError returns HTTP 503."""
    if not HAS_PSYCOPG:
        pytest.skip("psycopg not installed")

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=psycopg.OperationalError("connection to server was lost")
    )

    async def _override():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override
    try:
        response = client.get("/sessions")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data["error"]["code"] == "db_unavailable"
        assert data["error"]["message"] == "Database service is temporarily unavailable"
        assert data["error"]["status_code"] == 503
        assert "connection to server was lost" not in response.text
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_app_exception_envelope_consistency():
    """Verify that AppException returns the standard envelope format."""
    from fastapi import APIRouter

    test_router = APIRouter()

    @test_router.get("/test-custom-app-error")
    def _raise_app_error():
        raise AppException(
            code="custom_forbidden",
            message="You do not have access",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    app.include_router(test_router)
    try:
        response = client.get("/test-custom-app-error")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert data["error"]["code"] == "custom_forbidden"
        assert data["error"]["message"] == "You do not have access"
        assert data["error"]["status_code"] == 403
    finally:
        app.routes[:] = [r for r in app.routes if getattr(r, "path", None) != "/test-custom-app-error"]


def test_unhandled_exception_does_not_leak_traceback():
    """Verify that unexpected exceptions return HTTP 500 without leaking tracebacks."""
    from fastapi import APIRouter

    test_router = APIRouter()

    @test_router.get("/test-crash")
    def _raise_runtime_error():
        raise RuntimeError("super_secret_internal_crash_details")

    app.include_router(test_router)
    try:
        response = client.get("/test-crash")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()
        assert data["error"]["code"] == "internal_server_error"
        assert data["error"]["message"] == "An unexpected internal server error occurred"
        assert data["error"]["status_code"] == 500
        assert "super_secret_internal_crash_details" not in response.text
    finally:
        app.routes[:] = [r for r in app.routes if getattr(r, "path", None) != "/test-crash"]
