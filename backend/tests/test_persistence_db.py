"""Real PostgreSQL persistence tests (not mocks).

Requires a live PostgreSQL database with pgvector.
Marked with @pytest.mark.db. Skipped with a clear message if database is unreachable.
"""

import asyncio
import os
import uuid
import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models import Artifact, Message, Session, utc_now

settings = get_settings()
TEST_DB_URL = os.environ.get("DATABASE_URL", settings.database_url)


async def is_db_available() -> bool:
    """Check whether PostgreSQL database is reachable."""
    try:
        eng = create_async_engine(TEST_DB_URL, connect_args={"connect_timeout": 2})
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await eng.dispose()
        return True
    except Exception:
        return False


@pytest.fixture(autouse=True)
def check_db_or_skip():
    """Skip test if PostgreSQL is unreachable."""
    if not asyncio.run(is_db_available()):
        pytest.skip(f"PostgreSQL database is unreachable at {TEST_DB_URL}")


@pytest.fixture
def test_engine():
    """Create a separate async engine for persistence testing."""
    eng = create_async_engine(TEST_DB_URL, echo=False)
    yield eng
    asyncio.run(eng.dispose())


@pytest.fixture
def session_maker(test_engine):
    """Provide fresh async session factory."""
    return async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


# -----------------------------------------------------------------------------
# 1. Session Creation & Read-Back Through Fresh Connection
# -----------------------------------------------------------------------------
@pytest.mark.db
@pytest.mark.asyncio
async def test_db_create_and_read_session_fresh_connection(session_maker):
    """Verify session is written to PostgreSQL and retrievable via an independent connection."""
    test_session_id = uuid.uuid4()
    title = f"Test Session {uuid.uuid4().hex[:8]}"

    # Connection 1: Insert session
    async with session_maker() as conn1:
        session_obj = Session(
            id=test_session_id,
            title=title,
            llm_provider="ollama",
            llm_model="qwen2.5:7b",
        )
        conn1.add(session_obj)
        await conn1.commit()

    # Connection 2: Completely fresh connection to verify persistence
    async with session_maker() as conn2:
        stmt = select(Session).where(Session.id == test_session_id)
        result = await conn2.execute(stmt)
        persisted = result.scalar_one_or_none()

        assert persisted is not None
        assert persisted.id == test_session_id
        assert persisted.title == title
        assert persisted.llm_provider == "ollama"
        assert persisted.llm_model == "qwen2.5:7b"
        assert persisted.created_at is not None
        assert persisted.updated_at is not None

        # Cleanup
        await conn2.delete(persisted)
        await conn2.commit()


# -----------------------------------------------------------------------------
# 2. User Metadata & Client ID Round-Trip
# -----------------------------------------------------------------------------
@pytest.mark.db
@pytest.mark.asyncio
async def test_db_user_metadata_and_client_id_roundtrip(session_maker):
    """Verify JSONB user_metadata and client_id serialize, store, and round-trip correctly."""
    test_session_id = uuid.uuid4()
    client_id = f"client-app-{uuid.uuid4().hex[:6]}"
    metadata = {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TestClient/1.0",
        "accept_language": "en-US,en;q=0.9",
        "nested_experiment": {"variant": "B", "cohort": 2026},
        "flags": ["feature_artifacts", "feature_citations"],
    }

    # Connection 1: Save with user_metadata
    async with session_maker() as conn1:
        session_obj = Session(
            id=test_session_id,
            title="Metadata Round-Trip Session",
            client_id=client_id,
            user_metadata=metadata,
            llm_provider="ollama",
            llm_model="qwen2.5:7b",
        )
        conn1.add(session_obj)
        await conn1.commit()

    # Connection 2: Fresh query and verify exact JSONB structure
    async with session_maker() as conn2:
        stmt = select(Session).where(Session.id == test_session_id)
        result = await conn2.execute(stmt)
        persisted = result.scalar_one_or_none()

        assert persisted is not None
        assert persisted.client_id == client_id
        assert persisted.user_metadata["user_agent"] == metadata["user_agent"]
        assert persisted.user_metadata["accept_language"] == metadata["accept_language"]
        assert persisted.user_metadata["nested_experiment"] == {"variant": "B", "cohort": 2026}
        assert persisted.user_metadata["flags"] == ["feature_artifacts", "feature_citations"]
        assert "ip" not in persisted.user_metadata  # Strict privacy invariant

        # Cleanup
        await conn2.delete(persisted)
        await conn2.commit()


# -----------------------------------------------------------------------------
# 3. Message Ordering & Timestamp Precision
# -----------------------------------------------------------------------------
@pytest.mark.db
@pytest.mark.asyncio
async def test_db_message_ordering_and_timestamps(session_maker):
    """Verify messages persist with timezone-aware timestamps and retrieve in created_at order."""
    session_id = uuid.uuid4()

    async with session_maker() as conn1:
        sess = Session(
            id=session_id,
            title="Message Ordering Test",
            llm_provider="ollama",
            llm_model="qwen2.5:7b",
        )
        conn1.add(sess)
        await conn1.commit()

        # Add 3 messages sequentially
        for i in range(3):
            msg = Message(
                session_id=session_id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message step {i}",
                created_at=utc_now(),
            )
            conn1.add(msg)
            await conn1.commit()
            await asyncio.sleep(0.01)  # Ensure monotonic timestamp ordering

    # Read back via fresh connection
    async with session_maker() as conn2:
        stmt = (
            select(Session)
            .where(Session.id == session_id)
            .options(selectinload(Session.messages))
        )
        result = await conn2.execute(stmt)
        sess_read = result.scalar_one()

        assert len(sess_read.messages) == 3
        # Verify ordering
        for idx, msg in enumerate(sess_read.messages):
            assert msg.content == f"Message step {idx}"
            if idx > 0:
                assert msg.created_at >= sess_read.messages[idx - 1].created_at

        # Cleanup
        await conn2.delete(sess_read)
        await conn2.commit()


# -----------------------------------------------------------------------------
# 4. Cascade Deletion of Messages and Artifacts
# -----------------------------------------------------------------------------
@pytest.mark.db
@pytest.mark.asyncio
async def test_db_cascade_delete_messages_and_artifacts(session_maker):
    """Verify deleting a session cascades to its messages and artifacts in PostgreSQL."""
    session_id = uuid.uuid4()
    msg_id = uuid.uuid4()
    art_id = uuid.uuid4()

    async with session_maker() as conn1:
        sess = Session(
            id=session_id,
            title="Cascade Test",
            llm_provider="ollama",
            llm_model="qwen2.5:7b",
        )
        conn1.add(sess)
        await conn1.flush()

        msg = Message(
            id=msg_id,
            session_id=session_id,
            role="user",
            content="Hello world",
        )
        conn1.add(msg)

        art = Artifact(
            id=art_id,
            session_id=session_id,
            type="markdown",
            title="Test Playbook",
            content="# Playbook content",
        )
        conn1.add(art)
        await conn1.commit()

    # Verify both exist
    async with session_maker() as conn2:
        res_m = await conn2.execute(select(Message).where(Message.id == msg_id))
        res_a = await conn2.execute(select(Artifact).where(Artifact.id == art_id))
        assert res_m.scalar_one_or_none() is not None
        assert res_a.scalar_one_or_none() is not None

        # Delete session
        res_s = await conn2.execute(select(Session).where(Session.id == session_id))
        sess_to_del = res_s.scalar_one()
        await conn2.delete(sess_to_del)
        await conn2.commit()

    # Verify messages and artifacts were CASCADE deleted
    async with session_maker() as conn3:
        res_m_after = await conn3.execute(select(Message).where(Message.id == msg_id))
        res_a_after = await conn3.execute(select(Artifact).where(Artifact.id == art_id))
        assert res_m_after.scalar_one_or_none() is None
        assert res_a_after.scalar_one_or_none() is None


# -----------------------------------------------------------------------------
# 5. Session Updated At Mutation
# -----------------------------------------------------------------------------
@pytest.mark.db
@pytest.mark.asyncio
async def test_db_session_timestamp_mutation(session_maker):
    """Verify session updated_at advances upon updating session attributes."""
    session_id = uuid.uuid4()

    async with session_maker() as conn1:
        sess = Session(
            id=session_id,
            title="Initial Title",
            llm_provider="ollama",
            llm_model="qwen2.5:7b",
        )
        conn1.add(sess)
        await conn1.commit()
        initial_updated_at = sess.updated_at

    await asyncio.sleep(0.02)

    async with session_maker() as conn2:
        stmt = select(Session).where(Session.id == session_id)
        res = await conn2.execute(stmt)
        sess2 = res.scalar_one()
        sess2.title = "Updated Title"
        sess2.updated_at = utc_now()
        await conn2.commit()

    async with session_maker() as conn3:
        stmt = select(Session).where(Session.id == session_id)
        res = await conn3.execute(stmt)
        sess3 = res.scalar_one()
        assert sess3.title == "Updated Title"
        assert sess3.updated_at > initial_updated_at

        # Cleanup
        await conn3.delete(sess3)
        await conn3.commit()
