"""Evaluation script comparing 10 product/growth queries vs 3 off-topic queries."""

import asyncio
import sys
import time
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import get_settings
from app.db import async_session_factory
from app.rag.embeddings import get_embeddings_client
from app.rag.retrieval import RetrievalResult, retrieve

ON_TOPIC_QUERIES = [
    ("Q1", "Tell me about activation in the first week", "Onboarding / Activation"),
    ("Q2", "What does the podcast say about retention and churn?", "Retention & Churn"),
    ("Q3", "How should early stage startups approach pricing and monetization?", "Pricing & Monetization"),
    ("Q4", "What are the best interview questions for hiring product managers?", "PM Hiring"),
    ("Q5", "How do you know when you have product-market fit?", "Product-Market Fit"),
    ("Q6", "How do viral growth loops differ from performance marketing?", "Growth Loops"),
    ("Q7", "What frameworks exist for feature prioritization and roadmap planning?", "Feature Prioritization"),
    ("Q8", "How should founders give away their Legos as the company scales?", "Give Away Your Legos"),
    ("Q9", "What is the role of taste and intuition versus data in product development?", "Taste & Intuition"),
    ("Q10", "What are common onboarding mistakes in B2B SaaS?", "B2B SaaS Onboarding"),
]

OFF_TOPIC_QUERIES = [
    ("O1", "How do I bake sourdough bread with wild yeast?", "Culinary / Baking"),
    ("O2", "Who won the 2026 World Cup football championship?", "Sports"),
    ("O3", "What are the capital gains tax rates for commercial real estate in Texas?", "Tax Law"),
]


async def run_evaluation() -> None:
    settings = get_settings()
    client = get_embeddings_client()

    print("=" * 80)
    print("Lenny Growth Assistant — Retrieval Evaluation Benchmark")
    print(f"Model: {settings.embedding_model} (dim={settings.embedding_dim}) | Ollama URL: {settings.ollama_base_url}")
    print("=" * 80)

    on_topic_results = []
    off_topic_results = []

    async with async_session_factory() as session:
        print("\n--- IN-DOMAIN (PRODUCT & GROWTH) QUERIES ---")
        for qid, query, topic in ON_TOPIC_QUERIES:
            t0 = time.time()
            results: list[RetrievalResult] = await retrieve(
                query=query, db=session, top_k=6, min_score=0.0, embedder=client
            )
            elapsed_ms = (time.time() - t0) * 1000.0

            top_score = results[0].score if results else 0.0
            top_doc = f"{results[0].document_slug} ({results[0].title[:30]}...)" if results else "None"
            top_guest = results[0].guest or "Lenny" if results else "None"

            on_topic_results.append((qid, query, topic, top_score, elapsed_ms, top_guest, results[:3]))
            print(f"[{qid}] Score: {top_score:.4f} | {topic:<25} | Guest: {top_guest:<18} | Time: {elapsed_ms:.1f}ms")

        print("\n--- OUT-OF-DOMAIN (OFF-TOPIC) QUERIES ---")
        for qid, query, topic in OFF_TOPIC_QUERIES:
            t0 = time.time()
            results: list[RetrievalResult] = await retrieve(
                query=query, db=session, top_k=6, min_score=0.0, embedder=client
            )
            elapsed_ms = (time.time() - t0) * 1000.0

            top_score = results[0].score if results else 0.0
            top_doc = f"{results[0].document_slug} ({results[0].title[:30]}...)" if results else "None"
            top_guest = results[0].guest or "Lenny" if results else "None"

            off_topic_results.append((qid, query, topic, top_score, elapsed_ms, top_guest, results[:3]))
            print(f"[{qid}] Score: {top_score:.4f} | {topic:<25} | Guest: {top_guest:<18} | Time: {elapsed_ms:.1f}ms")

    # Statistical summary
    on_scores = [r[3] for r in on_topic_results]
    off_scores = [r[3] for r in off_topic_results]

    min_on = min(on_scores) if on_scores else 0.0
    max_on = max(on_scores) if on_scores else 0.0
    avg_on = sum(on_scores) / len(on_scores) if on_scores else 0.0

    min_off = min(off_scores) if off_scores else 0.0
    max_off = max(off_scores) if off_scores else 0.0
    avg_off = sum(off_scores) / len(off_scores) if off_scores else 0.0

    separation_gap = min_on - max_off
    recommended_min_score = 0.50

    print("\n" + "=" * 80)
    print("EVALUATION STATISTICAL SUMMARY")
    print("=" * 80)
    print(f"On-Topic Queries   : Count={len(on_scores)} | Min={min_on:.4f} | Mean={avg_on:.4f} | Max={max_on:.4f}")
    print(f"Off-Topic Queries  : Count={len(off_scores)} | Min={min_off:.4f} | Mean={avg_off:.4f} | Max={max_off:.4f}")
    print(f"Separation Margin  : {separation_gap:+.4f} (Min On-Topic - Max Off-Topic)")
    print(f"Recommended Threshold (RETRIEVAL_MIN_SCORE) : {recommended_min_score:.2f}")
    print(f"Safety Margin above highest Off-Topic score : {recommended_min_score - max_off:+.4f}")
    print("=" * 80)

    # Print markdown table for docs/DATA_NOTES.md
    print("\n--- MARKDOWN FORMAT FOR DATA_NOTES.md ---\n")
    print("| Query ID | Type | Query | Category | Top Cosine Score | Top Matched Episode & Guest |")
    print("|---|---|---|---|---|---|")
    for qid, query, topic, score, _, guest, top_res in on_topic_results:
        slug = top_res[0].document_slug if top_res else "None"
        print(f"| {qid} | On-Topic | \"{query}\" | {topic} | **{score:.4f}** | {slug} ({guest}) |")
    for qid, query, topic, score, _, guest, top_res in off_topic_results:
        slug = top_res[0].document_slug if top_res else "None"
        print(f"| {qid} | Off-Topic | \"{query}\" | {topic} | **{score:.4f}** | {slug} ({guest}) |")


if __name__ == "__main__":
    asyncio.run(run_evaluation())
