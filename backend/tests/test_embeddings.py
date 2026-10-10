"""Unit tests for Ollama embeddings client, prefixes, and FakeEmbeddingsClient."""

import math
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.rag.embeddings import (
    DOCUMENT_PREFIX,
    QUERY_PREFIX,
    EmbeddingDimensionMismatchError,
    EmbeddingModelNotFoundError,
    FakeEmbeddingsClient,
    OllamaConnectionError,
    OllamaEmbeddingsClient,
    apply_prefix,
    check_embedding_dim,
    get_embedding,
    get_embeddings_batch,
    get_query_embedding,
    set_embeddings_client,
)


def test_apply_prefix():
    # Document prefix
    doc_res = apply_prefix("This is a transcript excerpt.", is_query=False)
    assert doc_res == f"{DOCUMENT_PREFIX}This is a transcript excerpt."

    # Query prefix
    query_res = apply_prefix("What is activation rate?", is_query=True)
    assert query_res == f"{QUERY_PREFIX}What is activation rate?"

    # Guard against double prefixing
    assert apply_prefix(doc_res, is_query=False) == doc_res
    assert apply_prefix(query_res, is_query=True) == query_res

    # Switching prefix
    switched = apply_prefix(doc_res, is_query=True)
    assert switched == f"{QUERY_PREFIX}This is a transcript excerpt."


def test_fake_embedder_deterministic_and_normalized():
    client = FakeEmbeddingsClient(dim=768)

    v1 = client.get_embedding("Product market fit and retention", is_query=False)
    v2 = client.get_embedding("Product market fit and retention", is_query=False)
    v3 = client.get_embedding("Completely unrelated text about baking", is_query=False)

    assert len(v1) == 768
    assert len(v2) == 768
    assert len(v3) == 768

    # Determinism
    assert v1 == v2
    assert v1 != v3

    # Unit norm (L2 norm == 1.0)
    norm1 = math.sqrt(sum(x * x for x in v1))
    norm3 = math.sqrt(sum(x * x for x in v3))
    assert pytest.approx(norm1, abs=1e-5) == 1.0
    assert pytest.approx(norm3, abs=1e-5) == 1.0


def test_fake_embedder_batching_and_tracking():
    client = FakeEmbeddingsClient(dim=768)
    texts = [f"Text chunk number {i}" for i in range(70)]

    results = client.get_embeddings_batch(texts, is_query=False, batch_size=32)
    assert len(results) == 70
    assert client.call_count == 1
    assert len(client.calls[0]) == 70

    # Query embedding
    q_vec = client.get_query_embedding("search question")
    assert len(q_vec) == 768


def test_fake_embedder_dimension_validation():
    client = FakeEmbeddingsClient(dim=768)
    assert client.check_embedding_dim(768) == 768

    with pytest.raises(EmbeddingDimensionMismatchError) as exc_info:
        client.check_embedding_dim(384)
    assert "Embedding dimension mismatch" in exc_info.value.message


def test_empty_batch_returns_empty():
    client = OllamaEmbeddingsClient()
    assert client.get_embeddings_batch([]) == []


def test_ollama_404_fails_fast_without_retries():
    client = OllamaEmbeddingsClient(
        base_url="http://localhost:11434",
        model="nonexistent-model",
        max_retries=3,
        initial_backoff_s=0.01,
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = '{"error":"model not found"}'

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        with pytest.raises(EmbeddingModelNotFoundError) as exc_info:
            client.get_embedding("hello")

        assert exc_info.value.code == "embedding_model_not_found"
        assert "nonexistent-model" in exc_info.value.message
        # Must fail immediately on first attempt without retrying
        assert mock_post.call_count == 1


def test_ollama_transient_retry_success():
    client = OllamaEmbeddingsClient(
        base_url="http://localhost:11434",
        model="nomic-embed-text",
        max_retries=3,
        initial_backoff_s=0.01,
        backoff_factor=1.0,
    )

    # Attempt 1: Timeout, Attempt 2: 503, Attempt 3: 200 OK
    resp_503 = MagicMock()
    resp_503.status_code = 503
    resp_503.text = "Service Unavailable"

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {"embeddings": [[0.1] * 768]}

    with patch("httpx.Client.post", side_effect=[httpx.ReadTimeout("timeout"), resp_503, resp_200]) as mock_post:
        with patch("time.sleep", return_value=None):
            result = client.get_embedding("test retry")

        assert len(result) == 768
        assert mock_post.call_count == 3


def test_ollama_exhausted_retries_raises_connection_error():
    client = OllamaEmbeddingsClient(
        base_url="http://localhost:11434",
        model="nomic-embed-text",
        max_retries=2,
        initial_backoff_s=0.01,
    )

    with patch("httpx.Client.post", side_effect=httpx.ConnectError("Connection refused")):
        with patch("time.sleep", return_value=None):
            with pytest.raises(OllamaConnectionError) as exc_info:
                client.get_embedding("test failure")

            assert exc_info.value.code == "llm_unavailable"
            assert "Cannot connect to Ollama" in exc_info.value.message


def test_dimension_mismatch_raises_error():
    client = OllamaEmbeddingsClient(expected_dim=768)

    # Return 384 dimensions instead of 768
    with patch.object(client, "get_query_embedding", return_value=[0.1] * 384):
        with pytest.raises(EmbeddingDimensionMismatchError) as exc_info:
            client.check_embedding_dim(768)

        assert exc_info.value.code == "embedding_dim_mismatch"
        assert "expected 768, but model 'nomic-embed-text' returned 384" in exc_info.value.message


@pytest.mark.asyncio
async def test_async_methods_and_global_client_override():
    fake = FakeEmbeddingsClient(dim=768)
    set_embeddings_client(fake)
    try:
        vec = await fake.get_embedding_async("async test", is_query=False)
        assert len(vec) == 768

        qvec = await fake.get_query_embedding_async("async query")
        assert len(qvec) == 768

        batch = await fake.get_embeddings_batch_async(["chunk 1", "chunk 2"])
        assert len(batch) == 2

        dim = await fake.check_embedding_dim_async()
        assert dim == 768

        # Test global helpers with fake injected
        g_vec = get_embedding("global text")
        assert len(g_vec) == 768
        g_qvec = get_query_embedding("global query")
        assert len(g_qvec) == 768
        g_batch = get_embeddings_batch(["a", "b"])
        assert len(g_batch) == 2
        assert check_embedding_dim(768) == 768
    finally:
        set_embeddings_client(None)


def test_live_ollama_integration():
    """Live integration test against host Ollama instance (skipped if unreachable)."""
    import socket

    s = socket.socket()
    s.settimeout(0.5)
    try:
        s.connect(("localhost", 11434))
        s.close()
    except Exception:
        pytest.skip("Ollama is not reachable on localhost:11434")

    client = OllamaEmbeddingsClient(base_url="http://localhost:11434")
    dim = client.check_embedding_dim(768)
    assert dim == 768

    # Verify query and document embedding
    doc_vec = client.get_embedding("This is a document about product growth.")
    assert len(doc_vec) == 768

    q_vec = client.get_query_embedding("product growth")
    assert len(q_vec) == 768
