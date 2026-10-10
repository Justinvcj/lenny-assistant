"""Unit tests for transcript ingestion pipeline and idempotency."""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import Chunk, Document
from app.rag.embeddings import FakeEmbeddingsClient
from app.rag.ingest import (
    IngestionStats,
    ingest_document,
    ingest_transcripts,
    resolve_data_dir,
)

FIXTURE_MARKDOWN_1 = """---
title: "Retention Masterclass | Alice Smith"
date: "2026-09-01"
description: "How to fix churn"
guest: "Alice Smith"
post_url: "https://example.com/alice"
---

**Lenny Rachitsky** (00:00:00):
Welcome to the podcast. Today we are talking about product growth and onboarding retention.

**Alice Smith** (00:00:15):
Thanks Lenny. Retention is the single most important metric for early stage SaaS products. If your retention curve doesn't flatten, no amount of marketing will save you.

**Lenny Rachitsky** (00:00:30):
What is the number one mistake you see founders make with retention?

**Alice Smith** (00:00:35):
They focus on acquisition before product-market fit.
"""

FIXTURE_MARKDOWN_2 = """---
title: "Pricing Strategy | Bob Jones"
date: "2026-09-02"
description: "Monetization frameworks"
guest: "Bob Jones"
post_url: "https://example.com/bob"
---

**Lenny Rachitsky** (00:00:00):
Bob, welcome to the show. Let's talk about pricing tiers.

**Bob Jones** (00:00:10):
Pricing is the ultimate lever for SaaS revenue. Most founders undercharge by 2x to 5x.
"""


def test_resolve_data_dir_explicit(tmp_path: Path):
    d = tmp_path / "custom_data"
    d.mkdir()
    (d / "test.md").write_text(FIXTURE_MARKDOWN_1, encoding="utf-8")

    resolved = resolve_data_dir(str(d))
    assert resolved == d


def test_resolve_data_dir_with_podcasts_subfolder(tmp_path: Path):
    d = tmp_path / "lenny_data"
    podcasts_dir = d / "podcasts"
    podcasts_dir.mkdir(parents=True)
    (podcasts_dir / "ep1.md").write_text(FIXTURE_MARKDOWN_1, encoding="utf-8")

    resolved = resolve_data_dir(str(d))
    assert resolved == podcasts_dir


@pytest.mark.asyncio
async def test_ingest_document_dry_run(tmp_path: Path):
    file_path = tmp_path / "alice-smith.md"
    file_path.write_text(FIXTURE_MARKDOWN_1, encoding="utf-8")

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    embedder = FakeEmbeddingsClient(dim=768)

    status, chunk_count, token_count = await ingest_document(
        file_path=file_path,
        db=mock_db,
        embedder=embedder,
        dry_run=True,
    )

    assert status == "created"
    assert chunk_count > 0
    assert token_count > 0
    # Dry run must not call add, add_all, or commit
    assert mock_db.add.call_count == 0
    assert mock_db.add_all.call_count == 0
    assert mock_db.commit.call_count == 0
    assert embedder.call_count == 0


@pytest.mark.asyncio
async def test_ingest_document_creates_new_document_and_chunks(tmp_path: Path):
    file_path = tmp_path / "alice-smith.md"
    file_path.write_text(FIXTURE_MARKDOWN_1, encoding="utf-8")

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    embedder = FakeEmbeddingsClient(dim=768)

    status, chunk_count, token_count = await ingest_document(
        file_path=file_path,
        db=mock_db,
        embedder=embedder,
        batch_size=16,
    )

    assert status == "created"
    assert chunk_count > 0
    assert token_count > 0

    # Verifies document added and chunks inserted
    assert mock_db.add.call_count == 1
    added_doc = mock_db.add.call_args[0][0]
    assert isinstance(added_doc, Document)
    assert added_doc.slug == "alice-smith"
    assert added_doc.guest == "Alice Smith"

    assert mock_db.add_all.call_count == 1
    added_chunks = mock_db.add_all.call_args[0][0]
    assert len(added_chunks) == chunk_count
    for c in added_chunks:
        assert isinstance(c, Chunk)
        assert len(c.embedding) == 768

    assert mock_db.commit.call_count == 1


@pytest.mark.asyncio
async def test_ingest_document_skips_when_content_hash_matches(tmp_path: Path):
    file_path = tmp_path / "alice-smith.md"
    file_path.write_text(FIXTURE_MARKDOWN_1, encoding="utf-8")

    from app.rag.parser import compute_content_hash

    # Compute exact content hash
    expected_hash = compute_content_hash(FIXTURE_MARKDOWN_1)

    existing_doc = Document(
        id=uuid.uuid4(),
        slug="alice-smith",
        title="Retention Masterclass",
        guest="Alice Smith",
        source_path=str(file_path),
        content_hash=expected_hash,
    )

    mock_db = AsyncMock()
    # First query for Document: returns existing_doc
    # Second query for Chunk count: returns 3
    mock_result_doc = MagicMock()
    mock_result_doc.scalar_one_or_none.return_value = existing_doc

    mock_result_cnt = MagicMock()
    mock_result_cnt.scalar.return_value = 3

    mock_db.execute.side_effect = [mock_result_doc, mock_result_cnt]

    embedder = FakeEmbeddingsClient(dim=768)

    status, chunk_count, token_count = await ingest_document(
        file_path=file_path,
        db=mock_db,
        embedder=embedder,
        force=False,
    )

    assert status == "skipped"
    assert chunk_count == 3
    assert token_count == 0

    # No writes or embedder calls
    assert mock_db.add.call_count == 0
    assert mock_db.add_all.call_count == 0
    assert mock_db.commit.call_count == 0
    assert embedder.call_count == 0


@pytest.mark.asyncio
async def test_ingest_document_updates_when_content_hash_differs(tmp_path: Path):
    file_path = tmp_path / "alice-smith.md"
    file_path.write_text(FIXTURE_MARKDOWN_1, encoding="utf-8")

    doc_id = uuid.uuid4()
    existing_doc = Document(
        id=doc_id,
        slug="alice-smith",
        title="Old Title",
        guest="Old Guest",
        source_path=str(file_path),
        content_hash="old_stale_hash_12345",
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_doc
    mock_db.execute.return_value = mock_result

    embedder = FakeEmbeddingsClient(dim=768)

    status, chunk_count, token_count = await ingest_document(
        file_path=file_path,
        db=mock_db,
        embedder=embedder,
        force=False,
    )

    assert status == "updated"
    assert chunk_count > 0
    assert existing_doc.title == "Retention Masterclass | Alice Smith"
    assert existing_doc.guest == "Alice Smith"

    # Verifies old chunks deleted, new chunks added, and committed
    assert mock_db.add_all.call_count == 1
    assert mock_db.commit.call_count == 1


@pytest.mark.asyncio
async def test_ingest_transcripts_batch_and_limit(tmp_path: Path):
    (tmp_path / "01_alice.md").write_text(FIXTURE_MARKDOWN_1, encoding="utf-8")
    (tmp_path / "02_bob.md").write_text(FIXTURE_MARKDOWN_2, encoding="utf-8")

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    embedder = FakeEmbeddingsClient(dim=768)
    progress_log = []

    def on_progress(cur, total, slug, status, count):
        progress_log.append((cur, total, slug, status, count))

    # Test with limit=1: only the first file is processed
    stats: IngestionStats = await ingest_transcripts(
        source_dir=tmp_path,
        db=mock_db,
        limit=1,
        embedder=embedder,
        on_progress=on_progress,
    )

    assert stats.total_files == 1
    assert stats.created_docs == 1
    assert stats.total_chunks > 0
    assert len(progress_log) == 1
    assert progress_log[0][2] == "01_alice"
    assert progress_log[0][3] == "created"


@pytest.mark.asyncio
async def test_ingest_transcripts_rollback_on_document_error(tmp_path: Path):
    (tmp_path / "valid.md").write_text(FIXTURE_MARKDOWN_1, encoding="utf-8")

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    embedder = MagicMock()
    embedder.get_embeddings_batch_async = AsyncMock(side_effect=RuntimeError("Embedding hardware fault"))

    stats: IngestionStats = await ingest_transcripts(
        source_dir=tmp_path,
        db=mock_db,
        embedder=embedder,
    )

    assert len(stats.errors) == 1
    assert "valid.md" in stats.errors[0]["file"]
    assert "Embedding hardware fault" in stats.errors[0]["error"]
    assert mock_db.rollback.call_count == 1
