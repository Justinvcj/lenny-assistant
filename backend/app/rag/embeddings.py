"""Ollama embedding client with batching, prefixes, resilient retries, and offline fake embedder."""

import asyncio
import hashlib
import math
import random
import time
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import httpx
from app.config import get_settings
from app.errors import AppException


class EmbeddingsError(AppException):
    """Base exception for embeddings pipeline errors."""

    def __init__(self, code: str, message: str, status_code: int = 502):
        super().__init__(code=code, message=message, status_code=status_code)


class OllamaConnectionError(EmbeddingsError):
    """Raised when Ollama is unreachable after retries."""

    def __init__(self, message: str, base_url: str):
        super().__init__(
            code="llm_unavailable",
            message=f"Cannot connect to Ollama at {base_url}: {message}",
            status_code=502,
        )


class EmbeddingModelNotFoundError(EmbeddingsError):
    """Raised when the specified embedding model is missing from Ollama."""

    def __init__(self, model: str, base_url: str):
        super().__init__(
            code="embedding_model_not_found",
            message=f"Embedding model '{model}' not found in Ollama at {base_url}. Run 'ollama pull {model}'.",
            status_code=502,
        )


class EmbeddingDimensionMismatchError(EmbeddingsError):
    """Raised when the embedding dimension does not match configured EMBEDDING_DIM."""

    def __init__(self, expected: int, actual: int, model: str):
        super().__init__(
            code="embedding_dim_mismatch",
            message=(
                f"Embedding dimension mismatch: expected {expected}, but model '{model}' "
                f"returned {actual}. Check EMBEDDING_DIM in config."
            ),
            status_code=500,
        )


DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


def apply_prefix(text: str, is_query: bool = False) -> str:
    """Apply the required task prefix for nomic-embed-text asymmetric retrieval."""
    prefix = QUERY_PREFIX if is_query else DOCUMENT_PREFIX
    if text.startswith(prefix):
        return text
    # Also guard against conflicting prefix
    other_prefix = DOCUMENT_PREFIX if is_query else QUERY_PREFIX
    if text.startswith(other_prefix):
        return prefix + text[len(other_prefix):]
    return prefix + text


@runtime_checkable
class EmbeddingsClient(Protocol):
    """Protocol for embedding generation clients."""

    def get_embedding(self, text: str, is_query: bool = False) -> list[float]: ...
    def get_query_embedding(self, query: str) -> list[float]: ...
    def get_embeddings_batch(
        self, texts: Sequence[str], is_query: bool = False, batch_size: int = 32
    ) -> list[list[float]]: ...

    async def get_embedding_async(self, text: str, is_query: bool = False) -> list[float]: ...
    async def get_query_embedding_async(self, query: str) -> list[float]: ...
    async def get_embeddings_batch_async(
        self, texts: Sequence[str], is_query: bool = False, batch_size: int = 32
    ) -> list[list[float]]: ...

    def check_embedding_dim(self, expected_dim: int | None = None) -> int: ...
    async def check_embedding_dim_async(self, expected_dim: int | None = None) -> int: ...


class OllamaEmbeddingsClient:
    """Client for Ollama /api/embed endpoint with retry backoff and batch slicing."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        expected_dim: int | None = None,
        timeout_s: float = 60.0,
        max_retries: int = 3,
        initial_backoff_s: float = 1.0,
        backoff_factor: float = 2.0,
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.embedding_model
        self.expected_dim = expected_dim if expected_dim is not None else settings.embedding_dim
        self.timeout = httpx.Timeout(timeout=timeout_s, connect=10.0)
        self.max_retries = max_retries
        self.initial_backoff_s = initial_backoff_s
        self.backoff_factor = backoff_factor

    def _is_transient_status(self, status_code: int) -> bool:
        return status_code in (429, 502, 503, 504)

    def _call_embed_sync(self, prefixed_texts: list[str]) -> list[list[float]]:
        if not prefixed_texts:
            return []

        url = f"{self.base_url}/api/embed"
        payload = {"model": self.model, "input": prefixed_texts}

        last_exc: Exception | None = None

        with httpx.Client(timeout=self.timeout) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    resp = client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        embeddings = data.get("embeddings", [])
                        return embeddings

                    if resp.status_code == 404:
                        raise EmbeddingModelNotFoundError(model=self.model, base_url=self.base_url)

                    if self._is_transient_status(resp.status_code):
                        last_exc = Exception(f"HTTP {resp.status_code}: {resp.text}")
                    else:
                        resp.raise_for_status()

                except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
                    last_exc = exc
                except EmbeddingModelNotFoundError:
                    raise
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        raise EmbeddingModelNotFoundError(model=self.model, base_url=self.base_url) from exc
                    if self._is_transient_status(exc.response.status_code):
                        last_exc = exc
                    else:
                        raise OllamaConnectionError(str(exc), base_url=self.base_url) from exc

                if attempt < self.max_retries:
                    delay = self.initial_backoff_s * (self.backoff_factor ** attempt)
                    time.sleep(delay)

        raise OllamaConnectionError(
            f"Failed after {self.max_retries + 1} attempts. Last error: {last_exc}",
            base_url=self.base_url,
        )

    async def _call_embed_async(self, prefixed_texts: list[str]) -> list[list[float]]:
        if not prefixed_texts:
            return []

        url = f"{self.base_url}/api/embed"
        payload = {"model": self.model, "input": prefixed_texts}

        last_exc: Exception | None = None

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        embeddings = data.get("embeddings", [])
                        return embeddings

                    if resp.status_code == 404:
                        raise EmbeddingModelNotFoundError(model=self.model, base_url=self.base_url)

                    if self._is_transient_status(resp.status_code):
                        last_exc = Exception(f"HTTP {resp.status_code}: {resp.text}")
                    else:
                        resp.raise_for_status()

                except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
                    last_exc = exc
                except EmbeddingModelNotFoundError:
                    raise
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        raise EmbeddingModelNotFoundError(model=self.model, base_url=self.base_url) from exc
                    if self._is_transient_status(exc.response.status_code):
                        last_exc = exc
                    else:
                        raise OllamaConnectionError(str(exc), base_url=self.base_url) from exc

                if attempt < self.max_retries:
                    delay = self.initial_backoff_s * (self.backoff_factor ** attempt)
                    await asyncio.sleep(delay)

        raise OllamaConnectionError(
            f"Failed after {self.max_retries + 1} attempts. Last error: {last_exc}",
            base_url=self.base_url,
        )

    def get_embeddings_batch(
        self, texts: Sequence[str], is_query: bool = False, batch_size: int = 32
    ) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float]] = []
        prefixed = [apply_prefix(t, is_query=is_query) for t in texts]

        for i in range(0, len(prefixed), batch_size):
            chunk = prefixed[i : i + batch_size]
            batch_embeddings = self._call_embed_sync(chunk)
            results.extend(batch_embeddings)

        return results

    async def get_embeddings_batch_async(
        self, texts: Sequence[str], is_query: bool = False, batch_size: int = 32
    ) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float]] = []
        prefixed = [apply_prefix(t, is_query=is_query) for t in texts]

        for i in range(0, len(prefixed), batch_size):
            chunk = prefixed[i : i + batch_size]
            batch_embeddings = await self._call_embed_async(chunk)
            results.extend(batch_embeddings)

        return results

    def get_embedding(self, text: str, is_query: bool = False) -> list[float]:
        res = self.get_embeddings_batch([text], is_query=is_query, batch_size=1)
        if not res:
            raise EmbeddingsError(code="empty_embedding_result", message="No embedding returned")
        return res[0]

    def get_query_embedding(self, query: str) -> list[float]:
        return self.get_embedding(query, is_query=True)

    async def get_embedding_async(self, text: str, is_query: bool = False) -> list[float]:
        res = await self.get_embeddings_batch_async([text], is_query=is_query, batch_size=1)
        if not res:
            raise EmbeddingsError(code="empty_embedding_result", message="No embedding returned")
        return res[0]

    async def get_query_embedding_async(self, query: str) -> list[float]:
        return await self.get_embedding_async(query, is_query=True)

    def check_embedding_dim(self, expected_dim: int | None = None) -> int:
        target_dim = self.expected_dim if expected_dim is None else expected_dim
        sample = self.get_query_embedding("dimension check probe")
        actual_dim = len(sample)
        if actual_dim != target_dim:
            raise EmbeddingDimensionMismatchError(
                expected=target_dim, actual=actual_dim, model=self.model
            )
        return actual_dim

    async def check_embedding_dim_async(self, expected_dim: int | None = None) -> int:
        target_dim = self.expected_dim if expected_dim is None else expected_dim
        sample = await self.get_query_embedding_async("dimension check probe")
        actual_dim = len(sample)
        if actual_dim != target_dim:
            raise EmbeddingDimensionMismatchError(
                expected=target_dim, actual=actual_dim, model=self.model
            )
        return actual_dim


class FakeEmbeddingsClient:
    """Deterministic, unit-normalized fake embedder for offline unit testing without Ollama."""

    def __init__(self, dim: int = 768):
        self.dim = dim
        self.call_count: int = 0
        self.calls: list[list[str]] = []

    def _generate_vector(self, text: str, is_query: bool = False) -> list[float]:
        prefixed = apply_prefix(text, is_query=is_query)
        # Use sha256 hash as seed to produce deterministic pseudo-random values
        seed_bytes = hashlib.sha256(prefixed.encode("utf-8")).digest()
        seed_int = int.from_bytes(seed_bytes[:8], "big")
        rng = random.Random(seed_int)

        # Generate Gaussian distributed vector
        raw = [rng.gauss(0.0, 1.0) for _ in range(self.dim)]

        # Also add word-level token signals so vocabulary overlap produces higher similarity
        words = prefixed.lower().split()
        for word in words:
            w_hash = int.from_bytes(hashlib.md5(word.encode("utf-8")).digest()[:4], "big")
            idx = w_hash % self.dim
            raw[idx] += 2.0

        # L2-normalize
        norm = math.sqrt(sum(x * x for x in raw))
        if norm == 0.0:
            return [1.0 / math.sqrt(self.dim)] * self.dim
        return [x / norm for x in raw]

    def get_embeddings_batch(
        self, texts: Sequence[str], is_query: bool = False, batch_size: int = 32
    ) -> list[list[float]]:
        self.call_count += 1
        text_list = list(texts)
        self.calls.append(text_list)
        return [self._generate_vector(t, is_query=is_query) for t in text_list]

    async def get_embeddings_batch_async(
        self, texts: Sequence[str], is_query: bool = False, batch_size: int = 32
    ) -> list[list[float]]:
        return self.get_embeddings_batch(texts, is_query=is_query, batch_size=batch_size)

    def get_embedding(self, text: str, is_query: bool = False) -> list[float]:
        self.call_count += 1
        self.calls.append([text])
        return self._generate_vector(text, is_query=is_query)

    def get_query_embedding(self, query: str) -> list[float]:
        return self.get_embedding(query, is_query=True)

    async def get_embedding_async(self, text: str, is_query: bool = False) -> list[float]:
        return self.get_embedding(text, is_query=is_query)

    async def get_query_embedding_async(self, query: str) -> list[float]:
        return self.get_query_embedding(query)

    def check_embedding_dim(self, expected_dim: int | None = None) -> int:
        target = self.dim if expected_dim is None else expected_dim
        if self.dim != target:
            raise EmbeddingDimensionMismatchError(expected=target, actual=self.dim, model="fake")
        return self.dim

    async def check_embedding_dim_async(self, expected_dim: int | None = None) -> int:
        return self.check_embedding_dim(expected_dim)


# Module-level default singleton management
_global_client: EmbeddingsClient | None = None


def get_embeddings_client() -> EmbeddingsClient:
    """Get the active embeddings client singleton, defaulting to OllamaEmbeddingsClient."""
    global _global_client
    if _global_client is None:
        _global_client = OllamaEmbeddingsClient()
    return _global_client


def set_embeddings_client(client: EmbeddingsClient | None) -> None:
    """Set or override the global embeddings client (e.g. for testing with FakeEmbeddingsClient)."""
    global _global_client
    _global_client = client


def get_embedding(text: str, is_query: bool = False) -> list[float]:
    return get_embeddings_client().get_embedding(text, is_query=is_query)


def get_query_embedding(query: str) -> list[float]:
    return get_embeddings_client().get_query_embedding(query)


def get_embeddings_batch(
    texts: Sequence[str], is_query: bool = False, batch_size: int = 32
) -> list[list[float]]:
    return get_embeddings_client().get_embeddings_batch(texts, is_query=is_query, batch_size=batch_size)


async def get_embedding_async(text: str, is_query: bool = False) -> list[float]:
    return await get_embeddings_client().get_embedding_async(text, is_query=is_query)


async def get_query_embedding_async(query: str) -> list[float]:
    return await get_embeddings_client().get_query_embedding_async(query)


async def get_embeddings_batch_async(
    texts: Sequence[str], is_query: bool = False, batch_size: int = 32
) -> list[list[float]]:
    return await get_embeddings_client().get_embeddings_batch_async(
        texts, is_query=is_query, batch_size=batch_size
    )


def check_embedding_dim(expected_dim: int | None = None) -> int:
    return get_embeddings_client().check_embedding_dim(expected_dim)


async def check_embedding_dim_async(expected_dim: int | None = None) -> int:
    return await get_embeddings_client().check_embedding_dim_async(expected_dim)
