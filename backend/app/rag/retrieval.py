"""pgvector-based retrieval for Lenny Growth Assistant."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.models import Chunk, Document
from app.rag.embeddings import get_embeddings_client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


@dataclass
class RetrievalResult:
    """Standardized retrieval result representation for prompts and citations."""

    chunk_id: uuid.UUID
    text: str
    score: float
    document_slug: str
    title: str
    guest: str | None
    speaker: str | None
    start_char: int | None
    end_char: int | None
    chunk_index: int


async def retrieve(
    query: str,
    db: AsyncSession,
    top_k: int | None = None,
    min_score: float | None = None,
    embedder: Any | None = None,
) -> list[RetrievalResult]:
    """Retrieve top-k chunks matching query using pgvector cosine similarity.

    Args:
        query: User question or search query string.
        db: AsyncSession database handle.
        top_k: Number of chunks to retrieve (defaults to settings.retrieval_top_k).
        min_score: Cosine similarity floor (defaults to 0.0, filtering below threshold).
        embedder: Optional embedding client override (for testing or custom providers).

    Returns:
        List of RetrievalResult objects ordered by cosine similarity descending.
    """
    clean_query = query.strip()
    if not clean_query:
        return []

    settings = get_settings()
    k = top_k if (top_k is not None and top_k > 0) else settings.retrieval_top_k
    threshold = min_score if min_score is not None else 0.0

    # Obtain query embedding with "search_query: " prefix
    client = embedder or get_embeddings_client()
    if hasattr(client, "get_query_embedding_async"):
        query_vector = await client.get_query_embedding_async(clean_query)
    elif hasattr(client, "get_query_embedding"):
        query_vector = client.get_query_embedding(clean_query)
    elif hasattr(client, "get_embedding_async"):
        query_vector = await client.get_embedding_async(clean_query, is_query=True)
    else:
        query_vector = client.get_embedding(clean_query, is_query=True)

    # Cosine distance operator in pgvector: <=>
    # Cosine similarity = 1 - cosine_distance
    distance_expr = Chunk.embedding.cosine_distance(query_vector)
    similarity_expr = (1.0 - distance_expr).label("similarity_score")

    stmt = (
        select(
            Chunk.id,
            Chunk.text,
            similarity_expr,
            Document.slug,
            Document.title,
            Document.guest,
            Chunk.speaker,
            Chunk.start_char,
            Chunk.end_char,
            Chunk.chunk_index,
        )
        .join(Document, Chunk.document_id == Document.id)
    )

    if threshold > 0.0:
        # cosine_similarity >= threshold <=> cosine_distance <= 1.0 - threshold
        stmt = stmt.where(distance_expr <= (1.0 - threshold))

    stmt = stmt.order_by(distance_expr.asc()).limit(k)

    result = await db.execute(stmt)
    rows = result.all()

    results: list[RetrievalResult] = []
    for row in rows:
        results.append(
            RetrievalResult(
                chunk_id=row[0],
                text=row[1],
                score=float(row[2]),
                document_slug=row[3],
                title=row[4],
                guest=row[5],
                speaker=row[6],
                start_char=row[7],
                end_char=row[8],
                chunk_index=row[9],
            )
        )

    return results


async def get_chunks_by_ids(
    chunk_ids: Sequence[uuid.UUID], db: AsyncSession
) -> list[Chunk]:
    """Fetch Chunk models with their related Document loaded by UUIDs.

    Preserves the relative ordering of the input chunk_ids list.
    """
    if not chunk_ids:
        return []

    # Deduplicate while preserving order for lookup
    unique_ids = list(dict.fromkeys(chunk_ids))

    stmt = (
        select(Chunk)
        .where(Chunk.id.in_(unique_ids))
        .options(selectinload(Chunk.document))
    )
    result = await db.execute(stmt)
    chunks_found = result.scalars().all()

    chunk_map = {c.id: c for c in chunks_found}
    ordered_chunks: list[Chunk] = []
    for cid in chunk_ids:
        if cid in chunk_map and chunk_map[cid] not in ordered_chunks:
            ordered_chunks.append(chunk_map[cid])

    return ordered_chunks
