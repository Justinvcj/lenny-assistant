"""Follow-up query rewriter audit across 5 fresh multi-turn sessions and 1 out-of-domain control session.

Executes the sequence:
  (1) Grounded question
  (2) "Why is that?"
  (3) "Can you explain that more?"
Plus control session:
  (1) "How do I bake chocolate cake?"
  (2) "Why is that?"

Logs and asserts rewritten queries, retrieval scores, and response status.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List

import socket
import urllib.parse

import pytest
from app.agent.prompts import EXACT_REFUSAL_MESSAGE, rewrite_query
from app.config import get_settings
from app.db import async_session_factory
from app.rag.embeddings import get_embeddings_client
from app.rag.retrieval import retrieve

logger = logging.getLogger(__name__)


def _ollama_reachable() -> bool:
    """Return True iff the configured Ollama endpoint accepts a TCP connect.

    These tests exercise the real embedding path end to end. Without Ollama they
    cannot run; they are skipped (never falsely failed) when it is unreachable.
    """
    url = get_settings().ollama_base_url
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 11434
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _ollama_reachable(),
    reason="Ollama is unreachable at the configured OLLAMA_BASE_URL",
)


AUDIT_SESSIONS: List[Dict[str, Any]] = [
    {
        "id": 1,
        "name": "Session 1: Product-Market Fit",
        "turn1": "How do you know when you have product-market fit?",
    },
    {
        "id": 2,
        "name": "Session 2: Early SaaS Retention",
        "turn1": "What drives early retention in SaaS products?",
    },
    {
        "id": 3,
        "name": "Session 3: Giving Away Legos",
        "turn1": "How should founders give away Legos?",
    },
    {
        "id": 4,
        "name": "Session 4: Product-Led vs Sales-Led Growth",
        "turn1": "What is the difference between product-led and sales-led growth?",
    },
    {
        "id": 5,
        "name": "Session 5: Brian Chesky Founder Mode",
        "turn1": "What did Brian Chesky discuss regarding founder mode?",
    },
]


@pytest.mark.asyncio
async def test_audit_five_fresh_sessions_followup_sequence():
    """Audit 5 fresh sessions through (1) Grounded Q, (2) 'Why is that?', (3) 'Can you explain that more?'."""
    settings = get_settings()
    threshold = settings.retrieval_min_score
    embedder = get_embeddings_client()

    audit_logs: List[Dict[str, Any]] = []

    async with async_session_factory() as db:
        for sess in AUDIT_SESSIONS:
            sess_name = sess["name"]
            turn1_q = sess["turn1"]

            # --- TURN 1 ---
            chunks1 = await retrieve(query=turn1_q, db=db, top_k=3, min_score=None, embedder=embedder)
            score1 = chunks1[0].score if chunks1 else 0.0
            status1 = "Grounded" if score1 >= threshold else "Refused"
            top_doc1 = chunks1[0].title if chunks1 else "None"
            top_guest1 = chunks1[0].guest if chunks1 else "None"

            citations1 = [
                {"chunk_id": str(c.chunk_id), "title": c.title, "guest": c.guest}
                for c in chunks1
                if c.score >= threshold
            ]
            asst_text1 = (
                f"According to {top_guest1} in {top_doc1}, the key factor is established by "
                f"clear metrics and structured processes [S1]."
            )
            history = [
                {"role": "user", "content": turn1_q},
                {"role": "assistant", "content": asst_text1, "citations": citations1},
            ]

            # --- TURN 2: 'Why is that?' ---
            turn2_raw = "Why is that?"
            turn2_rewritten = rewrite_query(turn2_raw, history=history)
            chunks2 = await retrieve(query=turn2_rewritten, db=db, top_k=3, min_score=None, embedder=embedder)
            score2 = chunks2[0].score if chunks2 else 0.0
            status2 = "Grounded" if score2 >= threshold else "Refused"
            top_doc2 = chunks2[0].title if chunks2 else "None"
            top_guest2 = chunks2[0].guest if chunks2 else "None"

            citations2 = [
                {"chunk_id": str(c.chunk_id), "title": c.title, "guest": c.guest}
                for c in chunks2
                if c.score >= threshold
            ]
            asst_text2 = (
                f"{top_guest2} elaborates that this happens because underlying feedback loops "
                f"compound quickly [S1]."
            )
            history.extend([
                {"role": "user", "content": turn2_raw},
                {"role": "assistant", "content": asst_text2, "citations": citations2},
            ])

            # --- TURN 3: 'Can you explain that more?' ---
            turn3_raw = "Can you explain that more?"
            turn3_rewritten = rewrite_query(turn3_raw, history=history)
            chunks3 = await retrieve(query=turn3_rewritten, db=db, top_k=3, min_score=None, embedder=embedder)
            score3 = chunks3[0].score if chunks3 else 0.0
            status3 = "Grounded" if score3 >= threshold else "Refused"
            top_doc3 = chunks3[0].title if chunks3 else "None"
            top_guest3 = chunks3[0].guest if chunks3 else "None"

            log_entry = {
                "session": sess_name,
                "turn1_q": turn1_q,
                "score1": round(score1, 4),
                "status1": status1,
                "turn2_rewritten": turn2_rewritten,
                "score2": round(score2, 4),
                "status2": status2,
                "turn3_rewritten": turn3_rewritten,
                "score3": round(score3, 4),
                "status3": status3,
            }
            audit_logs.append(log_entry)

            print(f"\n=== {sess_name} ===")
            print(f"Turn 1 Q: '{turn1_q}' => Score: {score1:.4f} ({status1}) [{top_doc1}]")
            print(f"Turn 2 Rewritten: '{turn2_rewritten}' => Score: {score2:.4f} ({status2}) [{top_doc2}]")
            print(f"Turn 3 Rewritten: '{turn3_rewritten}' => Score: {score3:.4f} ({status3}) [{top_doc3}]")

            # Assertions: All in-domain turns must meet threshold and remain grounded!
            assert score1 >= threshold, f"Turn 1 score {score1:.4f} below threshold {threshold}"
            assert score2 >= threshold, f"Turn 2 score {score2:.4f} below threshold {threshold}"
            assert score3 >= threshold, f"Turn 3 score {score3:.4f} below threshold {threshold}"
            assert status1 == status2 == status3 == "Grounded"

            # Assert Turn 3 retains topic and cited entities
            assert turn1_q in turn3_rewritten or "PMF" in turn3_rewritten or "retention" in turn3_rewritten.lower()


@pytest.mark.asyncio
async def test_audit_out_of_domain_control_session():
    """Verify control session with out-of-domain query refuses Turn 1 and immediate follow-up Turn 2."""
    settings = get_settings()
    threshold = settings.retrieval_min_score
    embedder = get_embeddings_client()

    async with async_session_factory() as db:
        # Turn 1: Cooking query
        turn1_q = "How do I bake chocolate cake?"
        chunks1 = await retrieve(query=turn1_q, db=db, top_k=3, min_score=None, embedder=embedder)
        score1 = chunks1[0].score if chunks1 else 0.0
        assert score1 < threshold, f"Out-of-domain query should score below threshold {threshold}, got {score1:.4f}"

        # Refusal is returned
        history = [
            {"role": "user", "content": turn1_q},
            {"role": "assistant", "content": EXACT_REFUSAL_MESSAGE, "citations": []},
        ]

        # Turn 2: 'Why is that?' after refusal
        turn2_raw = "Why is that?"
        turn2_rewritten = rewrite_query(turn2_raw, history=history)

        # Query rewriter preserves the refused out-of-domain query rather than inflating it
        assert turn2_rewritten == turn1_q

        # Retrieval score on rewritten query remains below threshold
        chunks2 = await retrieve(query=turn2_rewritten, db=db, top_k=3, min_score=None, embedder=embedder)
        score2 = chunks2[0].score if chunks2 else 0.0
        assert score2 < threshold, f"Follow-up after refusal should score below threshold {threshold}, got {score2:.4f}"

        # Turn 3: 'Can you explain that more?' after refusal
        history.extend([
            {"role": "user", "content": turn2_raw},
            {"role": "assistant", "content": EXACT_REFUSAL_MESSAGE, "citations": []},
        ])
        turn3_raw = "Can you explain that more?"
        turn3_rewritten = rewrite_query(turn3_raw, history=history)
        assert turn3_rewritten == turn1_q
        chunks3 = await retrieve(query=turn3_rewritten, db=db, top_k=3, min_score=None, embedder=embedder)
        score3 = chunks3[0].score if chunks3 else 0.0
        assert score3 < threshold, f"Cascading follow-up turn 3 should score below threshold, got {score3:.4f}"

        # Turn 4: 'Tell me more about it' after refusal
        history.extend([
            {"role": "user", "content": turn3_raw},
            {"role": "assistant", "content": EXACT_REFUSAL_MESSAGE, "citations": []},
        ])
        turn4_raw = "Tell me more about it"
        turn4_rewritten = rewrite_query(turn4_raw, history=history)
        assert turn4_rewritten == turn1_q
        chunks4 = await retrieve(query=turn4_rewritten, db=db, top_k=3, min_score=None, embedder=embedder)
        score4 = chunks4[0].score if chunks4 else 0.0
        assert score4 < threshold, f"Cascading follow-up turn 4 should score below threshold, got {score4:.4f}"

        print("\n=== Out-of-Domain Control Session ===")
        print(f"Turn 1 Q: '{turn1_q}' => Score: {score1:.4f} (Refused)")
        print(f"Turn 2 Rewritten: '{turn2_rewritten}' => Score: {score2:.4f} (Refused)")
        print(f"Turn 3 Rewritten: '{turn3_rewritten}' => Score: {score3:.4f} (Refused)")
        print(f"Turn 4 Rewritten: '{turn4_rewritten}' => Score: {score4:.4f} (Refused)")
