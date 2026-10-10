"""Idempotent transcript ingestion pipeline for Lenny Growth Assistant."""

import inspect
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Chunk, Document, utc_now
from app.rag.chunking import ChunkDraft, chunk_document
from app.rag.embeddings import get_embeddings_client
from app.rag.parser import ParsedDocument, parse_transcript_file

logger = logging.getLogger(__name__)


@dataclass
class IngestionStats:
    """Summary metrics of an ingestion run."""

    total_files: int = 0
    created_docs: int = 0
    updated_docs: int = 0
    skipped_docs: int = 0
    total_chunks: int = 0
    total_tokens: int = 0
    errors: List[Dict[str, str]] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, self.end_time - self.start_time)


def resolve_data_dir(data_dir_arg: Optional[str] = None) -> Path:
    """Resolve the transcript directory across Docker container and Windows host environments."""
    settings = get_settings()

    candidates: List[Path] = []
    if data_dir_arg:
        candidates.append(Path(data_dir_arg))

    # Docker container volume mount
    if settings.data_dir:
        candidates.append(Path(settings.data_dir))
        candidates.append(Path(settings.data_dir) / "lenny-source" / "podcasts")
        candidates.append(Path(settings.data_dir) / "podcasts")

    # Local host repo root candidates
    cwd = Path.cwd()
    candidates.extend(
        [
            cwd / "data" / "lenny-source" / "podcasts",
            cwd / "data" / "lenny-source",
            cwd / "data" / "podcasts",
            cwd / "data",
            cwd.parent / "data" / "lenny-source" / "podcasts",
            cwd.parent / "data" / "lenny-source",
            cwd.parent / "data",
        ]
    )

    for cand in candidates:
        if cand.is_dir():
            # Check if this dir or its podcasts subdir contains .md files
            if (cand / "podcasts").is_dir() and any((cand / "podcasts").glob("*.md")):
                return cand / "podcasts"
            if any(cand.glob("*.md")):
                return cand

    # Default fallback
    return Path(data_dir_arg or settings.data_dir)


async def _get_embeddings_for_chunks(
    chunk_texts: Sequence[str],
    embedder: Any,
    batch_size: int,
) -> List[List[float]]:
    if not chunk_texts:
        return []

    client = embedder or get_embeddings_client()
    if hasattr(client, "get_embeddings_batch_async"):
        return await client.get_embeddings_batch_async(
            chunk_texts, is_query=False, batch_size=batch_size
        )
    elif hasattr(client, "get_embeddings_batch"):
        return client.get_embeddings_batch(
            chunk_texts, is_query=False, batch_size=batch_size
        )
    else:
        # Fallback to single calls
        return [client.get_embedding(t, is_query=False) for t in chunk_texts]


async def ingest_document(
    file_path: Path | str,
    db: AsyncSession,
    embedder: Optional[Any] = None,
    batch_size: int = 32,
    force: bool = False,
    dry_run: bool = False,
) -> Tuple[str, int, int]:
    """Ingest a single transcript file with strict idempotency by content_hash.

    Returns:
        tuple of (status, chunk_count, token_count)
        where status is 'created', 'updated', or 'skipped'.
    """
    path = Path(file_path)
    parsed: ParsedDocument = parse_transcript_file(path)

    # 1. Check for existing document by slug
    stmt = select(Document).where(Document.slug == parsed.slug)
    res = await db.execute(stmt)
    existing_doc = res.scalar_one_or_none()
    if inspect.isawaitable(existing_doc):
        existing_doc = await existing_doc

    # 2. Idempotency check: unchanged file
    if existing_doc is not None and not force and existing_doc.content_hash == parsed.content_hash:
        # Count existing chunks
        cnt_stmt = select(func.count(Chunk.id)).where(Chunk.document_id == existing_doc.id)
        cnt_res = await db.execute(cnt_stmt)
        existing_chunk_count = cnt_res.scalar() or 0
        if inspect.isawaitable(existing_chunk_count):
            existing_chunk_count = await existing_chunk_count
        return ("skipped", int(existing_chunk_count), 0)

    # 3. Chunk the parsed document
    target_doc_id = existing_doc.id if existing_doc is not None else uuid.uuid4()
    chunks: List[ChunkDraft] = chunk_document(parsed, document_id=target_doc_id)
    token_sum = sum(c.token_count or 0 for c in chunks)

    # 4. Dry-run mode bypasses embedding and database writes
    if dry_run:
        status = "updated" if existing_doc is not None else "created"
        return (status, len(chunks), token_sum)

    # 5. Generate embeddings for chunk texts in batches
    chunk_texts = [c.text for c in chunks]
    embeddings = await _get_embeddings_for_chunks(chunk_texts, embedder, batch_size=batch_size)

    # 6. Database upsert within atomic per-document transaction
    if existing_doc is not None:
        # Delete old chunks
        await db.execute(delete(Chunk).where(Chunk.document_id == existing_doc.id))

        # Update document attributes
        existing_doc.title = parsed.title
        existing_doc.guest = parsed.guest
        existing_doc.published_at = parsed.published_at
        existing_doc.source_path = str(path)
        existing_doc.content_hash = parsed.content_hash
        existing_doc.metadata_ = parsed.metadata
        existing_doc.updated_at = utc_now()
        status = "updated"
    else:
        # Insert new document
        doc_model = parsed.to_document_model(doc_id=target_doc_id)
        doc_model.source_path = str(path)
        db.add(doc_model)
        status = "created"

    # 7. Insert new chunk models with pgvector embeddings
    chunk_models = [
        draft.to_chunk_model(document_id=target_doc_id, embedding=emb)
        for draft, emb in zip(chunks, embeddings)
    ]
    db.add_all(chunk_models)
    await db.commit()

    return (status, len(chunk_models), token_sum)


async def ingest_transcripts(
    source_dir: Path | str,
    db: AsyncSession,
    limit: Optional[int] = None,
    embedder: Optional[Any] = None,
    batch_size: int = 32,
    force: bool = False,
    dry_run: bool = False,
    on_progress: Optional[Callable[[int, int, str, str, int], None]] = None,
) -> IngestionStats:
    """Ingest all transcript files in source_dir with progress tracking and idempotency."""
    dir_path = Path(source_dir)
    stats = IngestionStats(start_time=time.time())

    if not dir_path.is_dir():
        stats.end_time = time.time()
        stats.errors.append({"file": str(dir_path), "error": "Source directory does not exist"})
        return stats

    # Collect markdown files, preferring podcasts folder if present
    target_dir = dir_path
    if (dir_path / "podcasts").is_dir() and any((dir_path / "podcasts").glob("*.md")):
        target_dir = dir_path / "podcasts"

    files = sorted(list(target_dir.glob("*.md")), key=lambda p: p.name)
    if limit is not None and limit > 0:
        files = files[:limit]

    stats.total_files = len(files)

    for idx, file_path in enumerate(files):
        slug = file_path.stem
        try:
            status, chunk_count, token_count = await ingest_document(
                file_path=file_path,
                db=db,
                embedder=embedder,
                batch_size=batch_size,
                force=force,
                dry_run=dry_run,
            )

            if status == "created":
                stats.created_docs += 1
                stats.total_chunks += chunk_count
                stats.total_tokens += token_count
            elif status == "updated":
                stats.updated_docs += 1
                stats.total_chunks += chunk_count
                stats.total_tokens += token_count
            elif status == "skipped":
                stats.skipped_docs += 1
                stats.total_chunks += chunk_count

            if on_progress:
                on_progress(idx + 1, stats.total_files, slug, status, chunk_count)

        except Exception as exc:
            logger.error("Failed to ingest %s: %s", file_path, exc, exc_info=True)
            await db.rollback()
            stats.errors.append({"file": str(file_path), "error": str(exc)})
            if on_progress:
                on_progress(idx + 1, stats.total_files, slug, f"error: {exc}", 0)

    stats.end_time = time.time()
    return stats
