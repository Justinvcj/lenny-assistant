"""Root wrapper CLI script for transcript ingestion into pgvector.

Usage:
    python scripts/ingest.py
    python scripts/ingest.py --limit 5
    python scripts/ingest.py --dry-run
    python scripts/ingest.py --reset
"""

from pathlib import Path
import sys

# Ensure backend root is on sys.path
repo_root = Path(__file__).resolve().parent.parent
backend_dir = repo_root / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from backend.scripts.ingest import main

if __name__ == "__main__":
    main()
