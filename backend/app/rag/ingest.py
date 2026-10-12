"""Idempotent transcript ingestion pipeline for Lenny Growth Assistant."""

import inspect
import logging
import time
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.models import Chunk, Document, utc_now
from app.rag.chunking import ChunkDraft, chunk_document
from app.rag.embeddings import get_embeddings_client
from app.rag.parser import (
    ParsedDocument,
    derive_slug,
    is_episode_file,
    parse_transcript_file,
)
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


from dataclasses import dataclass, field


@dataclass
class IngestionStats:
    """Summary metrics of an ingestion run."""

    total_files: int = 0
    created_docs: int = 0
    updated_docs: int = 0
    skipped_docs: int = 0
    pruned_docs: int = 0
    total_chunks: int = 0
    total_tokens: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, self.end_time - self.start_time)


def resolve_data_dir(data_dir_arg: str | None = None) -> Path:
    """Resolve the transcript directory across Docker container and Windows host environments."""
    settings = get_settings()

    if data_dir_arg:
        base = Path(data_dir_arg)
        candidates = [
            base / "lenny-chatprd" / "episodes",
            base / "lenny-chatprd",
            base / "episodes",
            base / "podcasts",
            base,
        ]
        for cand in candidates:
            if cand.is_dir():
                if (cand / "episodes").is_dir() and any((cand / "episodes").rglob("*.md")):
                    return cand / "episodes"
                if (cand / "podcasts").is_dir() and any((cand / "podcasts").glob("*.md")):
                    return cand / "podcasts"
                if any(cand.glob("*.md")):
                    return cand
        raise FileNotFoundError(
            "Transcript data directory not found. Expected 'data/lenny-chatprd/episodes' containing markdown transcripts. "
            "Please run 'python scripts/fetch_data.py' or 'git clone --depth 1 https://github.com/ChatPRD/lennys-podcast-transcripts data/lenny-chatprd' to fetch the ChatPRD corpus."
        )

    configured_dir = Path(settings.data_dir)
    candidates = [
        configured_dir / "lenny-chatprd" / "episodes",
        configured_dir / "lenny-chatprd",
        configured_dir / "episodes",
        configured_dir / "podcasts",
        configured_dir,
    ]
    # If configured data_dir is default /data, also check cwd and cwd.parent for host dev
    if str(settings.data_dir).rstrip("/\\") in ("/data", "data"):
        cwd = Path.cwd()
        candidates.extend(
            [
                cwd / "data" / "lenny-chatprd" / "episodes",
                cwd / "data" / "lenny-chatprd",
                cwd / "data" / "episodes",
                cwd / "data",
                cwd.parent / "data" / "lenny-chatprd" / "episodes",
                cwd.parent / "data" / "lenny-chatprd",
                cwd.parent / "data" / "episodes",
                cwd.parent / "data",
            ]
        )

    for cand in candidates:
        if cand.is_dir():
            if (cand / "episodes").is_dir() and any((cand / "episodes").rglob("*.md")):
                return cand / "episodes"
            if (cand / "podcasts").is_dir() and any((cand / "podcasts").glob("*.md")):
                return cand / "podcasts"
            if any(cand.glob("*.md")):
                return cand

    raise FileNotFoundError(
        "Transcript data directory not found. Expected 'data/lenny-chatprd/episodes' containing markdown transcripts. "
        "Please run 'python scripts/fetch_data.py' or 'git clone --depth 1 https://github.com/ChatPRD/lennys-podcast-transcripts data/lenny-chatprd' to fetch the ChatPRD corpus."
    )


async def _get_embeddings_for_chunks(
    chunk_texts: Sequence[str],
    embedder: Any,
    batch_size: int,
) -> list[list[float]]:
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
        return [client.get_embedding(t, is_query=False) for t in chunk_texts]


async def ingest_document(
    file_path: Path | str,
    db: AsyncSession,
    embedder: Any | None = None,
    batch_size: int = 32,
    force: bool = False,
    dry_run: bool = False,
) -> tuple[str, int, int]:
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

    # 2. Idempotency check: unchanged file with existing chunks
    if existing_doc is not None and not force and existing_doc.content_hash == parsed.content_hash:
        cnt_stmt = select(func.count(Chunk.id)).where(Chunk.document_id == existing_doc.id)
        cnt_res = await db.execute(cnt_stmt)
        existing_chunk_count = cnt_res.scalar() or 0
        if inspect.isawaitable(existing_chunk_count):
            existing_chunk_count = await existing_chunk_count
        if int(existing_chunk_count) > 0:
            return ("skipped", int(existing_chunk_count), 0)

    # 3. Chunk the parsed document
    target_doc_id = existing_doc.id if existing_doc is not None else uuid.uuid4()
    chunks: list[ChunkDraft] = chunk_document(parsed, document_id=target_doc_id)
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
    limit: int | None = None,
    embedder: Any | None = None,
    batch_size: int = 32,
    force: bool = False,
    dry_run: bool = False,
    reset: bool = False,
    on_progress: Callable[[int, int, str, str, int], None] | None = None,
) -> IngestionStats:
    """Ingest all transcript files in source_dir with progress tracking and idempotency."""
    dir_path = Path(source_dir)
    stats = IngestionStats(start_time=time.time())

    if not dir_path.is_dir():
        stats.end_time = time.time()
        stats.errors.append({"file": str(dir_path), "error": "Source directory does not exist"})
        return stats

    # Prefer episodes subfolder if present
    target_dir = dir_path
    if (dir_path / "episodes").is_dir() and any((dir_path / "episodes").rglob("*.md")):
        target_dir = dir_path / "episodes"
    elif (dir_path / "podcasts").is_dir() and any((dir_path / "podcasts").glob("*.md")):
        target_dir = dir_path / "podcasts"

    if any(target_dir.glob("*/*.md")):
        all_md_files = list(target_dir.rglob("*.md"))
    else:
        all_md_files = list(target_dir.glob("*.md"))

    # Filter out non-episode files
    files = [f for f in all_md_files if is_episode_file(f)]
    files.sort(key=lambda p: derive_slug(p))

    if limit is not None and limit > 0:
        files = files[:limit]

    stats.total_files = len(files)

    # If --reset flag is set, delete documents and chunks not present in current source
    if reset and not dry_run:
        source_slugs = {derive_slug(f) for f in files}
        stmt = select(Document.slug)
        res = await db.execute(stmt)
        existing_slugs = set(res.scalars().all())
        stale_slugs = existing_slugs - source_slugs
        if stale_slugs:
            logger.info("Reset flag: deleting %d stale documents not present in current source", len(stale_slugs))
            await db.execute(delete(Document).where(Document.slug.in_(list(stale_slugs))))
            await db.commit()
            stats.pruned_docs = len(stale_slugs)

    for idx, file_path in enumerate(files):
        slug = derive_slug(file_path)
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
