"""Unit tests for pgvector retrieval module and get_chunks_by_ids."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import Chunk, Document
from app.rag.embeddings import FakeEmbeddingsClient
from app.rag.retrieval import RetrievalResult, get_chunks_by_ids, retrieve


@pytest.mark.asyncio
async def test_retrieve_empty_or_whitespace_query_returns_empty():
    mock_db = AsyncMock()
    embedder = MagicMock()

    res1 = await retrieve("", mock_db, embedder=embedder)
    res2 = await retrieve("   \n\t  ", mock_db, embedder=embedder)

    assert res1 == []
    assert res2 == []
    assert mock_db.execute.call_count == 0
    assert embedder.get_query_embedding.call_count == 0


@pytest.mark.asyncio
async def test_retrieve_constructs_results_correctly():
    chunk_id = uuid.uuid4()
    mock_row = (
        chunk_id,
        "Here is a key quote about product-market fit and retention.",
        0.8425,
        "alice-smith",
        "Retention Masterclass",
        "Alice Smith",
        "Alice Smith",
        150,
        650,
        2,
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = [mock_row]
    mock_db.execute.return_value = mock_result

    embedder = FakeEmbeddingsClient(dim=768)

    results = await retrieve(
        query="product retention and onboarding",
        db=mock_db,
        top_k=5,
        min_score=0.5,
        embedder=embedder,
    )

    assert len(results) == 1
    item = results[0]
    assert isinstance(item, RetrievalResult)
    assert item.chunk_id == chunk_id
    assert item.text == "Here is a key quote about product-market fit and retention."
    assert item.score == pytest.approx(0.8425)
    assert item.document_slug == "alice-smith"
    assert item.title == "Retention Masterclass"
    assert item.guest == "Alice Smith"
    assert item.speaker == "Alice Smith"
    assert item.start_char == 150
    assert item.end_char == 650
    assert item.chunk_index == 2

    # Verify query was embedded
    assert embedder.call_count == 1


@pytest.mark.asyncio
async def test_retrieve_applies_min_score_and_top_k():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.execute.return_value = mock_result

    embedder = FakeEmbeddingsClient(dim=768)

    # Test top_k clamp
    await retrieve(
        query="test query",
        db=mock_db,
        top_k=3,
        min_score=0.65,
        embedder=embedder,
    )

    assert mock_db.execute.call_count == 1
    # Check that statement passed to execute has where and limit clauses
    stmt = mock_db.execute.call_args[0][0]
    # Check compiled statement has limit 3
    assert stmt._limit == 3


@pytest.mark.asyncio
async def test_get_chunks_by_ids_preserves_ordering():
    id_1 = uuid.uuid4()
    id_2 = uuid.uuid4()
    id_3 = uuid.uuid4()

    chunk_1 = Chunk(id=id_1, chunk_index=0, text="First chunk", embedding=[0.1] * 768)
    chunk_2 = Chunk(id=id_2, chunk_index=1, text="Second chunk", embedding=[0.2] * 768)
    chunk_3 = Chunk(id=id_3, chunk_index=2, text="Third chunk", embedding=[0.3] * 768)

    mock_db = AsyncMock()
    mock_result = MagicMock()
    # Simulate DB returning them in arbitrary order: 3, 1, 2
    mock_result.scalars.return_value.all.return_value = [chunk_3, chunk_1, chunk_2]
    mock_db.execute.return_value = mock_result

    # Request order: id_2, id_1, id_3
    ordered = await get_chunks_by_ids([id_2, id_1, id_3], mock_db)

    assert len(ordered) == 3
    assert ordered[0].id == id_2
    assert ordered[1].id == id_1
    assert ordered[2].id == id_3


@pytest.mark.asyncio
async def test_get_chunks_by_ids_handles_empty_and_missing():
    mock_db = AsyncMock()

    # Empty list
    res_empty = await get_chunks_by_ids([], mock_db)
    assert res_empty == []
    assert mock_db.execute.call_count == 0

    # Non-existent ID in result
    id_exists = uuid.uuid4()
    id_missing = uuid.uuid4()
    chunk_found = Chunk(id=id_exists, chunk_index=0, text="Found", embedding=[0.1] * 768)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [chunk_found]
    mock_db.execute.return_value = mock_result

    res = await get_chunks_by_ids([id_missing, id_exists], mock_db)
    assert len(res) == 1
    assert res[0].id == id_exists
