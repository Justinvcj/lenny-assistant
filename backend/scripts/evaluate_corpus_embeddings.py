"""Run empirical retrieval evaluation benchmark over real transcript chunks with live Ollama nomic-embed-text."""

import math
import sys
import time
from pathlib import Path
from typing import List, Tuple

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.rag.chunking import ChunkDraft, chunk_document
from app.rag.embeddings import OllamaEmbeddingsClient
from app.rag.parser import ParsedDocument, parse_transcript_file

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

TARGET_EPISODES = [
    "molly-graham-2.md",
    "adam-mosseri.md",
    "eric-ries-2.md",
    "jason-m-lemkin.md",
    "elena-verna-40.md",
    "marc-andreessen.md",
    "keith-rabois.md",
    "brian-halligan.md",
    "jason-cohen.md",
    "tony-fadell.md",
    "zevi-arnovitz.md",
    "nikhyl-singhal-2.md",
]


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)


def main():
    data_dir = backend_dir.parent / "data" / "lenny-source" / "podcasts"
    if not data_dir.is_dir():
        print(f"Directory not found: {data_dir}", file=sys.stderr)
        sys.exit(1)

    print("=" * 80)
    print("Lenny Growth Assistant — Live Ollama Retrieval Evaluation Benchmark")
    print(f"Data Dir: {data_dir}")
    print("=" * 80)

    # 1. Initialize client
    client = OllamaEmbeddingsClient(base_url="http://localhost:11434")
    dim = client.check_embedding_dim(768)
    print(f"Connected to Ollama. Model: {client.model} | Dimension: {dim}\n")

    # 2. Parse and chunk selected representative episodes
    print("Parsing and chunking episodes...")
    all_chunks: List[Tuple[str, str, str, str, ChunkDraft]] = []  # (slug, title, guest, text, draft)

    for ep_filename in TARGET_EPISODES:
        ep_path = data_dir / ep_filename
        if not ep_path.is_file():
            print(f"Warning: {ep_filename} not found, skipping")
            continue
        parsed: ParsedDocument = parse_transcript_file(ep_path)
        chunks = chunk_document(parsed)
        for c in chunks:
            all_chunks.append((parsed.slug, parsed.title, parsed.guest or "Lenny", c.text, c))
        print(f" - {parsed.slug:<25}: {len(chunks)} chunks")

    print(f"\nTotal corpus chunks to embed: {len(all_chunks)}")

    # 3. Batch embed all chunks with search_document: prefix
    chunk_texts = [c[3] for c in all_chunks]
    print(f"Embedding {len(chunk_texts)} chunks via Ollama in batches of 32...")
    t0 = time.time()
    chunk_embeddings = client.get_embeddings_batch(chunk_texts, is_query=False, batch_size=32)
    embed_duration = time.time() - t0
    print(f"Done embedding chunks in {embed_duration:.2f}s ({len(chunk_texts)/embed_duration:.1f} chunks/sec).\n")

    # 4. Embed queries with search_query: prefix
    print("Embedding evaluation queries...")
    on_topic_results = []
    off_topic_results = []

    print("\n--- IN-DOMAIN (PRODUCT & GROWTH) QUERIES ---")
    for qid, query, category in ON_TOPIC_QUERIES:
        q_vec = client.get_query_embedding(query)
        # Calculate similarity against all chunks
        scores = [cosine_similarity(q_vec, c_vec) for c_vec in chunk_embeddings]
        max_idx = max(range(len(scores)), key=lambda i: scores[i])
        best_score = scores[max_idx]
        best_chunk = all_chunks[max_idx]

        on_topic_results.append((qid, query, category, best_score, best_chunk[0], best_chunk[2], best_chunk[1], best_chunk[3][:200]))
        print(f"[{qid}] Score: {best_score:.4f} | {category:<25} | Best: {best_chunk[0]} ({best_chunk[2]})")

    print("\n--- OUT-OF-DOMAIN (OFF-TOPIC) QUERIES ---")
    for qid, query, category in OFF_TOPIC_QUERIES:
        q_vec = client.get_query_embedding(query)
        scores = [cosine_similarity(q_vec, c_vec) for c_vec in chunk_embeddings]
        max_idx = max(range(len(scores)), key=lambda i: scores[i])
        best_score = scores[max_idx]
        best_chunk = all_chunks[max_idx]

        off_topic_results.append((qid, query, category, best_score, best_chunk[0], best_chunk[2], best_chunk[1], best_chunk[3][:200]))
        print(f"[{qid}] Score: {best_score:.4f} | {category:<25} | Best: {best_chunk[0]} ({best_chunk[2]})")

    # 5. Statistical distribution
    on_scores = [r[3] for r in on_topic_results]
    off_scores = [r[3] for r in off_topic_results]

    min_on = min(on_scores)
    max_on = max(on_scores)
    avg_on = sum(on_scores) / len(on_scores)

    min_off = min(off_scores)
    max_off = max(off_scores)
    avg_off = sum(off_scores) / len(off_scores)

    separation_gap = min_on - max_off
    recommended_threshold = 0.50

    print("\n" + "=" * 80)
    print("EVALUATION STATISTICAL SUMMARY")
    print("=" * 80)
    print(f"On-Topic Queries   : Count={len(on_scores)} | Min={min_on:.4f} | Mean={avg_on:.4f} | Max={max_on:.4f}")
    print(f"Off-Topic Queries  : Count={len(off_scores)} | Min={min_off:.4f} | Mean={avg_off:.4f} | Max={max_off:.4f}")
    print(f"Separation Margin  : {separation_gap:+.4f} (Min On-Topic - Max Off-Topic)")
    print(f"Recommended Threshold (RETRIEVAL_MIN_SCORE) : {recommended_threshold:.2f}")
    print(f"Safety Margin above highest Off-Topic score : {recommended_threshold - max_off:+.4f}")
    print("=" * 80)

    # 6. Generate Markdown table
    print("\n### MARKDOWN TABLE FOR docs/DATA_NOTES.md\n")
    print("| Query ID | Type | Query | Category | Top Cosine Score | Top Matched Episode & Guest |")
    print("|---|---|---|---|---|---|")
    for qid, query, topic, score, slug, guest, title, excerpt in on_topic_results:
        print(f"| {qid} | On-Topic | \"{query}\" | {topic} | **{score:.4f}** | `{slug}` ({guest}) |")
    for qid, query, topic, score, slug, guest, title, excerpt in off_topic_results:
        print(f"| {qid} | Off-Topic | \"{query}\" | {topic} | **{score:.4f}** | `{slug}` ({guest}) |")


if __name__ == "__main__":
    main()
