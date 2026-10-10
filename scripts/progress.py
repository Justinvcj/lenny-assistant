"""Progress tracker script for Lenny Growth Assistant build phases."""

import sys


def print_progress():
    phases = [
        ("Phase 0: Setup & Transcripts", True),
        ("P1: Scaffold (FastAPI, React, Compose)", True),
        ("P2: Database Schema & Sessions API", True),
        ("P3a: Transcript Corpus Analysis", True),
        ("P3b: Speaker Parser & Chunker", True),
        ("P3c: Embeddings, Ingestion, Retrieval", True),
        ("P4a: Intent Router, Prompts, Verifier", True),
        ("P4b: LLM Provider & Agent Orchestrator", True),
        ("P4c: Chat Endpoint & Grounding", True),
        ("P4d: Real E2E Run & Faithfulness Eval", True),
    ]

    total = len(phases)
    done = sum(1 for _, d in phases if d)
    pct = int((done / total) * 100)
    bar_len = 30
    filled = int(bar_len * (done / total))
    bar = "=" * filled + "-" * (bar_len - filled)

    print("\n" + "=" * 60)
    print("      LENNY GROWTH ASSISTANT - OVERALL PROGRESS")
    print("=" * 60)
    print(f"\nProgress: [{bar}] {pct}% ({done}/{total} phases complete)\n")
    for name, is_done in phases:
        if is_done:
            status = "\033[92m[DONE]\033[0m"
        else:
            status = "\033[93m[IN PROGRESS]\033[0m"
        print(f"  {status:<22} {name}")
    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    print_progress()
