#!/usr/bin/env python3
"""Fetch podcast transcripts from ChatPRD/lennys-podcast-transcripts.

Dynamically queries the remote repository for the default branch before cloning.
Provides clear, actionable error reporting when offline or unreachable.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


DEFAULT_REPO = "https://github.com/ChatPRD/lennys-podcast-transcripts"


def get_default_branch(repo_url: str) -> str:
    """Determine the default branch dynamically using git ls-remote --symref.

    Never assumes 'main' or 'master'.
    Raises RuntimeError if offline or unreachable.
    """
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--symref", repo_url, "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except FileNotFoundError:
        raise RuntimeError("git executable not found in PATH. Please install git.")
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Connection timed out contacting {repo_url}. "
            "Please check your internet connection."
        )
    except Exception as exc:
        raise RuntimeError(f"Network error contacting {repo_url}: {exc}")

    if result.returncode != 0:
        stderr_msg = result.stderr.strip() or "Connection refused or host unreachable"
        raise RuntimeError(
            f"Failed to query remote repository at {repo_url}.\n"
            f"Git error: {stderr_msg}\n"
            "You appear to be offline or the repository is unreachable."
        )

    # Output format typically contains:
    # ref: refs/heads/<branch>\tHEAD
    # <hash>\tHEAD
    match = re.search(r"ref:\s+refs/heads/(\S+)\s+HEAD", result.stdout)
    if not match:
        raise RuntimeError(
            f"Unable to parse default branch from git ls-remote output:\n{result.stdout}"
        )

    return match.group(1)


def fetch_transcripts(
    repo_url: str = DEFAULT_REPO,
    dest_dir: Path = Path("data/lenny-chatprd"),
    force: bool = False,
) -> int:
    """Clone transcript repository into dest_dir if missing."""
    dest_path = dest_dir.resolve()

    # Check if already present and has content
    episodes_dir = dest_path / "episodes"
    if dest_path.exists() and episodes_dir.exists() and not force:
        count = len(list(episodes_dir.glob("*/transcript.md")))
        print(f"Transcripts already present at: {dest_path}")
        print(f"Discovered {count} transcript files. Skipping clone.")
        return 0

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Connecting to {repo_url}...")
    try:
        default_branch = get_default_branch(repo_url)
    except RuntimeError as exc:
        print(f"\n[OFFLINE ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"Detected remote default branch: '{default_branch}'")
    print(f"Cloning into {dest_path}...")

    cmd = [
        "git",
        "clone",
        "--branch",
        default_branch,
        "--depth",
        "1",
        repo_url,
        str(dest_path),
    ]

    try:
        res = subprocess.run(cmd, check=False)
        if res.returncode != 0:
            print(
                f"[ERROR] git clone failed with exit code {res.returncode}",
                file=sys.stderr,
            )
            return res.returncode
    except Exception as exc:
        print(f"[ERROR] Failed to execute git clone: {exc}", file=sys.stderr)
        return 1

    print(f"Successfully fetched transcripts into {dest_path} on branch '{default_branch}'.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download Lenny podcast transcripts from source repository."
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"Remote repository URL (default: {DEFAULT_REPO})",
    )
    parser.add_argument(
        "--dest",
        default="data/lenny-chatprd",
        help="Destination directory under project root (default: data/lenny-chatprd)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-clone even if destination directory exists",
    )
    args = parser.parse_args()

    exit_code = fetch_transcripts(
        repo_url=args.repo,
        dest_dir=Path(args.dest),
        force=args.force,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
