"""Comprehensive test suite for chat endpoint and artifact persistence.

Tests:
  - 404 on non-existent session
  - 422 on invalid/empty/oversized payload
  - Zero-LLM immediate refusal on off-topic / low-score queries
  - In-domain grounded Q&A with valid citations
  - Automatic retry when first turn lacks citation tags
  - Exact refusal fallback when second turn also lacks citations
  - Artifact persistence and GET /artifacts/{id} endpoint
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.agent.prompts import EXACT_REFUSAL_MESSAGE
from app.agent.router import Intent
from app.db import get_db_session
from app.llm.base import ChatMessage, ChatResponse, LLMProvider, ProviderHealth
from app.main import app
from app.models import Artifact, Message, Session
from app.rag.retrieval import RetrievalResult
from app.routers.chat import get_chat_embedder, get_chat_provider


# ---------------------------------------------------------------------------
# Test fixtures & mocks
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_disable_sdk_in_unit_tests():
    """Ensure chat endpoint unit tests run through the mock provider rather than live SDK CLI."""
    with patch("app.agent.orchestrator._run_with_sdk", side_effect=RuntimeError("SDK disabled in unit tests")):
        yield



def make_mock_db(session_obj: Optional[Session] = None, history: Optional[List[Any]] = None):
    """Create a mock AsyncSession that returns synchronous Result objects."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    async def fake_refresh(instance):
        if not getattr(instance, "id", None):
            instance.id = uuid.uuid4()
        if not getattr(instance, "created_at", None):
            instance.created_at = datetime.now(timezone.utc)

    mock_db.refresh = AsyncMock(side_effect=fake_refresh)

    def execute_side_effect(stmt):
        stmt_str = str(stmt).lower()
        res = MagicMock()
        if "from sessions" in stmt_str or "sessions.id" in stmt_str:
            res.scalar_one_or_none.return_value = session_obj
        elif "from artifacts" in stmt_str or "artifacts.id" in stmt_str:
            res.scalar_one_or_none.return_value = session_obj
        else:
            res.scalars.return_value.all.return_value = history or []
            res.scalar_one_or_none.return_value = None
        return res

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    return mock_db


class MockLLMProvider:
    """Mock LLMProvider that tracks call count and returns preset responses."""

    def __init__(self, responses: Optional[List[str]] = None):
        self.responses = responses or ["According to the podcast, retention is key [S1]."]
        self.call_count = 0
        self.prompts: List[str] = []

    async def chat(
        self,
        messages: List[ChatMessage],
        *,
        system: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        extra: Optional[Any] = None,
    ) -> ChatResponse:
        self.call_count += 1
        prompt_text = messages[-1].content if messages else ""
        self.prompts.append(prompt_text)

        idx = min(self.call_count - 1, len(self.responses) - 1)
        resp_text = self.responses[idx]
        return ChatResponse(
            content=resp_text,
            input_tokens=120,
            output_tokens=45,
            model="mock-qwen",
        )

    async def embed(self, texts: List[str]) -> List[List[float]]:
        return [[0.1] * 768 for _ in texts]

    async def health(self) -> ProviderHealth:
        return ProviderHealth(ok=True, model="mock-qwen")


class MockEmbedder:
    """Mock embedder returning deterministic 768-dim vector."""

    async def embed_query(self, text: str) -> List[float]:
        return [0.05] * 768

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [[0.05] * 768 for _ in texts]


def make_retrieval_chunk(
    score: float = 0.75,
    title: str = "Growing Startups",
    guest: str = "Elena Verna",
    text: str = "Retention is driven by activation within the first week.",
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=uuid.uuid4(),
        text=text,
        score=score,
        document_slug="elena-verna-growth",
        title=title,
        guest=guest,
        speaker=guest,
        start_char=0,
        end_char=len(text),
        chunk_index=0,
    )


# ---------------------------------------------------------------------------
# Client fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


def test_post_message_session_not_found(client):
    """POST /sessions/{id}/messages returns 404 when session does not exist."""
    fake_session_id = uuid.uuid4()
    mock_db = make_mock_db(session_obj=None)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = override_db
    try:
        resp = client.post(
            f"/sessions/{fake_session_id}/messages",
            json={"content": "What is activation?"},
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"]["code"] == "session_not_found"
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_post_message_empty_content_422(client):
    """POST /sessions/{id}/messages with empty string returns 422."""
    session_id = uuid.uuid4()
    resp = client.post(
        f"/sessions/{session_id}/messages",
        json={"content": ""},
    )
    assert resp.status_code == 422


def test_post_message_oversized_content_422(client):
    """POST /sessions/{id}/messages with content > 4000 chars returns 422."""
    session_id = uuid.uuid4()
    resp = client.post(
        f"/sessions/{session_id}/messages",
        json={"content": "a" * 4001},
    )
    assert resp.status_code == 422


def test_post_message_invalid_uuid_422(client):
    """POST /sessions/invalid-uuid/messages returns 422 validation error."""
    resp = client.post(
        "/sessions/invalid-uuid-string/messages",
        json={"content": "Hello"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Retrieval Threshold & Immediate Refusal (Zero LLM calls)
# ---------------------------------------------------------------------------


def test_immediate_refusal_below_threshold(client):
    """When top retrieval score < 0.58, immediately refuse with ZERO LLM calls."""
    session_id = uuid.uuid4()
    mock_session_obj = Session(
        id=session_id,
        llm_provider="ollama",
        llm_model="qwen2.5:7b",
        created_at=datetime.now(timezone.utc),
    )

    mock_db = make_mock_db(session_obj=mock_session_obj)
    low_chunk = make_retrieval_chunk(score=0.45, text="Irrelevant transcript text.")

    provider = MockLLMProvider()
    embedder = MockEmbedder()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_chat_provider] = lambda: provider
    app.dependency_overrides[get_chat_embedder] = lambda: embedder

    try:
        with patch("app.routers.chat.retrieve", new=AsyncMock(return_value=[low_chunk])):
            resp = client.post(
                f"/sessions/{session_id}/messages",
                json={"content": "How do I bake sourdough bread?"},
            )

        assert resp.status_code == 200
        data = resp.json()

        # Immediate refusal verification
        assert data["message"]["content"] == EXACT_REFUSAL_MESSAGE
        assert data["citations"] == []
        assert data["message"]["role"] == "assistant"

        # Verification that ZERO LLM calls were made!
        assert provider.call_count == 0

        # DB persistence was called
        assert mock_db.commit.called
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_chat_provider, None)
        app.dependency_overrides.pop(get_chat_embedder, None)


# ---------------------------------------------------------------------------
# Grounded Q&A with Valid Citations
# ---------------------------------------------------------------------------


def test_grounded_qa_success(client):
    """When chunks score >= 0.58 and agent cites [S1], citations are attached."""
    session_id = uuid.uuid4()
    mock_session_obj = Session(
        id=session_id,
        llm_provider="ollama",
        llm_model="qwen2.5:7b",
        created_at=datetime.now(timezone.utc),
    )

    mock_db = make_mock_db(session_obj=mock_session_obj)

    high_chunk = make_retrieval_chunk(
        score=0.78,
        title="Elena Verna on B2B PLG",
        guest="Elena Verna",
        text="Retention is heavily driven by activation within the first week.",
    )

    provider = MockLLMProvider(
        responses=["Retention is driven by activation in the first week [S1]."]
    )
    embedder = MockEmbedder()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_chat_provider] = lambda: provider
    app.dependency_overrides[get_chat_embedder] = lambda: embedder

    try:
        with patch("app.routers.chat.retrieve", new=AsyncMock(return_value=[high_chunk])):
            resp = client.post(
                f"/sessions/{session_id}/messages",
                json={"content": "What drives retention in B2B PLG?"},
            )

        assert resp.status_code == 200
        data = resp.json()

        assert "[S1]" in data["message"]["content"]
        assert len(data["citations"]) == 1
        citation = data["citations"][0]
        assert citation["n"] == 1
        assert citation["chunk_id"] == str(high_chunk.chunk_id)
        assert citation["title"] == "Elena Verna on B2B PLG"
        assert citation["guest"] == "Elena Verna"
        assert "Retention is heavily driven" in citation["passage"]
        assert provider.call_count >= 1
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_chat_provider, None)
        app.dependency_overrides.pop(get_chat_embedder, None)


# ---------------------------------------------------------------------------
# Retry on Missing Citations
# ---------------------------------------------------------------------------


def test_retry_on_missing_citations_succeeds_on_second_turn(client):
    """If first turn has zero citations, pipeline retries once with grounding reminder."""
    session_id = uuid.uuid4()
    mock_session_obj = Session(
        id=session_id,
        llm_provider="ollama",
        llm_model="qwen2.5:7b",
        created_at=datetime.now(timezone.utc),
    )

    mock_db = make_mock_db(session_obj=mock_session_obj)
    high_chunk = make_retrieval_chunk(score=0.82)

    # First turn forgets citations; second turn fixes it
    provider = MockLLMProvider(
        responses=[
            "Activation drives retention strongly.",  # No [S#]
            "Activation drives retention strongly [S1].",  # Has [S1]
        ]
    )
    embedder = MockEmbedder()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_chat_provider] = lambda: provider
    app.dependency_overrides[get_chat_embedder] = lambda: embedder

    try:
        with patch("app.routers.chat.retrieve", new=AsyncMock(return_value=[high_chunk])):
            resp = client.post(
                f"/sessions/{session_id}/messages",
                json={"content": "What is activation?"},
            )

        assert resp.status_code == 200
        data = resp.json()

        # Two calls were made (1 original + 1 retry)
        assert provider.call_count == 2
        assert len(data["citations"]) == 1
        assert "[S1]" in data["message"]["content"]
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_chat_provider, None)
        app.dependency_overrides.pop(get_chat_embedder, None)


def test_double_failure_falls_back_to_exact_refusal(client):
    """If retry ALSO fails to provide valid citations, answer is replaced with exact refusal."""
    session_id = uuid.uuid4()
    mock_session_obj = Session(
        id=session_id,
        llm_provider="ollama",
        llm_model="qwen2.5:7b",
        created_at=datetime.now(timezone.utc),
    )

    mock_db = make_mock_db(session_obj=mock_session_obj)
    high_chunk = make_retrieval_chunk(score=0.80)

    # Both turns fail to provide citations
    provider = MockLLMProvider(
        responses=[
            "Hallucinated response without citation.",
            "Still hallucinated without citation.",
        ]
    )
    embedder = MockEmbedder()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_chat_provider] = lambda: provider
    app.dependency_overrides[get_chat_embedder] = lambda: embedder

    try:
        with patch("app.routers.chat.retrieve", new=AsyncMock(return_value=[high_chunk])):
            resp = client.post(
                f"/sessions/{session_id}/messages",
                json={"content": "What is activation?"},
            )

        assert resp.status_code == 200
        data = resp.json()

        assert provider.call_count == 2
        # Exact refusal is enforced
        assert data["message"]["content"] == EXACT_REFUSAL_MESSAGE
        assert data["citations"] == []
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_chat_provider, None)
        app.dependency_overrides.pop(get_chat_embedder, None)


# ---------------------------------------------------------------------------
# Artifacts endpoint tests
# ---------------------------------------------------------------------------


def test_get_artifact_not_found(client):
    """GET /artifacts/{id} returns 404 if artifact does not exist."""
    fake_art_id = uuid.uuid4()
    mock_db = make_mock_db(session_obj=None)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = override_db
    try:
        resp = client.get(f"/artifacts/{fake_art_id}")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "artifact_not_found"
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_get_artifact_success(client):
    """GET /artifacts/{id} returns 200 with artifact data."""
    art_id = uuid.uuid4()
    sess_id = uuid.uuid4()
    mock_art = Artifact(
        id=art_id,
        session_id=sess_id,
        type="html",
        title="Retention Framework",
        content="<div>Sample HTML</div>",
        created_at=datetime.now(timezone.utc),
    )

    mock_db = make_mock_db(session_obj=mock_art)

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = override_db
    try:
        resp = client.get(f"/artifacts/{art_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(art_id)
        assert data["title"] == "Retention Framework"
        assert data["content"] == "<div>Sample HTML</div>"
        assert data["type"] == "html"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
