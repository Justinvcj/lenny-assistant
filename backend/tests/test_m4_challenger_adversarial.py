"""Milestone 4 Adversarial Challenger Stress Test Suite.

Empirical verification of:
1. Command string rejection in derive_summary_title (R6).
2. Walkback depth across chained artifacts, essays, refusals, clarifications (R6).
3. Out-of-domain follow-up refusal guard with zero LLM calls (R7).
"""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from fastapi.testclient import TestClient

from app.agent.prompts import EXACT_REFUSAL_MESSAGE, is_standalone_query, rewrite_query

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

from app.agent.router import Intent, classify_intent
from app.db import get_db_session
from app.main import app
from app.models import Artifact, Message, Session
from app.routers.chat import (
    derive_summary_title,
    find_last_grounded_qa_exchange,
    get_chat_embedder,
    get_chat_provider,
    is_command_string,
)
from tests.test_chat import MockEmbedder, MockLLMProvider, make_dynamic_mock_db, make_retrieval_chunk


# ============================================================================
# 1. Command String Rejection in derive_summary_title
# ============================================================================

COMMAND_PHRASES = [
    "Make a one-pager",
    "Generate an essay",
    "Can you summarize that in HTML",
    "Please export markdown",
    "Export as markdown",
    "Export this as markdown",
    "Can you export to markdown",
    "Please export to markdown",
    "Turn that into a Ship 30 essay",
    "Make a markdown doc summarizing that",
    "Summarize that",
]


@pytest.mark.parametrize("cmd_phrase", COMMAND_PHRASES)
def test_derive_summary_title_command_rejection(cmd_phrase):
    """Assert title never equals or contains command imperative text."""
    plain_assistant_text = "Here is the summary of Lenny's podcast on product growth."
    derived_title = derive_summary_title(cmd_phrase, plain_assistant_text)

    # The title must never equal or contain imperative command tokens
    lower_title = derived_title.lower()
    lower_cmd = cmd_phrase.lower()

    # The command itself must be detected as a command string
    is_cmd = is_command_string(cmd_phrase)

    # Imperatives that should not leak into artifact titles
    for verb in ["make", "generate", "summarize", "export", "turn", "draft", "create"]:
        if verb in lower_cmd:
            assert verb not in lower_title, (
                f"Command verb '{verb}' from '{cmd_phrase}' leaked into derived title: '{derived_title}'"
            )

    assert is_cmd, f"Expected is_command_string('{cmd_phrase}') to be True"
    assert derived_title != f"{cmd_phrase.title()}: Summary", (
        f"derive_summary_title failed to reject command: returned '{derived_title}'"
    )


# ============================================================================
# 2. Walkback Depth in find_last_grounded_qa_exchange
# ============================================================================

def test_find_last_grounded_qa_exchange_deep_walkback():
    """Test history with multiple back-to-back artifact/essay commands, refusals, and clarifications.
    Assert find_last_grounded_qa_exchange walks back to the original QA exchange.
    """
    t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    step = timedelta(seconds=10)

    # 1. Original grounded QA exchange
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
        created_at=t0 + step,
    )

    # 2. Turn 2: HTML Artifact request
    msg_user_art1 = Message(
        id=uuid.uuid4(),
        role="user",
        content="Make a one-pager (HTML)",
        created_at=t0 + step * 2,
    )
    msg_asst_art1 = Message(
        id=uuid.uuid4(),
        role="assistant",
        content="Your HTML one-pager is ready: 'Finding PMF: Summary' (150 words)...",
        citations=[{"chunk_id": str(uuid.uuid4()), "guest": "Peter Specht", "title": "Finding PMF"}],
        intent="artifact",
        created_at=t0 + step * 3,
    )

    # 3. Turn 3: Ship 30 Essay request
    msg_user_essay = Message(
        id=uuid.uuid4(),
        role="user",
        content="Turn that into a Ship 30 essay",
        created_at=t0 + step * 4,
    )
    msg_asst_essay = Message(
        id=uuid.uuid4(),
        role="assistant",
        content="Your atomic essay is ready: 'Finding PMF: Summary' (250 words)...",
        citations=[{"chunk_id": str(uuid.uuid4()), "guest": "Peter Specht", "title": "Finding PMF"}],
        intent="essay",
        created_at=t0 + step * 5,
    )

    # 4. Turn 4: Out-of-domain refusal
    msg_user_ood = Message(
        id=uuid.uuid4(),
        role="user",
        content="How do I bake chocolate cake?",
        created_at=t0 + step * 6,
    )
    msg_asst_ood = Message(
        id=uuid.uuid4(),
        role="assistant",
        content=EXACT_REFUSAL_MESSAGE,
        citations=[],
        intent="qa",
        created_at=t0 + step * 7,
    )

    # 5. Turn 5: Follow-up refusal
    msg_user_ood_fu = Message(
        id=uuid.uuid4(),
        role="user",
        content="Why is that?",
        created_at=t0 + step * 8,
    )
    msg_asst_ood_fu = Message(
        id=uuid.uuid4(),
        role="assistant",
        content=EXACT_REFUSAL_MESSAGE,
        citations=[],
        intent="qa",
        created_at=t0 + step * 9,
    )

    # 6. Turn 6: Clarification exchange
    msg_user_clarif = Message(
        id=uuid.uuid4(),
        role="user",
        content="Can you draft a doc?",
        created_at=t0 + step * 10,
    )
    msg_asst_clarif = Message(
        id=uuid.uuid4(),
        role="assistant",
        content="What topic would you like the document to focus on?",
        citations=[],
        intent="artifact",
        created_at=t0 + step * 11,
    )

    # 7. Turn 7: Markdown Artifact request
    msg_user_art2 = Message(
        id=uuid.uuid4(),
        role="user",
        content="Make a markdown doc summarizing that",
        created_at=t0 + step * 12,
    )
    msg_asst_art2 = Message(
        id=uuid.uuid4(),
        role="assistant",
        content="Your markdown document is ready: 'Finding PMF: Summary' (200 words)...",
        citations=[{"chunk_id": str(uuid.uuid4()), "guest": "Peter Specht", "title": "Finding PMF"}],
        intent="artifact",
        created_at=t0 + step * 13,
    )

    deep_history = [
        msg_user_qa, msg_asst_qa,
        msg_user_art1, msg_asst_art1,
        msg_user_essay, msg_asst_essay,
        msg_user_ood, msg_asst_ood,
        msg_user_ood_fu, msg_asst_ood_fu,
        msg_user_clarif, msg_asst_clarif,
        msg_user_art2, msg_asst_art2,
    ]

    u, a = find_last_grounded_qa_exchange(deep_history)
    assert u is not None, "Failed to find grounded user query across deep history"
    assert a is not None, "Failed to find grounded assistant answer across deep history"
    assert u.content == "What did Lenny say about finding product-market fit?"
    assert "retention curves flatten" in a.content


def test_find_last_grounded_qa_exchange_edge_cases():
    """Verify edge cases: empty history, only refusals, only artifacts."""
    # Empty history
    assert find_last_grounded_qa_exchange([]) == (None, None)

    # Only refusals
    t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    ood_history = [
        Message(id=uuid.uuid4(), role="user", content="How to bake pizza?", created_at=t0),
        Message(id=uuid.uuid4(), role="assistant", content=EXACT_REFUSAL_MESSAGE, citations=[], intent="qa", created_at=t0 + timedelta(seconds=1)),
        Message(id=uuid.uuid4(), role="user", content="Why is that?", created_at=t0 + timedelta(seconds=2)),
        Message(id=uuid.uuid4(), role="assistant", content=EXACT_REFUSAL_MESSAGE, citations=[], intent="qa", created_at=t0 + timedelta(seconds=3)),
    ]
    assert find_last_grounded_qa_exchange(ood_history) == (None, None)


# ============================================================================
# 3. Out-of-Domain Follow-up Refusal Guard (0 LLM Calls)
# ============================================================================

def make_accurate_mock_db(session_obj: Session):
    messages: list[Message] = []
    artifacts: list[Artifact] = []

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()

    def fake_add(instance):
        if isinstance(instance, Message):
            if not getattr(instance, "id", None):
                instance.id = uuid.uuid4()
            if not getattr(instance, "created_at", None):
                instance.created_at = datetime.now(timezone.utc)
            messages.append(instance)
        elif isinstance(instance, Artifact):
            if not getattr(instance, "id", None):
                instance.id = uuid.uuid4()
            if not getattr(instance, "created_at", None):
                instance.created_at = datetime.now(timezone.utc)
            artifacts.append(instance)

    mock_db.add = MagicMock(side_effect=fake_add)

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
        elif "from artifacts" in stmt_str:
            res.scalar_one_or_none.return_value = artifacts[-1] if artifacts else None
        elif "from messages" in stmt_str:
            # Match where Message.id != user_msg.id
            if "messages.id !=" in stmt_str or "messages.id not in" in stmt_str:
                res.scalars.return_value.all.return_value = list(messages[:-1]) if messages else []
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


@pytest.mark.parametrize("followup_query", [
    "Why is that?",
    "Can you explain?",
    "Can you explain that?",
    "Why?",
    "Tell me more.",
    "Could you elaborate?",
    "What do you mean?",
    "How come?",
])
def test_out_of_domain_followup_guard_zero_llm_calls(client, followup_query):
    """Test out-of-domain query ('How to make pizza?') followed by elliptical follow-ups.
    Assert immediate refusal with zero LLM calls.
    """
    session_id = uuid.uuid4()
    mock_session_obj = Session(
        id=session_id,
        llm_provider="ollama",
        llm_model="qwen2.5:7b",
        created_at=datetime.now(timezone.utc),
    )
    mock_db = make_accurate_mock_db(session_obj=mock_session_obj)

    low_chunk = make_retrieval_chunk(score=0.35, text="Pizza recipe and mozzarella cheese")
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
                json={"content": "How to make pizza?"},
            )
        assert resp1.status_code == 200
        assert resp1.json()["message"]["content"] == EXACT_REFUSAL_MESSAGE
        assert provider.call_count == 0

        # Turn 2: Elliptical follow-up -> MUST immediately refuse with 0 LLM calls
        with patch("app.routers.chat.retrieve", new=AsyncMock(return_value=[low_chunk])):
            resp2 = client.post(
                f"/sessions/{session_id}/messages",
                json={"content": followup_query},
            )
        assert resp2.status_code == 200
        assert resp2.json()["message"]["content"] == EXACT_REFUSAL_MESSAGE
        assert provider.call_count == 0, f"Expected 0 LLM calls for '{followup_query}', got {provider.call_count}"
        assert resp2.json()["message"]["tool_trace"][0]["action"] == "refusal_followup_to_out_of_domain"
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_chat_provider, None)
        app.dependency_overrides.pop(get_chat_embedder, None)
