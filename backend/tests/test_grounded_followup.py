"""R1 grounded follow-up: short/anaphoric follow-ups to a grounded answer must
bypass the retrieval score gate, merge previously cited chunks, and go through
the normal agent + citation verifier.

Negative cases must still refuse: fresh-session short follow-ups, follow-ups
after a refusal, and standalone off-domain questions after a grounded answer.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.agent.prompts import EXACT_REFUSAL_MESSAGE
from app.db import get_db_session
from app.llm.base import ChatResponse as LLMChatResponse
from app.llm.base import ProviderHealth
from app.main import app
from app.models import Message, Session
from app.rag.retrieval import RetrievalResult
from app.routers.chat import get_chat_embedder, get_chat_provider
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _no_sdk():
    with patch("app.agent.orchestrator._run_with_sdk",
               side_effect=RuntimeError("SDK disabled in unit tests")):
        yield


class _Provider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    async def chat(self, messages, *, system=None, temperature=0.2, max_tokens=1024, extra=None):
        self.call_count += 1
        idx = min(self.call_count - 1, len(self.responses) - 1)
        return LLMChatResponse(content=self.responses[idx], input_tokens=10,
                               output_tokens=10, model="mock")

    async def embed(self, texts):
        return [[0.1] * 768 for _ in texts]

    async def health(self):
        return ProviderHealth(ok=True, model="mock")


class _Embedder:
    async def embed_query(self, text):
        return [0.05] * 768

    async def embed_documents(self, texts):
        return [[0.05] * 768 for _ in texts]


def _chunk(score=0.75, title="PMF Episode", guest="Hila Qu", text="Retention after activation [S1]."):
    return RetrievalResult(
        chunk_id=uuid.uuid4(), text=text, score=score,
        document_slug="ep", title=title, guest=guest, speaker=guest,
        start_char=0, end_char=len(text), chunk_index=0,
    )


def _db(session_obj, history):
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def _refresh(instance):
        if not getattr(instance, "id", None):
            instance.id = uuid.uuid4()
        if not getattr(instance, "created_at", None):
            instance.created_at = datetime.now(UTC)

    db.refresh = AsyncMock(side_effect=_refresh)

    def execute(stmt):
        s = str(stmt).lower()
        res = MagicMock()
        if "from sessions" in s:
            res.scalar_one_or_none.return_value = session_obj
        elif "from chunks" in s:
            # grounded-followup merges prev cited chunks: return [] (not needed for test)
            res.scalars.return_value.all.return_value = []
        else:
            res.scalars.return_value.all.return_value = history or []
            res.scalar_one_or_none.return_value = None
        return res

    db.execute = AsyncMock(side_effect=execute)
    return db


def _grounded_history(session_id):
    base = datetime.now(UTC) - timedelta(minutes=5)
    chunk_id = uuid.uuid4()
    return [
        Message(id=uuid.uuid4(), session_id=session_id, role="user",
                content="How do you know when you have product-market fit?",
                created_at=base),
        Message(id=uuid.uuid4(), session_id=session_id, role="assistant",
                content="PMF is when users pull the product [S1].",
                intent="qa",
                citations=[{"n": 1, "chunk_id": str(chunk_id),
                            "title": "PMF Episode", "guest": "Hila Qu",
                            "passage": "Users pull the product"}],
                created_at=base + timedelta(seconds=30)),
    ]


def _refused_history(session_id):
    base = datetime.now(UTC) - timedelta(minutes=5)
    return [
        Message(id=uuid.uuid4(), session_id=session_id, role="user",
                content="How do I bake chocolate cake?", created_at=base),
        Message(id=uuid.uuid4(), session_id=session_id, role="assistant",
                content=EXACT_REFUSAL_MESSAGE, intent="qa", citations=[],
                created_at=base + timedelta(seconds=5)),
    ]


# Twelve short/anaphoric phrasings the brief says must still answer
POSITIVE_FOLLOWUPS = [
    "Why is that?",
    "Can you explain that more?",
    "Why?",
    "How so?",
    "Tell me more.",
    "Tell me more about that.",
    "Can you elaborate?",
    "Can you expand on that?",
    "What do you mean by that?",
    "Say more.",
    "Go deeper on that.",
    "Explain further.",
]


def _run(client, session_id, mock_db, raw_chunks, user_text, response_text):
    provider = _Provider([response_text])
    embedder = _Embedder()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override_db
    app.dependency_overrides[get_chat_provider] = lambda: provider
    app.dependency_overrides[get_chat_embedder] = lambda: embedder
    try:
        with patch("app.routers.chat.retrieve",
                   new=AsyncMock(return_value=raw_chunks)):
            r = client.post(f"/sessions/{session_id}/messages",
                            json={"content": user_text})
        return r, provider
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_chat_provider, None)
        app.dependency_overrides.pop(get_chat_embedder, None)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.parametrize("followup", POSITIVE_FOLLOWUPS)
def test_grounded_followup_bypasses_score_gate(client, followup):
    """A short/anaphoric follow-up after a grounded answer MUST answer even when the
    enriched-query retrieval score dips below `RETRIEVAL_MIN_SCORE`."""
    session_id = uuid.uuid4()
    session_obj = Session(id=session_id, llm_provider="ollama",
                          llm_model="qwen2.5:7b",
                          created_at=datetime.now(UTC))
    history = _grounded_history(session_id)
    low = _chunk(score=0.40, text="A passage of lower score about pmf discovery [S1].")

    r, provider = _run(client, session_id, _db(session_obj, history),
                       [low], followup,
                       "Because the signal becomes consistent across cohorts [S1].")
    assert r.status_code == 200
    data = r.json()
    assert data["message"]["content"] != EXACT_REFUSAL_MESSAGE, (
        f"follow-up {followup!r} wrongly refused; got {data['message']['content']!r}"
    )
    assert len(data["citations"]) >= 1
    assert provider.call_count >= 1


def test_fresh_short_message_refuses(client):
    """`Why is that?` in a fresh session (no prior grounded answer) must refuse."""
    session_id = uuid.uuid4()
    session_obj = Session(id=session_id, llm_provider="ollama",
                          llm_model="qwen2.5:7b",
                          created_at=datetime.now(UTC))
    low = _chunk(score=0.40)
    r, provider = _run(client, session_id, _db(session_obj, []),
                       [low], "Why is that?", "ignored")
    data = r.json()
    assert data["message"]["content"] == EXACT_REFUSAL_MESSAGE
    assert provider.call_count == 0


def test_short_followup_after_refusal_still_refuses(client):
    """`Why is that?` immediately after a refusal must refuse (no LLM call)."""
    session_id = uuid.uuid4()
    session_obj = Session(id=session_id, llm_provider="ollama",
                          llm_model="qwen2.5:7b",
                          created_at=datetime.now(UTC))
    low = _chunk(score=0.40)
    r, provider = _run(client, session_id,
                       _db(session_obj, _refused_history(session_id)),
                       [low], "Why is that?", "ignored")
    data = r.json()
    assert data["message"]["content"] == EXACT_REFUSAL_MESSAGE
    assert provider.call_count == 0


def test_standalone_off_domain_after_grounded_answer_refuses(client):
    """`How do I bake bread?` after a grounded answer must refuse via normal gate."""
    session_id = uuid.uuid4()
    session_obj = Session(id=session_id, llm_provider="ollama",
                          llm_model="qwen2.5:7b",
                          created_at=datetime.now(UTC))
    history = _grounded_history(session_id)
    low = _chunk(score=0.40)
    r, provider = _run(client, session_id, _db(session_obj, history),
                       [low], "How do I bake bread?", "ignored")
    data = r.json()
    assert data["message"]["content"] == EXACT_REFUSAL_MESSAGE
    assert provider.call_count == 0


def test_sky_blue_after_grounded_answer_refuses(client):
    """`Why is the sky blue?` is standalone — must refuse via normal gate."""
    session_id = uuid.uuid4()
    session_obj = Session(id=session_id, llm_provider="ollama",
                          llm_model="qwen2.5:7b",
                          created_at=datetime.now(UTC))
    history = _grounded_history(session_id)
    low = _chunk(score=0.40)
    r, provider = _run(client, session_id, _db(session_obj, history),
                       [low], "Why is the sky blue?", "ignored")
    data = r.json()
    assert data["message"]["content"] == EXACT_REFUSAL_MESSAGE
    assert provider.call_count == 0
