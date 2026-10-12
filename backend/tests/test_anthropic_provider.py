"""Unit and integration tests for Anthropic provider graceful startup, health reporting, and 502 error envelopes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest
from app.agent.orchestrator import run_agent
from app.agent.router import Intent
from app.config import get_settings
from app.db import get_db_session
from app.errors import AppException
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import ChatMessage
from app.main import app
from app.models import Session
from app.rag.retrieval import RetrievalResult
from app.routers.chat import get_chat_provider
from fastapi.testclient import TestClient

client = TestClient(app)


def test_anthropic_init_graceful_missing_key(monkeypatch):
    """When api_key is missing or empty, AnthropicProvider.__init__ must NOT raise RuntimeError."""
    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    # Instantiation with None or empty string must succeed gracefully
    p1 = AnthropicProvider(api_key=None)
    assert p1._api_key == ""
    assert p1._client is None

    p2 = AnthropicProvider(api_key="")
    assert p2._api_key == ""
    assert p2._client is None


def test_anthropic_init_with_key():
    """When api_key is provided, AnthropicProvider initializes client normally."""
    p = AnthropicProvider(api_key="sk-ant-test-key-123", model="claude-3-5-sonnet-20241022")
    assert p._api_key == "sk-ant-test-key-123"
    assert p._client is not None
    assert p._model == "claude-3-5-sonnet-20241022"


@pytest.mark.asyncio
async def test_anthropic_health_missing_key():
    """When API key is missing, health check reports ok=False with error='missing_api_key'."""
    p = AnthropicProvider(api_key="")
    h = await p.health()
    assert h.ok is False
    assert h.error == "missing_api_key"
    assert h.model == "claude-3-5-sonnet-20241022"


@pytest.mark.asyncio
async def test_anthropic_health_invalid_key():
    """When API key is invalid, health check reports ok=False with error='invalid_api_key'."""
    p = AnthropicProvider(api_key="invalid-key-xyz")
    mock_models = MagicMock()
    # Simulate Anthropic 401 AuthenticationError
    fake_resp = MagicMock()
    fake_resp.status_code = 401
    mock_models.list = AsyncMock(
        side_effect=anthropic.AuthenticationError(
            message="Error code: 401 - {'type': 'error', 'error': {'type': 'authentication_error', 'message': 'invalid x-api-key'}}",
            response=fake_resp,
            body={"error": {"type": "authentication_error", "message": "invalid x-api-key"}},
        )
    )
    p._client.models = mock_models

    h = await p.health()
    assert h.ok is False
    assert h.error == "invalid_api_key"


@pytest.mark.asyncio
async def test_anthropic_health_valid_key_success():
    """When credentials are valid, health check reports ok=True."""
    p = AnthropicProvider(api_key="valid-key-xyz")
    mock_models = MagicMock()
    mock_models.list = AsyncMock(return_value=[MagicMock(id="claude-3-5-sonnet-20241022")])
    p._client.models = mock_models

    h = await p.health()
    assert h.ok is True
    assert h.error is None


@pytest.mark.asyncio
async def test_anthropic_chat_missing_key_raises_502():
    """Calling chat() on AnthropicProvider with missing key raises 502 bad_gateway AppException."""
    p = AnthropicProvider(api_key="")
    with pytest.raises(AppException) as exc_info:
        await p.chat([ChatMessage(role="user", content="Hello")])

    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "bad_gateway"
    assert "Anthropic API key is not configured" in exc_info.value.message


@pytest.mark.asyncio
async def test_anthropic_chat_invalid_key_raises_502():
    """Calling chat() on AnthropicProvider with invalid key raises 502 bad_gateway AppException."""
    p = AnthropicProvider(api_key="invalid-test-key")
    fake_resp = MagicMock()
    fake_resp.status_code = 401
    p._client.messages.create = AsyncMock(
        side_effect=anthropic.AuthenticationError(
            message="401 authentication failed",
            response=fake_resp,
            body={"error": {"message": "invalid api key"}},
        )
    )

    with pytest.raises(AppException) as exc_info:
        await p.chat([ChatMessage(role="user", content="Hello")])

    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "bad_gateway"
    assert "Anthropic authentication failed. Invalid API key." in exc_info.value.message


@pytest.mark.asyncio
async def test_orchestrator_does_not_mask_auth_error_into_refusal(monkeypatch):
    """Orchestrator must re-raise 502 AppException rather than returning a 200 refusal message."""
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "invalid-test-key")

    p = AnthropicProvider(api_key="invalid-test-key")
    fake_resp = MagicMock()
    fake_resp.status_code = 401
    p._client.messages.create = AsyncMock(
        side_effect=anthropic.AuthenticationError(
            message="401 unauthorized",
            response=fake_resp,
            body={"error": {"message": "invalid api key"}},
        )
    )

    with pytest.raises(AppException) as exc_info:
        await run_agent(
            intent=Intent.QA,
            system_prompt="Test prompt",
            user_message="How do I know if I have PMF?",
            provider=p,
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "bad_gateway"


def test_chat_endpoint_missing_anthropic_key_returns_clean_502_envelope(monkeypatch):
    """POST /sessions/{id}/messages returns clean HTTP 502 envelope when Anthropic key is missing."""
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    session_id = uuid.uuid4()
    mock_session_obj = Session(
        id=session_id,
        llm_provider="anthropic",
        llm_model="claude-3-5-sonnet-20241022",
        created_at=datetime.now(UTC),
    )

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    async def fake_refresh(instance):
        if not getattr(instance, "id", None):
            instance.id = uuid.uuid4()
        if not getattr(instance, "created_at", None):
            instance.created_at = datetime.now(UTC)

    mock_db.refresh = AsyncMock(side_effect=fake_refresh)

    def execute_side_effect(stmt):
        stmt_str = str(stmt).lower()
        res = MagicMock()
        if "from sessions" in stmt_str or "sessions.id" in stmt_str:
            res.scalar_one_or_none.return_value = mock_session_obj
        else:
            res.scalars.return_value.all.return_value = []
            res.scalar_one_or_none.return_value = None
        return res

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)

    async def override_db():
        yield mock_db

    provider = AnthropicProvider(api_key="")

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_chat_provider] = lambda: provider
    try:
        resp = client.post(
            f"/sessions/{session_id}/messages",
            json={"content": "How do I know if I have PMF?"},
        )
        assert resp.status_code == 502
        data = resp.json()

        # Strict assertion of standard error envelope
        assert "error" in data
        assert data["error"]["code"] == "bad_gateway"
        assert data["error"]["status_code"] == 502
        assert "Anthropic API key is not configured" in data["error"]["message"]
        # Assert zero stack traces
        assert "traceback" not in data
        assert "stack" not in data
        assert "Traceback" not in resp.text
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_chat_provider, None)


def test_chat_endpoint_invalid_anthropic_key_returns_clean_502_envelope(monkeypatch):
    """POST /sessions/{id}/messages returns clean HTTP 502 envelope when Anthropic key is invalid."""
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "invalid-test-key")

    session_id = uuid.uuid4()
    mock_session_obj = Session(
        id=session_id,
        llm_provider="anthropic",
        llm_model="claude-3-5-sonnet-20241022",
        created_at=datetime.now(UTC),
    )

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    async def fake_refresh(instance):
        if not getattr(instance, "id", None):
            instance.id = uuid.uuid4()
        if not getattr(instance, "created_at", None):
            instance.created_at = datetime.now(UTC)

    mock_db.refresh = AsyncMock(side_effect=fake_refresh)

    def execute_side_effect(stmt):
        stmt_str = str(stmt).lower()
        res = MagicMock()
        if "from sessions" in stmt_str or "sessions.id" in stmt_str:
            res.scalar_one_or_none.return_value = mock_session_obj
        else:
            res.scalars.return_value.all.return_value = []
            res.scalar_one_or_none.return_value = None
        return res

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)

    async def override_db():
        yield mock_db

    provider = AnthropicProvider(api_key="invalid-test-key")
    fake_resp = MagicMock()
    fake_resp.status_code = 401
    provider._client.messages.create = AsyncMock(
        side_effect=anthropic.AuthenticationError(
            message="401 unauthorized",
            response=fake_resp,
            body={"error": {"message": "invalid api key"}},
        )
    )

    high_chunk = RetrievalResult(
        chunk_id=uuid.uuid4(),
        text="PMF is when customers pull your product.",
        score=0.85,
        document_slug="pmf-guide",
        title="PMF Guide",
        guest="Marc Andreessen",
        speaker="Marc Andreessen",
        start_char=0,
        end_char=40,
        chunk_index=0,
    )

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_chat_provider] = lambda: provider

    try:
        with patch("app.routers.chat.retrieve", new=AsyncMock(return_value=[high_chunk])):
            resp = client.post(
                f"/sessions/{session_id}/messages",
                json={"content": "How do I know if I have PMF?"},
            )
        assert resp.status_code == 502
        data = resp.json()

        # Strict assertion of standard error envelope
        assert "error" in data
        assert data["error"]["code"] == "bad_gateway"
        assert data["error"]["status_code"] == 502
        assert "Anthropic authentication failed. Invalid API key." in data["error"]["message"]
        # Assert zero stack traces
        assert "traceback" not in data
        assert "stack" not in data
        assert "Traceback" not in resp.text
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_chat_provider, None)
