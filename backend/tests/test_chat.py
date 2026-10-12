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
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.agent.prompts import EXACT_REFUSAL_MESSAGE
from app.db import get_db_session
from app.llm.base import ChatMessage, ChatResponse, ProviderHealth
from app.main import app
from app.models import Artifact, Message, Session
from app.rag.retrieval import RetrievalResult
from app.routers.chat import derive_summary_title, get_chat_embedder, get_chat_provider
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Test fixtures & mocks
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_disable_sdk_in_unit_tests():
    """Ensure chat endpoint unit tests run through the mock provider rather than live SDK CLI."""
    with patch("app.agent.orchestrator._run_with_sdk", side_effect=RuntimeError("SDK disabled in unit tests")):
        yield



def make_mock_db(session_obj: Session | None = None, history: list[Any] | None = None):
    """Create a mock AsyncSession that returns synchronous Result objects."""
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
        if "from sessions" in stmt_str or "sessions.id" in stmt_str or "from artifacts" in stmt_str or "artifacts.id" in stmt_str:
            res.scalar_one_or_none.return_value = session_obj
        else:
            res.scalars.return_value.all.return_value = history or []
            res.scalar_one_or_none.return_value = None
        return res

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    return mock_db


class MockLLMProvider:
    """Mock LLMProvider that tracks call count and returns preset responses."""

    def __init__(self, responses: list[str] | None = None):
        self.responses = responses or ["According to the podcast, retention is key [S1]."]
        self.call_count = 0
        self.prompts: list[str] = []

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        extra: Any | None = None,
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

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 768 for _ in texts]

    async def health(self) -> ProviderHealth:
        return ProviderHealth(ok=True, model="mock-qwen")


class MockEmbedder:
    """Mock embedder returning deterministic 768-dim vector."""

    async def embed_query(self, text: str) -> list[float]:
        return [0.05] * 768

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
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
        created_at=datetime.now(UTC),
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
        created_at=datetime.now(UTC),
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
        created_at=datetime.now(UTC),
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
        created_at=datetime.now(UTC),
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
        created_at=datetime.now(UTC),
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


# ---------------------------------------------------------------------------
# Requirement R6 & R7 Multi-Turn Conversation Tests
# ---------------------------------------------------------------------------


def make_dynamic_mock_db(session_obj: Session):
    """Dynamic mock DB that tracks messages and artifacts across turns."""
    messages: list[Message] = []
    artifacts: list[Artifact] = []

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    def fake_add(instance):
        if isinstance(instance, Message):
            if not getattr(instance, "id", None):
                instance.id = uuid.uuid4()
            if not getattr(instance, "created_at", None):
                instance.created_at = datetime.now(UTC)
            messages.append(instance)
        elif isinstance(instance, Artifact):
            if not getattr(instance, "id", None):
                instance.id = uuid.uuid4()
            if not getattr(instance, "created_at", None):
                instance.created_at = datetime.now(UTC)
            artifacts.append(instance)

    mock_db.add = MagicMock(side_effect=fake_add)
    mock_db.flush = AsyncMock()

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
            res.scalar_one_or_none.return_value = session_obj
        elif "from artifacts" in stmt_str:
            if artifacts:
                res.scalar_one_or_none.return_value = artifacts[-1]
            else:
                res.scalar_one_or_none.return_value = None
        elif "from messages" in stmt_str:
            if ("messages.id !=" in stmt_str or "messages.id not in" in stmt_str) and messages:
                res.scalars.return_value.all.return_value = list(messages[:-1])
            else:
                res.scalars.return_value.all.return_value = list(messages)
            res.scalar_one_or_none.return_value = None
        else:
            res.scalars.return_value.all.return_value = []
            res.scalar_one_or_none.return_value = None
        return res

    mock_db.execute = AsyncMock(side_effect=execute_side_effect)
    mock_db.messages = messages
    mock_db.artifacts = artifacts
    return mock_db


def test_derive_summary_title_rejects_command_strings():
    """Verify derive_summary_title rejects artifact/essay command strings and extracts topic from grounded Q."""
    # Command strings must be rejected and fall back to headings or default
    assert (
        derive_summary_title("Make a one-pager (HTML)", "Plain answer text")
        == "Key Growth Insights: Executive Summary"
    )
    assert (
        derive_summary_title("Make a markdown doc summarizing that", "Plain answer text")
        == "Key Growth Insights: Executive Summary"
    )
    assert (
        derive_summary_title("Turn that into a Ship 30 essay", "# Product-Market Fit\nBody text")
        == "Product-Market Fit"
    )
    assert derive_summary_title("Summarize that", "Some content") == "Key Growth Insights: Executive Summary"
    assert (
        derive_summary_title("Please export markdown", "Plain answer text")
        == "Key Growth Insights: Executive Summary"
    )
    assert (
        derive_summary_title("Export as markdown", "Plain answer text")
        == "Key Growth Insights: Executive Summary"
    )
    assert (
        derive_summary_title("Can you export to markdown", "Plain answer text")
        == "Key Growth Insights: Executive Summary"
    )
    assert (
        derive_summary_title("Why is that?", "Plain answer text")
        == "Key Growth Insights: Executive Summary"
    )

    # Grounded questions must extract informative title
    title1 = derive_summary_title("What did Lenny say about finding product-market fit?", "Answer")
    assert title1 == "Finding Product-Market Fit: Summary"
    assert "Make" not in title1

    title2 = derive_summary_title("What drives early retention in SaaS products?", "Answer")
    assert "Early Retention In Saas Products" in title2
    assert "Make" not in title2

    title3 = derive_summary_title("Can you explain how to know if you have product-market fit?", "Answer")
    assert title3 == "Product-Market Fit: Summary"
    assert "Explain" not in title3
    assert "Can You" not in title3


def test_find_last_grounded_qa_exchange_walkback():
    """Verify find_last_grounded_qa_exchange walks backward past intermediate artifact turns and elliptical turns."""
    from app.routers.chat import find_last_grounded_qa_exchange

    t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
    t1 = datetime(2026, 1, 1, 10, 1, 0, tzinfo=UTC)
    t2 = datetime(2026, 1, 1, 10, 2, 0, tzinfo=UTC)
    t3 = datetime(2026, 1, 1, 10, 3, 0, tzinfo=UTC)
    t4 = datetime(2026, 1, 1, 10, 4, 0, tzinfo=UTC)
    t5 = datetime(2026, 1, 1, 10, 5, 0, tzinfo=UTC)

    msg_user_qa = Message(
        id=uuid.uuid4(),
        role="user",
        content="What did Lenny say about finding product-market fit?",
        created_at=t0,
    )
    msg_asst_qa = Message(
        id=uuid.uuid4(),
        role="assistant",
        content="Product-market fit happens when retention curves flatten [S1].",
        citations=[{"chunk_id": str(uuid.uuid4()), "guest": "Peter Specht", "title": "Finding PMF"}],
        intent="qa",
        created_at=t1,
    )
    msg_user_art1 = Message(
        id=uuid.uuid4(),
        role="user",
        content="Make a one-pager (HTML)",
        created_at=t2,
    )
    msg_asst_art1 = Message(
        id=uuid.uuid4(),
        role="assistant",
        content="Your HTML one-pager is ready: 'Finding Product-Market Fit: Summary' (150 words)...",
        citations=[],
        intent="artifact",
        created_at=t3,
    )

    history = [msg_user_qa, msg_asst_qa, msg_user_art1, msg_asst_art1]
    u, a = find_last_grounded_qa_exchange(history)
    assert u is not None and u.content == "What did Lenny say about finding product-market fit?"
    assert a is not None and "retention curves flatten" in a.content

    # Also test walkback past follow-up QA exchange ("Why is that?")
    msg_user_fu = Message(
        id=uuid.uuid4(),
        role="user",
        content="Why is that?",
        created_at=t4,
    )
    msg_asst_fu = Message(
        id=uuid.uuid4(),
        role="assistant",
        content="Because customer retention stabilizes cohorts [S1].",
        citations=[{"chunk_id": str(uuid.uuid4()), "guest": "Peter Specht", "title": "Finding PMF"}],
        intent="qa",
        created_at=t5,
    )
    fu_history = [msg_user_qa, msg_asst_qa, msg_user_fu, msg_asst_fu]
    u2, a2 = find_last_grounded_qa_exchange(fu_history)
    assert u2 is not None and u2.content == "What did Lenny say about finding product-market fit?"
    assert a2 is not None and "customer retention stabilizes cohorts" in a2.content


def test_chained_artifact_requests_retain_original_grounded_title(client):
    """Test sequence: QA answer -> 'Make a one-pager (HTML)' -> 'Make a markdown doc summarizing that'.
    Assert BOTH artifacts carry the title derived from the original QA topic, never from command text.
    """
    session_id = uuid.uuid4()
    mock_session_obj = Session(
        id=session_id,
        llm_provider="ollama",
        llm_model="qwen2.5:7b",
        created_at=datetime.now(UTC),
    )

    mock_db = make_dynamic_mock_db(session_obj=mock_session_obj)

    high_chunk = make_retrieval_chunk(
        score=0.85,
        title="Finding Product-Market Fit",
        guest="Peter Specht",
        text="Lenny explains that finding product-market fit is proven when retention curves flatten into a horizontal line.",
    )

    provider = MockLLMProvider(
        responses=["Product-market fit is proven when retention curves flatten horizontally [S1]."]
    )
    embedder = MockEmbedder()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_chat_provider] = lambda: provider
    app.dependency_overrides[get_chat_embedder] = lambda: embedder

    try:
        # Turn 1: Grounded question
        with patch("app.routers.chat.retrieve", new=AsyncMock(return_value=[high_chunk])):
            resp1 = client.post(
                f"/sessions/{session_id}/messages",
                json={"content": "What did Lenny say about finding product-market fit?"},
            )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert len(data1["citations"]) >= 1
        assert "retention curves flatten" in data1["message"]["content"]

        # Turn 2: Chained HTML artifact command
        with patch("app.routers.chat.retrieve", new=AsyncMock(return_value=[high_chunk])):
            resp2 = client.post(
                f"/sessions/{session_id}/messages",
                json={"content": "Make a one-pager (HTML)"},
            )
        assert resp2.status_code == 200
        data2 = resp2.json()
        art2 = data2.get("artifact")
        assert art2 is not None
        assert art2["type"] == "html"
        # Assert title is derived from original QA topic, NOT command string
        assert art2["title"] == "Finding Product-Market Fit: Summary"
        assert "Make" not in art2["title"]
        assert "One-Pager" not in art2["title"]

        # Turn 3: Chained Markdown artifact command
        with patch("app.routers.chat.retrieve", new=AsyncMock(return_value=[high_chunk])):
            resp3 = client.post(
                f"/sessions/{session_id}/messages",
                json={"content": "Make a markdown doc summarizing that"},
            )
        assert resp3.status_code == 200
        data3 = resp3.json()
        art3 = data3.get("artifact")
        assert art3 is not None
        assert art3["type"] == "markdown"
        # Assert title is derived from original QA topic, NOT command string
        assert art3["title"] == "Finding Product-Market Fit: Summary"
        assert "Make" not in art3["title"]
        assert "Markdown" not in art3["title"]
        assert "Summarizing That" not in art3["title"]

        # Assert BOTH artifacts carry the exact topic-derived title
        assert art2["title"] == art3["title"] == "Finding Product-Market Fit: Summary"

        # Assert base_text for the markdown doc was the grounded answer, NOT the confirmation string
        assert "Your HTML one-pager is ready" not in art3["content"]
        assert "retention curves flatten" in art3["content"].lower()

    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_chat_provider, None)
        app.dependency_overrides.pop(get_chat_embedder, None)


def test_followup_after_out_of_domain_refusal_is_refused(client):
    """When a question is refused for being out-of-domain, an immediate 'Why is that?' follow-up is also immediately refused."""
    session_id = uuid.uuid4()
    mock_session_obj = Session(
        id=session_id,
        llm_provider="ollama",
        llm_model="qwen2.5:7b",
        created_at=datetime.now(UTC),
    )
    mock_db = make_dynamic_mock_db(session_obj=mock_session_obj)

    low_chunk = make_retrieval_chunk(score=0.40, text="Unrelated text")
    provider = MockLLMProvider()
    embedder = MockEmbedder()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_chat_provider] = lambda: provider
    app.dependency_overrides[get_chat_embedder] = lambda: embedder

    try:
        # Turn 1: Out of domain question -> immediate refusal
        with patch("app.routers.chat.retrieve", new=AsyncMock(return_value=[low_chunk])):
            resp1 = client.post(
                f"/sessions/{session_id}/messages",
                json={"content": "How do I bake chocolate cake?"},
            )
        assert resp1.status_code == 200
        assert resp1.json()["message"]["content"] == EXACT_REFUSAL_MESSAGE
        assert provider.call_count == 0

        # Turn 2: "Why is that?" follow-up -> MUST maintain immediate refusal with 0 LLM calls
        with patch("app.routers.chat.retrieve", new=AsyncMock(return_value=[low_chunk])):
            resp2 = client.post(
                f"/sessions/{session_id}/messages",
                json={"content": "Why is that?"},
            )
        assert resp2.status_code == 200
        assert resp2.json()["message"]["content"] == EXACT_REFUSAL_MESSAGE
        assert provider.call_count == 0

        # Turn 3: "Can you explain that more?" cascading follow-up -> MUST maintain immediate refusal with 0 LLM calls
        with patch("app.routers.chat.retrieve", new=AsyncMock(return_value=[low_chunk])):
            resp3 = client.post(
                f"/sessions/{session_id}/messages",
                json={"content": "Can you explain that more?"},
            )
        assert resp3.status_code == 200
        assert resp3.json()["message"]["content"] == EXACT_REFUSAL_MESSAGE
        assert provider.call_count == 0

        # Turn 4: "Tell me more about it" cascading follow-up -> MUST maintain immediate refusal with 0 LLM calls
        with patch("app.routers.chat.retrieve", new=AsyncMock(return_value=[low_chunk])):
            resp4 = client.post(
                f"/sessions/{session_id}/messages",
                json={"content": "Tell me more about it"},
            )
        assert resp4.status_code == 200
        assert resp4.json()["message"]["content"] == EXACT_REFUSAL_MESSAGE
        assert provider.call_count == 0
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_chat_provider, None)
        app.dependency_overrides.pop(get_chat_embedder, None)

