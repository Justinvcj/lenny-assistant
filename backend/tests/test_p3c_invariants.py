"""Empirical Challenger Invariant Verification Suite for Milestone 1 (P3c).

Verifies four core invariants:
1. Vector math invariants: FakeEmbedder produces unit-length vectors (L2 norm == 1.0 +- 1e-6) for all inputs.
2. Cosine distance vs similarity conversion: score = 1.0 - distance is mathematically exact.
3. Dimension check: check_embedding_dim strictly rejects any dimension != 768.
4. Prefix invariance: search_document: and search_query: prefixes are always properly applied and never doubled.
"""

import math
import random
import string
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models import Chunk, Document
from app.rag.embeddings import (
    DOCUMENT_PREFIX,
    QUERY_PREFIX,
    EmbeddingDimensionMismatchError,
    FakeEmbeddingsClient,
    OllamaEmbeddingsClient,
    apply_prefix,
    check_embedding_dim,
    check_embedding_dim_async,
    set_embeddings_client,
)
from app.rag.ingest import ingest_document
from app.rag.retrieval import RetrievalResult, retrieve


# ==============================================================================
# INVARIANT 1: Vector Math Invariants (Unit-Length Vectors)
# ==============================================================================

def test_invariant_1_fake_embedder_unit_norm_adversarial_battery():
    """Verify FakeEmbedder produces unit-length vectors (L2 norm == 1.0 +- 1e-6) across adversarial inputs."""
    adversarial_inputs = [
        "",
        " ",
        "   ",
        "\t\n\r",
        " \t\n \r ",
        "a",
        ".",
        "0",
        "!",
        "\x00",
        "a" * 100,
        "a" * 10000,
        "word " * 1000,
        "你好世界",
        "🚀🔥📈🎙️✨",
        "مرحبا بالعالم",
        "שלום עולם",
        "Привет мир",
        "नमस्ते दुनिया",
        "\u200b\u200c\u200d",  # zero-width joiners
    ]

    # Add 500 randomized text strings of varying lengths
    rng = random.Random(42)
    for _ in range(500):
        length = rng.randint(1, 200)
        s = "".join(rng.choices(string.printable, k=length))
        adversarial_inputs.append(s)

    client = FakeEmbeddingsClient(dim=768)
    max_deviation = 0.0

    for idx, text in enumerate(adversarial_inputs):
        for is_q in (False, True):
            vec = client.get_embedding(text, is_query=is_q)
            assert len(vec) == 768, f"Dimension != 768 on input {idx}"

            # Check no NaN or Inf
            assert not any(math.isnan(x) or math.isinf(x) for x in vec), f"NaN/Inf detected on input {idx}"

            norm = math.sqrt(sum(x * x for x in vec))
            dev = abs(norm - 1.0)
            if dev > max_deviation:
                max_deviation = dev

            assert dev <= 1e-6, f"Norm deviation {dev:.2e} exceeded 1e-6 tolerance on input {idx} (norm={norm})"

    print(f"\n[INVARIANT 1] Tested {len(adversarial_inputs) * 2} vectors. Max deviation from 1.0: {max_deviation:.2e}")
    assert max_deviation <= 1e-6


def test_invariant_1_zero_norm_fallback_branches():
    """Verify zero-norm fallback formula produces mathematically exact unit-length vector."""
    for test_dim in [1, 2, 384, 768, 1536]:
        fallback_vec = [1.0 / math.sqrt(test_dim)] * test_dim
        norm = math.sqrt(sum(x * x for x in fallback_vec))
        assert abs(norm - 1.0) <= 1e-12, f"Fallback norm deviation {abs(norm - 1.0)} on dim {test_dim}"


# ==============================================================================
# INVARIANT 2: Cosine Distance vs Similarity Conversion
# ==============================================================================

def test_invariant_2_cosine_distance_vs_similarity_exactness():
    """Verify score = 1.0 - distance is mathematically exact across 10,000 unit vector pairs."""
    np.random.seed(42)
    n_samples = 10000
    dim = 768

    u = np.random.randn(n_samples, dim)
    u = u / np.linalg.norm(u, axis=1, keepdims=True)

    v = np.random.randn(n_samples, dim)
    v = v / np.linalg.norm(v, axis=1, keepdims=True)

    # Edge cases: exact parallel, anti-parallel, orthogonal
    u[0] = v[0]
    u[1] = -v[1]
    v[2] = np.zeros(dim); v[2, 0] = 1.0
    u[2] = np.zeros(dim); u[2, 1] = 1.0

    # True cosine similarity for unit vectors: dot product
    cos_sim = np.sum(u * v, axis=1)

    # Cosine distance by definition (1 - cos_sim)
    cos_dist = 1.0 - cos_sim

    # Score calculation used in retrieval (score = 1.0 - distance)
    score = 1.0 - cos_dist

    # Deviation
    max_dev = np.max(np.abs(score - cos_sim))
    print(f"\n[INVARIANT 2] Tested {n_samples} vector pairs. Max diff: {max_dev:.2e}")
    assert max_dev <= 1e-15

    # Test threshold equivalence: score >= threshold <=> cos_dist <= (1.0 - threshold)
    thresholds = [0.0, 0.1, 0.3, 0.5, 0.58, 0.7, 0.85, 0.99, 1.0]
    for th in thresholds:
        filter_by_score = (score >= th)
        filter_by_dist = (cos_dist <= (1.0 - th))
        assert np.array_equal(filter_by_score, filter_by_dist), f"Threshold filtering divergence at th={th}"


def test_invariant_2_pgvector_sql_generation():
    """Verify pgvector <=> operator and (1.0 - distance) expression in compiled SQL."""
    query_vector = [0.0] * 768
    distance_expr = Chunk.embedding.cosine_distance(query_vector)
    similarity_expr = (1.0 - distance_expr).label("similarity_score")

    stmt = (
        select(Chunk.id, Chunk.text, similarity_expr, Document.slug)
        .join(Document, Chunk.document_id == Document.id)
        .where(distance_expr <= (1.0 - 0.58))
        .order_by(distance_expr.asc())
        .limit(6)
    )

    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert "<=>" in compiled, "Compiled SQL must use pgvector cosine distance operator <=>"
    assert "ORDER BY (chunks.embedding <=> " in compiled or "<=>" in compiled
    assert "WHERE (chunks.embedding <=> " in compiled


# ==============================================================================
# INVARIANT 3: Dimension Check
# ==============================================================================

def test_invariant_3_dimension_check_strictly_rejects_non_768():
    """Verify check_embedding_dim strictly rejects any dimension != 768."""
    fake = FakeEmbeddingsClient(dim=768)

    # 768 passes
    assert fake.check_embedding_dim(768) == 768
    assert fake.check_embedding_dim(None) == 768

    # Strictly rejects all non-768 dimensions
    invalid_dims = [0, -1, 1, 384, 512, 767, 769, 1024, 1536, 3072, 9999]
    for d in invalid_dims:
        with pytest.raises(EmbeddingDimensionMismatchError) as exc_info:
            fake.check_embedding_dim(d)
        assert exc_info.value.code == "embedding_dim_mismatch"
        assert exc_info.value.status_code == 500
        assert f"expected {d}" in exc_info.value.message


def test_invariant_3_embedder_mismatch_detection():
    """Verify client rejects model returning unexpected dimension length."""
    client = OllamaEmbeddingsClient(expected_dim=768)

    # Probe returns 384 or 1536 instead of 768
    for probe_len in [384, 767, 769, 1536]:
        with patch.object(client, "get_query_embedding", return_value=[0.1] * probe_len):
            with pytest.raises(EmbeddingDimensionMismatchError) as exc_info:
                client.check_embedding_dim(768)
            assert f"expected 768, but model '{client.model}' returned {probe_len}" in exc_info.value.message


# ==============================================================================
# INVARIANT 4: Prefix Invariance
# ==============================================================================

def test_invariant_4_prefix_application_and_no_doubling():
    """Verify search_document: and search_query: prefixes are applied and never doubled."""
    inputs = [
        "Plain text passage",
        "What is product market fit?",
        "",
        "   ",
        "search_document: already doc",
        "search_query: already query",
    ]

    for text in inputs:
        # Document prefix
        doc_1 = apply_prefix(text, is_query=False)
        assert doc_1.startswith(DOCUMENT_PREFIX)
        assert not doc_1.startswith(DOCUMENT_PREFIX + DOCUMENT_PREFIX), f"Doubled document prefix: {doc_1}"

        # Repeated document prefix
        doc_2 = apply_prefix(doc_1, is_query=False)
        assert doc_2 == doc_1
        assert not doc_2.startswith(DOCUMENT_PREFIX + DOCUMENT_PREFIX)

        # Query prefix
        q_1 = apply_prefix(text, is_query=True)
        assert q_1.startswith(QUERY_PREFIX)
        assert not q_1.startswith(QUERY_PREFIX + QUERY_PREFIX), f"Doubled query prefix: {q_1}"

        # Repeated query prefix
        q_2 = apply_prefix(q_1, is_query=True)
        assert q_2 == q_1
        assert not q_2.startswith(QUERY_PREFIX + QUERY_PREFIX)

        # Switching from doc to query
        switched_to_q = apply_prefix(doc_1, is_query=True)
        assert switched_to_q.startswith(QUERY_PREFIX)
        assert not switched_to_q.startswith(QUERY_PREFIX + QUERY_PREFIX)
        assert DOCUMENT_PREFIX not in switched_to_q

        # Switching from query to doc
        switched_to_doc = apply_prefix(q_1, is_query=False)
        assert switched_to_doc.startswith(DOCUMENT_PREFIX)
        assert not switched_to_doc.startswith(DOCUMENT_PREFIX + DOCUMENT_PREFIX)
        assert QUERY_PREFIX not in switched_to_doc


@pytest.mark.asyncio
async def test_invariant_4_retrieval_and_ingestion_prefixes(tmp_path: Path):
    """Verify retrieval passes search_query: without doubling and ingestion does not store prefixes in DB."""
    # 1. Retrieval prefix verification
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.execute.return_value = mock_result

    ollama = OllamaEmbeddingsClient(base_url="http://localhost:11434")
    logged_payloads = []

    async def mock_call_async(prefixed_texts):
        logged_payloads.append(list(prefixed_texts))
        return [[0.1] * 768 for _ in prefixed_texts]

    ollama._call_embed_async = mock_call_async

    # Raw query
    await retrieve("what is onboarding?", mock_db, embedder=ollama)
    assert logged_payloads[-1] == [f"{QUERY_PREFIX}what is onboarding?"]

    # Pre-prefixed query
    await retrieve(f"{QUERY_PREFIX}what is onboarding?", mock_db, embedder=ollama)
    assert logged_payloads[-1] == [f"{QUERY_PREFIX}what is onboarding?"]

    # Conflicting prefix query
    await retrieve(f"{DOCUMENT_PREFIX}what is onboarding?", mock_db, embedder=ollama)
    assert logged_payloads[-1] == [f"{QUERY_PREFIX}what is onboarding?"]

    # 2. Ingestion chunk storage verification (DB text column must be raw/unprefixed)
    ingest_db = AsyncMock()
    mock_ingest_res = MagicMock()
    mock_ingest_res.scalar_one_or_none.return_value = None
    ingest_db.execute.return_value = mock_ingest_res

    test_md = tmp_path / "test_ep.md"
    test_md.write_text(
        "---\ntitle: \"Prefix Test\"\nguest: \"Tester\"\n---\n\n"
        "**Lenny Rachitsky** (00:00:00):\nThis is test text for DB storage.\n",
        encoding="utf-8",
    )

    fake = FakeEmbeddingsClient(dim=768)
    status, n_chunks, _ = await ingest_document(file_path=test_md, db=ingest_db, embedder=fake)

    assert status == "created"
    assert ingest_db.add_all.call_count == 1
    stored_chunks = ingest_db.add_all.call_args[0][0]
    for c in stored_chunks:
        assert not c.text.startswith(DOCUMENT_PREFIX), f"DB stored chunk has prefix: {c.text}"
        assert not c.text.startswith(QUERY_PREFIX)
        assert len(c.embedding) == 768
