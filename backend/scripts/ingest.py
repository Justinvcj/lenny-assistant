"""CLI script for transcript ingestion into pgvector.

Usage:
    python -m scripts.ingest
    python -m scripts.ingest --limit 5
    python -m scripts.ingest --dry-run
    python -m scripts.ingest --force --batch-size 16
    python -m scripts.ingest --reset
"""

import argparse
import asyncio
import logging
from pathlib import Path
import sys

# Ensure backend root is on sys.path for direct module execution
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import get_settings
from app.db import async_session_factory, engine
from app.rag.embeddings import (
    EmbeddingDimensionMismatchError,
    EmbeddingModelNotFoundError,
    OllamaConnectionError,
    check_embedding_dim_async,
    get_embeddings_client,
)
from app.rag.ingest import IngestionStats, ingest_transcripts, resolve_data_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scripts.ingest")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest podcast transcripts into PostgreSQL with pgvector embeddings."
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Path to transcript data directory (defaults to auto-discovered path).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of transcript files to process.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for embedding generation (default: 32).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-chunking and re-embedding even if content_hash matches.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and chunk without database writes or embedding API calls.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete documents and chunks not present in the current source.",
    )
    return parser.parse_args()


def progress_callback(
    current: int, total: int, slug: str, status: str, chunk_count: int
) -> None:
    print(f"[{current:02d}/{total:02d}] {slug:<45} -> {status.upper()} ({chunk_count} chunks)")


async def main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    data_dir = resolve_data_dir(args.data_dir)

    print("=" * 65)
    print("Lenny Growth Assistant — Transcript Ingestion Pipeline")
    print("=" * 65)
    print(f"Target Directory : {data_dir}")
    print(f"Embedding Model  : {settings.embedding_model} (dim={settings.embedding_dim})")
    print(f"Ollama URL       : {settings.ollama_base_url}")
    print(f"Batch Size       : {args.batch_size}")
    print(f"Force Re-index   : {args.force}")
    print(f"Dry Run Mode     : {args.dry_run}")
    print(f"Reset / Prune    : {args.reset}")
    if args.limit:
        print(f"Limit Processing : First {args.limit} documents")
    print("=" * 65)

    if not data_dir.is_dir():
        print(f"ERROR: Data directory does not exist: {data_dir}", file=sys.stderr)
        return 1

    # 1. Startup embedding validation (unless dry-run)
    if not args.dry_run:
        print("Checking embedding model and dimension compatibility...")
        try:
            dim = await check_embedding_dim_async(expected_dim=settings.embedding_dim)
            print(f"Ollama embedding model verified: dimension = {dim}")
        except EmbeddingModelNotFoundError as exc:
            print(f"ERROR: {exc.message}", file=sys.stderr)
            return 1
        except OllamaConnectionError as exc:
            print(f"ERROR: {exc.message}", file=sys.stderr)
            return 1
        except EmbeddingDimensionMismatchError as exc:
            print(f"ERROR: {exc.message}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"ERROR verifying embeddings: {exc}", file=sys.stderr)
            return 1

    print("\nStarting transcript processing...\n")

    try:
        async with async_session_factory() as session:
            stats: IngestionStats = await ingest_transcripts(
                source_dir=data_dir,
                db=session,
                limit=args.limit,
                embedder=get_embeddings_client(),
                batch_size=args.batch_size,
                force=args.force,
                dry_run=args.dry_run,
                reset=args.reset,
                on_progress=progress_callback,
            )

        print("\n" + "=" * 65)
        print("Ingestion Run Summary")
        print("=" * 65)
        print(f"Total Files Scanned    : {stats.total_files}")
        print(f"Documents Created      : {stats.created_docs}")
        print(f"Documents Updated      : {stats.updated_docs}")
        print(f"Documents Skipped      : {stats.skipped_docs}")
        if args.reset:
            print(f"Documents Pruned       : {stats.pruned_docs}")
        print(f"Total Chunks Processed : {stats.total_chunks}")
        print(f"Total Estimated Tokens : {stats.total_tokens:,}")
        print(f"Elapsed Time           : {stats.elapsed_seconds:.2f} s")
        print(f"Errors Encountered     : {len(stats.errors)}")
        if stats.errors:
            print("\nError Details:")
            for err in stats.errors:
                print(f" - {err['file']}: {err['error']}")
        print("=" * 65)

        return 0 if not stats.errors else 1

    finally:
        await engine.dispose()


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    args = parse_args()
    exit_code = asyncio.run(main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

