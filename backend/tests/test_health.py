"""Tests for the /health and /config endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_config_endpoint():
    """Verify /config returns provider and model info without secrets."""
    response = client.get("/config")
    assert response.status_code == 200
    data = response.json()
    assert "provider" in data
    assert "model" in data
    assert "embedding_model" in data
    assert "embedding_dim" in data
    assert "anthropic_api_key" not in data


@pytest.mark.asyncio
async def test_health_ok_when_services_healthy():
    """Verify /health returns 200 and ok status when DB and Ollama are reachable."""
    with patch("app.routers.health.httpx.AsyncClient") as mock_client_cls, \
         patch("app.db.async_session_factory") as mock_session_factory:

        # Mock DB
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_res = MagicMock()
        mock_res.scalar.return_value = 42
        mock_session.execute.return_value = mock_res

        # Mock Ollama tags
        mock_http = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [{"name": "qwen2.5:7b"}, {"name": "nomic-embed-text"}]
        }
        mock_http.get.return_value = mock_resp
        mock_client_cls.return_value.__aenter__.return_value = mock_http

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"]["connected"] is True
        assert data["ollama"]["reachable"] is True


@pytest.mark.asyncio
async def test_health_503_when_database_down():
    """Verify /health returns 503 service unavailable when the database is unreachable."""
    with patch("app.db.async_session_factory") as mock_session_factory:
        mock_session_factory.return_value.__aenter__.side_effect = Exception("DB connection timeout")

        response = client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"]["connected"] is False


@pytest.mark.asyncio
async def test_health_degraded_when_ollama_unreachable():
    """Verify /health returns 200 degraded when Ollama is unreachable but DB is healthy."""
    with patch("app.routers.health.httpx.AsyncClient") as mock_client_cls, \
         patch("app.db.async_session_factory") as mock_session_factory:

        mock_session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar.return_value = 42
        mock_session.execute.return_value = mock_res
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        mock_http = AsyncMock()
        mock_http.get.side_effect = Exception("Connection refused")
        mock_client_cls.return_value.__aenter__.return_value = mock_http

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"]["connected"] is True
        assert data["ollama"]["reachable"] is False


@pytest.mark.asyncio
async def test_health_reports_ingested_false_when_knowledge_base_empty():
    """Verify /health reports ingested=false when vector_count is 0 without crashing."""
    with patch("app.routers.health.httpx.AsyncClient") as mock_client_cls, \
         patch("app.db.async_session_factory") as mock_session_factory:

        mock_session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar.return_value = 0  # 0 chunks
        mock_session.execute.return_value = mock_res
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        mock_http = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [{"name": "qwen2.5:7b"}, {"name": "nomic-embed-text"}]
        }
        mock_http.get.return_value = mock_resp
        mock_client_cls.return_value.__aenter__.return_value = mock_http

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["ingested"] is False
        assert data["database"]["ingested"] is False
        assert data["database"]["vector_count"] == 0


@pytest.mark.asyncio
async def test_health_reports_ingested_true_when_chunks_exist():
    """Verify /health reports ingested=true when vector_count > 0."""
    with patch("app.routers.health.httpx.AsyncClient") as mock_client_cls, \
         patch("app.db.async_session_factory") as mock_session_factory:

        mock_session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar.return_value = 1500
        mock_session.execute.return_value = mock_res
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        mock_http = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [{"name": "qwen2.5:7b"}, {"name": "nomic-embed-text"}]
        }
        mock_http.get.return_value = mock_resp
        mock_client_cls.return_value.__aenter__.return_value = mock_http

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["ingested"] is True
        assert data["database"]["ingested"] is True
        assert data["database"]["vector_count"] == 1500


@pytest.mark.asyncio
async def test_health_anthropic_degraded_missing_api_key(monkeypatch):
    """When LLM_PROVIDER=anthropic and key is missing, /health returns degraded with reason='missing_api_key'."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    with patch("app.db.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar.return_value = 100
        mock_session.execute.return_value = mock_res
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["reason"] == "missing_api_key"
        assert data["provider"]["reason"] == "missing_api_key"
        assert data["provider"]["ok"] is False


@pytest.mark.asyncio
async def test_health_anthropic_degraded_invalid_api_key(monkeypatch):
    """When LLM_PROVIDER=anthropic and key is invalid, /health returns degraded with reason='invalid_api_key'."""
    from app.config import get_settings
    from app.llm.base import ProviderHealth

    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "invalid-test-key")

    with patch("app.db.async_session_factory") as mock_session_factory, \
         patch("app.llm.factory.get_provider") as mock_get_provider:

        mock_session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar.return_value = 100
        mock_session.execute.return_value = mock_res
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        mock_provider = AsyncMock()
        mock_provider.health.return_value = ProviderHealth(
            ok=False, model="claude-3-5-sonnet-20241022", error="invalid_api_key"
        )
        mock_get_provider.return_value = mock_provider

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["reason"] == "invalid_api_key"
        assert data["provider"]["reason"] == "invalid_api_key"
        assert data["provider"]["ok"] is False


@pytest.mark.asyncio
async def test_health_anthropic_ok_when_valid_key(monkeypatch):
    """When LLM_PROVIDER=anthropic and provider is healthy, /health returns ok."""
    from app.config import get_settings
    from app.llm.base import ProviderHealth

    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "valid-key-xyz")

    with patch("app.db.async_session_factory") as mock_session_factory, \
         patch("app.llm.factory.get_provider") as mock_get_provider:

        mock_session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar.return_value = 100
        mock_session.execute.return_value = mock_res
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        mock_provider = AsyncMock()
        mock_provider.health.return_value = ProviderHealth(
            ok=True, model="claude-3-5-sonnet-20241022"
        )
        mock_get_provider.return_value = mock_provider

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "reason" not in data or data["reason"] is None
        assert data["provider"]["ok"] is True
