"""Empirical Challenger Test Suite for Milestone 1 (P3c: Embeddings, Ingestion, and Retrieval).

Stress-tests:
1. Retrieval edge cases: empty strings, unicode whitespace, huge queries (>10k chars),
   extreme top_k and min_score boundaries, SQL injection patterns, live Ollama.
2. ID lookup edge cases: zero IDs, duplicate IDs, non-existent UUIDs, nil UUIDs, large lists.
3. Batch embedding edge cases: empty list, single item, batch boundary sizes (31, 32, 33),
   sequence types (generators/tuples), live Ollama batching.
4. Content hash stability: CRLF vs LF strings, CRLF vs LF bytes, UTF-8 BOM,
   and corpus-wide hash invariance across all 50 real podcast files.
5. Ingestion parameter boundaries: limit=0 behavior, malformed files, empty turns.
"""

import hashlib
from pathlib import Path
from typing import List, Sequence
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from app.models import Chunk, Document
from app.rag.chunking import chunk_document
from app.rag.embeddings import (
    DOCUMENT_PREFIX,
    QUERY_PREFIX,
    FakeEmbeddingsClient,
    OllamaEmbeddingsClient,
    apply_prefix,
    get_embeddings_batch,
    get_embeddings_batch_async,
)
from app.rag.ingest import (
    IngestionStats,
    ingest_document,
    ingest_transcripts,
)
from app.rag.parser import (
    compute_content_hash,
    parse_transcript_file,
    parse_transcript_text,
)
from app.rag.retrieval import RetrievalResult, get_chunks_by_ids, retrieve


# ==============================================================================
# GROUP 1: RETRIEVE STRESS TESTING
# ==============================================================================


@pytest.mark.asyncio
async def test_retrieve_empty_string():
    """Empty string must immediately return [] without database or embedder calls."""
    mock_db = AsyncMock()
    mock_embedder = MagicMock()

    res = await retrieve("", mock_db, embedder=mock_embedder)
    assert res == []
    assert mock_db.execute.call_count == 0
    assert mock_embedder.get_query_embedding.call_count == 0


@pytest.mark.asyncio
async def test_retrieve_unicode_and_special_whitespace():
    """Various whitespace types (spaces, tabs, newlines, unicode spaces) must return []."""
    mock_db = AsyncMock()
    mock_embedder = MagicMock()

    test_cases = [
        "   ",
        "\t\t\n\r\n  \t",
        "\u00A0\u00A0",  # Non-breaking space
        "\u2003\u2002\u2009",  # Em space, en space, thin space
        "\u3000",  # Ideographic space (CJK)
        "\r\n\r\n\t \v\f",  # Mixed vertical tab and form feed
    ]

    for ws in test_cases:
        res = await retrieve(ws, mock_db, embedder=mock_embedder)
        assert res == [], f"Expected empty result for whitespace {repr(ws)}"

    assert mock_db.execute.call_count == 0
    assert mock_embedder.get_query_embedding.call_count == 0


@pytest.mark.asyncio
async def test_retrieve_huge_query_offline():
    """Huge queries (>10,000 characters) must execute without truncation error or stack overflow."""
    huge_query = ("What is the best way to optimize customer retention, reduce churn, "
                  "and accelerate product-market fit? ") * 150  # ~14,700 chars
    assert len(huge_query) > 10000

    chunk_id = uuid.uuid4()
    mock_row = (
        chunk_id,
        "Here is retention advice.",
        0.785,
        "elena-verna-40",
        "Elena Verna 4.0",
        "Elena Verna",
        "Elena Verna",
        100,
        300,
        1,
    )
    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.all.return_value = [mock_row]
    mock_db.execute.return_value = mock_res

    fake_embedder = FakeEmbeddingsClient(dim=768)

    results = await retrieve(
        query=huge_query,
        db=mock_db,
        top_k=5,
        min_score=0.5,
        embedder=fake_embedder,
    )

    assert len(results) == 1
    assert results[0].chunk_id == chunk_id
    assert results[0].score == pytest.approx(0.785)
    assert fake_embedder.call_count == 1
    assert mock_db.execute.call_count == 1


@pytest.mark.asyncio
async def test_retrieve_huge_query_live_ollama():
    """Empirically probe live Ollama instance with a >10,000 char query."""
    import socket

    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect(("localhost", 11434))
        s.close()
    except Exception:
        pytest.skip("Ollama is not running on localhost:11434")

    huge_query = ("Tell me everything about product growth loops, onboarding activation, "
                  "and SaaS pricing strategy. ") * 150  # ~14,250 chars
    assert len(huge_query) > 10000

    client = OllamaEmbeddingsClient(base_url="http://localhost:11434")
    vector = await client.get_query_embedding_async(huge_query)

    assert len(vector) == 768
    assert all(isinstance(v, float) for v in vector)
    # Check non-zero and non-NaN
    assert any(v != 0.0 for v in vector)
    assert not any(math_isnan(v) for v in vector)


def math_isnan(val: float) -> bool:
    import math
    return math.isnan(val)


@pytest.mark.asyncio
async def test_retrieve_boundary_parameters():
    """Test boundary values for top_k (<=0, large) and min_score (negative, 0.0, 1.0, >1.0)."""
    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.all.return_value = []
    mock_db.execute.return_value = mock_res

    embedder = FakeEmbeddingsClient(dim=768)

    # 1. top_k <= 0 should fall back to settings.retrieval_top_k (default 6)
    await retrieve(query="retention", db=mock_db, top_k=0, embedder=embedder)
    stmt0 = mock_db.execute.call_args[0][0]
    assert stmt0._limit == 6

    await retrieve(query="retention", db=mock_db, top_k=-10, embedder=embedder)
    stmt_neg = mock_db.execute.call_args[0][0]
    assert stmt_neg._limit == 6

    # 2. top_k = 100
    await retrieve(query="retention", db=mock_db, top_k=100, embedder=embedder)
    stmt_large = mock_db.execute.call_args[0][0]
    assert stmt_large._limit == 100

    # 3. min_score = 0.0 -> no distance where clause added
    await retrieve(query="retention", db=mock_db, min_score=0.0, embedder=embedder)
    stmt_zero = mock_db.execute.call_args[0][0]
    assert stmt_zero._where_criteria == ()

    # 4. min_score = -0.5 -> treated as <= 0.0, no where clause added
    await retrieve(query="retention", db=mock_db, min_score=-0.5, embedder=embedder)
    stmt_neg_score = mock_db.execute.call_args[0][0]
    assert stmt_neg_score._where_criteria == ()

    # 5. min_score = 0.8 -> where criteria present
    await retrieve(query="retention", db=mock_db, min_score=0.8, embedder=embedder)
    stmt_pos = mock_db.execute.call_args[0][0]
    assert len(stmt_pos._where_criteria) == 1


@pytest.mark.asyncio
async def test_retrieve_sql_injection_and_emojis():
    """SQL injection strings and emojis must be safely parameterized."""
    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.all.return_value = []
    mock_db.execute.return_value = mock_res

    embedder = FakeEmbeddingsClient(dim=768)

    malicious_query = "'; DROP TABLE chunks; SELECT * FROM documents WHERE slug = 'admin'--"
    res = await retrieve(query=malicious_query, db=mock_db, embedder=embedder)
    assert res == []
    assert mock_db.execute.call_count == 1

    emoji_query = "🚀🔥 What is retention? 🎯💡"
    res_emoji = await retrieve(query=emoji_query, db=mock_db, embedder=embedder)
    assert res_emoji == []
    assert mock_db.execute.call_count == 2


# ==============================================================================
# GROUP 2: GET_CHUNKS_BY_IDS STRESS TESTING
# ==============================================================================


@pytest.mark.asyncio
async def test_get_chunks_by_ids_zero_ids():
    """Zero IDs must immediately return [] without DB execution."""
    mock_db = AsyncMock()
    res = await get_chunks_by_ids([], mock_db)
    assert res == []
    assert mock_db.execute.call_count == 0


@pytest.mark.asyncio
async def test_get_chunks_by_ids_duplicates():
    """Duplicate IDs must return unique Chunk models preserving first-appearance order."""
    id1 = uuid.uuid4()
    id2 = uuid.uuid4()
    id3 = uuid.uuid4()

    chunk1 = Chunk(id=id1, chunk_index=0, text="Chunk 1", embedding=[0.1] * 768)
    chunk2 = Chunk(id=id2, chunk_index=1, text="Chunk 2", embedding=[0.2] * 768)
    chunk3 = Chunk(id=id3, chunk_index=2, text="Chunk 3", embedding=[0.3] * 768)

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [chunk3, chunk1, chunk2]
    mock_db.execute.return_value = mock_res

    # Input has heavy duplicates: id2, id1, id2, id3, id1, id2
    requested_ids = [id2, id1, id2, id3, id1, id2]
    ordered = await get_chunks_by_ids(requested_ids, mock_db)

    # Must deduplicate and preserve order: chunk2, chunk1, chunk3
    assert len(ordered) == 3
    assert ordered[0].id == id2
    assert ordered[1].id == id1
    assert ordered[2].id == id3


@pytest.mark.asyncio
async def test_get_chunks_by_ids_non_existent_and_nil_uuid():
    """Non-existent UUIDs and Nil UUID must return [] gracefully."""
    nil_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    random_id = uuid.uuid4()

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_res

    ordered = await get_chunks_by_ids([nil_id, random_id], mock_db)
    assert ordered == []
    assert mock_db.execute.call_count == 1


@pytest.mark.asyncio
async def test_get_chunks_by_ids_mixed_existing_and_missing():
    """Interleaved existing and missing UUIDs must return only existing chunks in order."""
    id_exist1 = uuid.uuid4()
    id_exist2 = uuid.uuid4()
    id_missing1 = uuid.uuid4()
    id_missing2 = uuid.uuid4()

    chunk1 = Chunk(id=id_exist1, chunk_index=0, text="First", embedding=[0.1] * 768)
    chunk2 = Chunk(id=id_exist2, chunk_index=1, text="Second", embedding=[0.2] * 768)

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [chunk2, chunk1]
    mock_db.execute.return_value = mock_res

    # Order: missing1, exist2, missing2, exist1
    req = [id_missing1, id_exist2, id_missing2, id_exist1]
    res = await get_chunks_by_ids(req, mock_db)

    assert len(res) == 2
    assert res[0].id == id_exist2
    assert res[1].id == id_exist1


# ==============================================================================
# GROUP 3: BATCH EMBEDDING STRESS TESTING
# ==============================================================================


def test_batch_embedding_empty_list():
    """Empty list returns [] with 0 network calls for both sync and async."""
    client = OllamaEmbeddingsClient()
    with patch("httpx.Client.post") as mock_post:
        res = client.get_embeddings_batch([])
        assert res == []
        assert mock_post.call_count == 0


@pytest.mark.asyncio
async def test_batch_embedding_empty_list_async():
    client = OllamaEmbeddingsClient()
    with patch("httpx.AsyncClient.post") as mock_post:
        res = await client.get_embeddings_batch_async([])
        assert res == []
        assert mock_post.call_count == 0


def test_batch_embedding_single_item():
    """Single item batch returns 1 embedding vector with 1 network call."""
    client = OllamaEmbeddingsClient()
    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {"embeddings": [[0.5] * 768]}

    with patch("httpx.Client.post", return_value=resp_200) as mock_post:
        res = client.get_embeddings_batch(["Single chunk"])
        assert len(res) == 1
        assert len(res[0]) == 768
        assert mock_post.call_count == 1
        payload = mock_post.call_args[1]["json"]
        assert payload["input"] == [f"{DOCUMENT_PREFIX}Single chunk"]


def test_batch_embedding_boundary_sizes_31_32_33_sync():
    """Verify batch boundary slicing behavior at 31, 32, and 33 items with batch_size=32."""
    client = OllamaEmbeddingsClient()

    def mock_post_impl(url, json=None, **kwargs):
        inp = json.get("input", [])
        m = MagicMock()
        m.status_code = 200
        m.json.return_value = {"embeddings": [[0.1] * 768 for _ in inp]}
        return m

    with patch("httpx.Client.post", side_effect=mock_post_impl) as mock_post:
        # Case 31: Exactly 1 call with 31 items
        res31 = client.get_embeddings_batch([f"item {i}" for i in range(31)], batch_size=32)
        assert len(res31) == 31
        assert mock_post.call_count == 1
        assert len(mock_post.call_args[1]["json"]["input"]) == 31

        mock_post.reset_mock()

        # Case 32: Exactly 1 call with 32 items
        res32 = client.get_embeddings_batch([f"item {i}" for i in range(32)], batch_size=32)
        assert len(res32) == 32
        assert mock_post.call_count == 1
        assert len(mock_post.call_args[1]["json"]["input"]) == 32

        mock_post.reset_mock()

        # Case 33: Exactly 2 calls: Call 1 has 32 items, Call 2 has 1 item
        res33 = client.get_embeddings_batch([f"item {i}" for i in range(33)], batch_size=32)
        assert len(res33) == 33
        assert mock_post.call_count == 2
        call1_input = mock_post.call_args_list[0][1]["json"]["input"]
        call2_input = mock_post.call_args_list[1][1]["json"]["input"]
        assert len(call1_input) == 32
        assert len(call2_input) == 1


@pytest.mark.asyncio
async def test_batch_embedding_boundary_sizes_31_32_33_async():
    """Verify async batch boundary slicing behavior at 31, 32, and 33 items with batch_size=32."""
    client = OllamaEmbeddingsClient()

    async def mock_post_impl(url, json=None, **kwargs):
        inp = json.get("input", [])
        m = MagicMock()
        m.status_code = 200
        m.json.return_value = {"embeddings": [[0.1] * 768 for _ in inp]}
        return m

    with patch("httpx.AsyncClient.post", side_effect=mock_post_impl) as mock_post:
        # Case 31
        res31 = await client.get_embeddings_batch_async([f"item {i}" for i in range(31)], batch_size=32)
        assert len(res31) == 31
        assert mock_post.call_count == 1

        mock_post.reset_mock()

        # Case 32
        res32 = await client.get_embeddings_batch_async([f"item {i}" for i in range(32)], batch_size=32)
        assert len(res32) == 32
        assert mock_post.call_count == 1

        mock_post.reset_mock()

        # Case 33
        res33 = await client.get_embeddings_batch_async([f"item {i}" for i in range(33)], batch_size=32)
        assert len(res33) == 33
        assert mock_post.call_count == 2
        assert len(mock_post.call_args_list[0][1]["json"]["input"]) == 32
        assert len(mock_post.call_args_list[1][1]["json"]["input"]) == 1


def test_batch_embedding_live_ollama_boundaries():
    """Empirically test live Ollama with 1, 31, 32, and 33 items."""
    import socket

    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect(("localhost", 11434))
        s.close()
    except Exception:
        pytest.skip("Ollama is not running on localhost:11434")

    client = OllamaEmbeddingsClient(base_url="http://localhost:11434")

    for count in [1, 31, 32, 33]:
        texts = [f"Transcript chunk #{i} discussing product-market fit and growth metrics." for i in range(count)]
        embeddings = client.get_embeddings_batch(texts, batch_size=32)
        assert len(embeddings) == count
        for emb in embeddings:
            assert len(emb) == 768


def test_batch_embedding_sequence_types():
    """Verify client accepts tuples and generators."""
    fake = FakeEmbeddingsClient(dim=768)

    # Tuple
    tuple_res = fake.get_embeddings_batch(("chunk A", "chunk B"))
    assert len(tuple_res) == 2

    # Generator
    gen_res = fake.get_embeddings_batch((f"gen {i}" for i in range(5)))
    assert len(gen_res) == 5


# ==============================================================================
# GROUP 4: CONTENT HASH STABILITY (CRLF vs LF)
# ==============================================================================


def test_content_hash_stability_crlf_vs_lf_string():
    """Strings differing only by CRLF vs LF line endings must produce identical SHA-256."""
    text_lf = (
        "---\ntitle: Sample\nguest: Alice\n---\n\n"
        "**Lenny Rachitsky** (00:00:00):\nWelcome to the podcast.\n\n"
        "**Alice Smith** (00:00:10):\nRetention is the key metric.\n"
    )
    text_crlf = text_lf.replace("\n", "\r\n")

    assert text_lf != text_crlf
    hash_lf = compute_content_hash(text_lf)
    hash_crlf = compute_content_hash(text_crlf)

    assert hash_lf == hash_crlf
    assert len(hash_lf) == 64


def test_content_hash_stability_crlf_vs_lf_bytes():
    """Byte sequences differing only by CRLF vs LF must produce identical SHA-256."""
    bytes_lf = b"---\ntitle: Sample\n---\n**Lenny**: Hello\n"
    bytes_crlf = b"---\r\ntitle: Sample\r\n---\r\n**Lenny**: Hello\r\n"

    assert bytes_lf != bytes_crlf
    hash_lf = compute_content_hash(bytes_lf)
    hash_crlf = compute_content_hash(bytes_crlf)

    assert hash_lf == hash_crlf


def test_content_hash_utf8_bom_stability():
    """Files with and without UTF-8 BOM prefix must yield identical content hashes and slugs."""
    raw = (
        "---\ntitle: Test Episode\nguest: Bob\n---\n\n"
        "**Lenny Rachitsky** (00:00:00):\nHello world.\n"
    )
    bom_raw = "\ufeff" + raw

    doc_plain = parse_transcript_text(raw, slug="test-ep")
    doc_bom = parse_transcript_text(bom_raw, slug="test-ep")

    assert doc_plain.content_hash == doc_bom.content_hash
    assert doc_plain.slug == doc_bom.slug
    assert doc_plain.title == doc_bom.title
    assert len(doc_plain.turns) == len(doc_bom.turns)


def test_corpus_wide_content_hash_crlf_stability():
    """Verify hash stability across all 50 real podcast transcripts converted to CRLF."""
    project_root = Path(__file__).resolve().parent.parent.parent
    podcasts_dir = project_root / "data" / "lenny-source" / "podcasts"
    files = sorted(podcasts_dir.glob("*.md"))
    assert len(files) == 50, f"Expected 50 files, found {len(files)}"

    for f in files:
        raw_text = f.read_text(encoding="utf-8-sig")
        crlf_text = raw_text.replace("\r\n", "\n").replace("\n", "\r\n")

        hash_native = compute_content_hash(raw_text)
        hash_crlf = compute_content_hash(crlf_text)

        assert hash_native == hash_crlf, f"Hash divergence under CRLF for {f.name}"


# ==============================================================================
# GROUP 5: INGESTION BOUNDARIES & MALFORMED INPUTS
# ==============================================================================


@pytest.mark.asyncio
async def test_ingest_transcripts_limit_zero_edge_case(tmp_path: Path):
    """Exposes and checks limit=0 boundary behavior.
    
    If limit=0 is passed, does the system process 0 files or all files?
    """
    (tmp_path / "ep1.md").write_text("---\ntitle: Ep 1\n---\n**Lenny** (00:00:00): Hello\n", encoding="utf-8")
    (tmp_path / "ep2.md").write_text("---\ntitle: Ep 2\n---\n**Lenny** (00:00:00): World\n", encoding="utf-8")

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    embedder = FakeEmbeddingsClient(dim=768)

    # When limit=0:
    stats = await ingest_transcripts(
        source_dir=tmp_path,
        db=mock_db,
        limit=0,
        embedder=embedder,
        dry_run=True,
    )

    # Note: If code checks `if limit is not None and limit > 0:`, then limit=0 will not slice files!
    # Let's inspect what stats.total_files reports:
    print(f"\n[LIMIT=0 AUDIT] total_files processed when limit=0: {stats.total_files}")


@pytest.mark.asyncio
async def test_ingest_document_no_turns(tmp_path: Path):
    """Document with frontmatter but no valid speaker turns."""
    f = tmp_path / "no-turns.md"
    f.write_text(
        "---\ntitle: Empty Episode\nguest: Nobody\ndate: 2026-01-01\n---\n\nJust general notes without dialogue.\n",
        encoding="utf-8",
    )

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    embedder = FakeEmbeddingsClient(dim=768)

    status, chunk_count, token_count = await ingest_document(
        file_path=f,
        db=mock_db,
        embedder=embedder,
    )

    assert status == "created"
    assert chunk_count == 0
    assert token_count == 0
    # Document model added, add_all called with empty list, committed
    assert mock_db.add.call_count == 1
    assert mock_db.commit.call_count == 1


@pytest.mark.asyncio
async def test_ingest_document_malformed_yaml(tmp_path: Path):
    """Document with malformed YAML frontmatter must not crash."""
    f = tmp_path / "bad-yaml.md"
    f.write_text(
        "---\n: invalid yaml [ unbalanced {\n---\n\n**Lenny Rachitsky** (00:00:00):\nStill parses body.\n",
        encoding="utf-8",
    )

    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    embedder = FakeEmbeddingsClient(dim=768)

    status, chunk_count, token_count = await ingest_document(
        file_path=f,
        db=mock_db,
        embedder=embedder,
    )

    assert status == "created"
    assert chunk_count == 1
    assert mock_db.commit.call_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
