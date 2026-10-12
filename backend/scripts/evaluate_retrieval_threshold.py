"""Evaluation script for on-topic vs off-topic retrieval scores on the real ChatPRD corpus."""

import asyncio
import sys
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.db import async_session_factory
from app.rag.retrieval import retrieve

on_topic_queries = [
    "How to identify product-market fit",
    "Giving away your Legos as a company scales",
    "How to optimize user onboarding and activation",
    "Pricing and monetization strategies for SaaS",
    "The origins and practices of founder mode",
    "How Duolingo runs A/B testing and experimentation",
    "Working backwards and writing PR/FAQs at Amazon",
    "Product-led growth vs sales-led growth",
    "How Airbnb redesigned its product management organization",
    "Setting and evaluating OKRs for engineering and product teams",
]

off_topic_queries = [
    "Recipe for authentic Neapolitan pizza dough with sourdough starter",
    "Quantum chromodynamics and gluon field theory in high energy physics",
    "Symptoms and treatment options for feline leukemia virus in domestic cats",
]


async def eval_queries() -> None:
    async with async_session_factory() as session:
        print("=" * 80)
        print("ON-TOPIC RETRIEVAL RESULTS (Top 3 per query)")
        print("=" * 80)
        on_scores = []
        top1_on_scores = []
        for q in on_topic_queries:
            results = await retrieve(q, session, top_k=3, min_score=0.0)
            print(f'\nQUERY: "{q}"')
            for rank, r in enumerate(results, 1):
                score = float(r.score)
                on_scores.append(score)
                if rank == 1:
                    top1_on_scores.append(score)
                snippet = r.text.replace("\n", " ")[:90]
                print(f"  #{rank} [Score: {score:.4f}] Guest: {r.guest} | Doc: {r.document_slug} | Snippet: {snippet}...")

        print("\n" + "=" * 80)
        print("OFF-TOPIC RETRIEVAL RESULTS (Top 3 per query)")
        print("=" * 80)
        off_scores = []
        top1_off_scores = []
        for q in off_topic_queries:
            results = await retrieve(q, session, top_k=3, min_score=0.0)
            print(f'\nQUERY: "{q}"')
            for rank, r in enumerate(results, 1):
                score = float(r.score)
                off_scores.append(score)
                if rank == 1:
                    top1_off_scores.append(score)
                snippet = r.text.replace("\n", " ")[:90]
                print(f"  #{rank} [Score: {score:.4f}] Guest: {r.guest} | Doc: {r.document_slug} | Snippet: {snippet}...")

        print("\n" + "=" * 80)
        print("SCORE DISTRIBUTION & RETRIEVAL_MIN_SCORE JUSTIFICATION")
        print("=" * 80)
        print(f"On-topic  - Min: {min(on_scores):.4f}, Max: {max(on_scores):.4f}, Mean: {sum(on_scores)/len(on_scores):.4f}")
        print(f"Off-topic - Min: {min(off_scores):.4f}, Max: {max(off_scores):.4f}, Mean: {sum(off_scores)/len(off_scores):.4f}")
        print(f"Lowest Top-1 On-Topic Score  : {min(top1_on_scores):.4f}")
        print(f"Highest Top-1 Off-Topic Score: {max(top1_off_scores):.4f}")
        recommended_threshold = round((min(top1_on_scores) + max(top1_off_scores)) / 2, 2)
        print(f"Empirically Justified RETRIEVAL_MIN_SCORE: {recommended_threshold:.2f}")


if __name__ == "__main__":
    asyncio.run(eval_queries())
