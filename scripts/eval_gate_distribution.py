"""Evaluate top-1 retrieval score distribution for 20 on-topic and 20 off-topic queries."""

import asyncio
from app.db import async_session_factory
from app.rag.embeddings import get_embeddings_client
from app.rag.retrieval import retrieve

ON_TOPIC = [
    "product led growth loops",
    "retention cohort analysis",
    "Sean Ellis 40 percent PMF survey",
    "activation milestone metrics",
    "pricing strategy for B2B SaaS",
    "onboarding dropoff reduction",
    "virality coefficient and referral mechanics",
    "customer discovery interview questions",
    "churn rate benchmarks",
    "Elena Verna growth model",
    "Brian Balfour product market fit engine",
    "Ben Williams product led onboarding",
    "growth accounting equation",
    "net revenue retention benchmarks",
    "freemium vs free trial conversion",
    "north star metric selection",
    "leading indicators of retention",
    "feature adoption funnels",
    "self serve sales motion",
    "aha moment identification",
]

OFF_TOPIC = [
    "how to bake a sourdough bread",
    "quantum entanglement in physics",
    "how to fix a bicycle flat tire",
    "best soil for planting tomatoes",
    "causes of the French Revolution",
    "how to train for a marathon",
    "chocolate chip cookie recipe",
    "troubleshooting a leaky kitchen faucet",
    "black hole event horizon mechanics",
    "rules of Australian football",
    "how to play the guitar minor pentatonic scale",
    "car engine spark plug replacement",
    "origami paper crane instructions",
    "acrylic painting techniques for beginners",
    "winter pruning of apple trees",
    "how to treat bee stings",
    "mountains in the Himalayan range",
    "history of ancient Roman architecture",
    "how to knit a wool scarf",
    "replacing bathroom ceramic tiles",
]

async def eval_distribution():
    embedder = get_embeddings_client()
    async with async_session_factory() as session:
        on_scores = []
        for q in ON_TOPIC:
            res = await retrieve(query=q, db=session, top_k=5, min_score=None, embedder=embedder)
            score = res[0].score if res else 0.0
            on_scores.append(score)

        off_scores = []
        for q in OFF_TOPIC:
            res = await retrieve(query=q, db=session, top_k=5, min_score=None, embedder=embedder)
            score = res[0].score if res else 0.0
            off_scores.append(score)

    on_sorted = sorted(on_scores)
    off_sorted = sorted(off_scores)

    print("=== RETRIEVAL GATE DISTRIBUTION (20 On-Topic vs 20 Off-Topic) ===")
    print(f"On-Topic (N=20):")
    print(f"  Min:    {min(on_scores):.4f}")
    print(f"  Median: {on_sorted[len(on_sorted)//2]:.4f}")
    print(f"  Max:    {max(on_scores):.4f}")
    print(f"  All: {[round(s, 3) for s in on_sorted]}")

    print(f"\nOff-Topic (N=20):")
    print(f"  Min:    {min(off_scores):.4f}")
    print(f"  Median: {off_sorted[len(off_sorted)//2]:.4f}")
    print(f"  Max:    {max(off_scores):.4f}")
    print(f"  All: {[round(s, 3) for s in off_sorted]}")

    threshold = 0.50
    on_above = sum(1 for s in on_scores if s >= threshold)
    off_below = sum(1 for s in off_scores if s < threshold)
    print(f"\nAt threshold = {threshold:.2f}:")
    print(f"  On-topic passed:  {on_above}/20 ({on_above/20:.1%})")
    print(f"  Off-topic rejected: {off_below}/20 ({off_below/20:.1%})")

if __name__ == "__main__":
    asyncio.run(eval_distribution())
