"""Corpus statistics script for Lenny Growth Assistant (Milestone 1 / P3b).

Parses and chunks all podcast transcripts in data/lenny-source/podcasts/
without database or Ollama dependencies. Computes token metrics, percentiles,
distributions, and prints 3 representative sample chunks.
"""

import argparse
import statistics
import sys
from pathlib import Path
from typing import Any

# Ensure UTF-8 stdout encoding on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

# Ensure backend directory is in sys.path when run directly
current_dir = Path(__file__).resolve().parent
backend_dir = current_dir.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.rag.chunking import ChunkDraft, chunk_document
from app.rag.parser import parse_transcript_file


def compute_percentile(sorted_list: list[int], p: float) -> float:
    """Calculate percentile from a sorted list of numbers."""
    if not sorted_list:
        return 0.0
    k = (len(sorted_list) - 1) * p
    f = int(k)
    c = f + 1
    if c < len(sorted_list):
        return sorted_list[f] + (k - f) * (sorted_list[c] - sorted_list[f])
    return float(sorted_list[f])


def run_corpus_analysis(
    podcasts_dir: Path,
    update_docs_path: Path | None = None,
) -> dict[str, Any]:
    """Parse and chunk all transcripts, returning structured statistics."""
    md_files = sorted(podcasts_dir.glob("*.md"))
    if not md_files:
        raise FileNotFoundError(f"No .md podcast files found in {podcasts_dir}")

    docs = []
    all_chunks: list[ChunkDraft] = []
    chunks_per_doc: list[int] = []
    turns_per_doc: list[int] = []
    all_turns_count = 0
    empty_turns_dropped = 0

    print(f"Parsing and chunking {len(md_files)} podcast transcripts without DB writes...")

    for fpath in md_files:
        doc = parse_transcript_file(fpath)
        chunks = chunk_document(doc)

        docs.append(doc)
        all_turns_count += len(doc.turns)
        empty_turns_dropped += doc.metadata.get("empty_turns_dropped", 0)
        chunks_per_doc.append(len(chunks))
        turns_per_doc.append(len(doc.turns))
        all_chunks.extend(chunks)

    token_counts = [c.token_count for c in all_chunks]
    sorted_tokens = sorted(token_counts)
    n = len(sorted_tokens)

    p10 = compute_percentile(sorted_tokens, 0.10)
    p25 = compute_percentile(sorted_tokens, 0.25)
    p50 = statistics.median(token_counts)
    p75 = compute_percentile(sorted_tokens, 0.75)
    p90 = compute_percentile(sorted_tokens, 0.90)
    p95 = compute_percentile(sorted_tokens, 0.95)

    # Bin distribution
    bin_lt_200 = sum(1 for t in token_counts if t < 200)
    bin_200_349 = sum(1 for t in token_counts if 200 <= t < 350)
    bin_350_450 = sum(1 for t in token_counts if 350 <= t <= 450)
    bin_451_500 = sum(1 for t in token_counts if 450 < t <= 500)
    bin_gt_500 = sum(1 for t in token_counts if t > 500)

    # Select 3 representative sample chunks
    sample_1 = all_chunks[0]  # First episode intro
    sample_2 = all_chunks[len(all_chunks) // 2]  # Mid corpus
    sample_3 = all_chunks[-1]  # Tail

    stats = {
        "doc_count": len(docs),
        "total_turns": all_turns_count,
        "empty_turns_dropped": empty_turns_dropped,
        "total_chunks": len(all_chunks),
        "min_tokens": min(token_counts),
        "p10": p10,
        "p25": p25,
        "median_tokens": p50,
        "mean_tokens": statistics.mean(token_counts),
        "p75": p75,
        "p90": p90,
        "p95": p95,
        "max_tokens": max(token_counts),
        "chunks_per_doc_min": min(chunks_per_doc),
        "chunks_per_doc_median": statistics.median(chunks_per_doc),
        "chunks_per_doc_mean": statistics.mean(chunks_per_doc),
        "chunks_per_doc_max": max(chunks_per_doc),
        "bin_lt_200": bin_lt_200,
        "bin_200_349": bin_200_349,
        "bin_350_450": bin_350_450,
        "bin_451_500": bin_451_500,
        "bin_gt_500": bin_gt_500,
        "sample_1": sample_1,
        "sample_2": sample_2,
        "sample_3": sample_3,
    }

    print("\n" + "=" * 68)
    print(" LENNY PODCAST CORPUS CHUNKING STATISTICS (P3b) ")
    print("=" * 68)
    print(f" Total Documents:         {stats['doc_count']}")
    print(f" Total Valid Turns:       {stats['total_turns']}")
    print(f" Empty Turns Dropped:     {stats['empty_turns_dropped']}")
    print(f" Total Chunks Produced:   {stats['total_chunks']}")
    print("-" * 68)
    print(f" Token Minimum:           {stats['min_tokens']}")
    print(f" Token 10th Percentile:   {stats['p10']:.1f}")
    print(f" Token 25th Percentile:   {stats['p25']:.1f}")
    print(f" Token Median (p50):      {stats['median_tokens']:.1f}")
    print(f" Token Mean:              {stats['mean_tokens']:.1f}")
    print(f" Token 75th Percentile:   {stats['p75']:.1f}")
    print(f" Token 90th Percentile:   {stats['p90']:.1f}")
    print(f" Token 95th Percentile:   {stats['p95']:.1f}")
    print(f" Token Maximum:           {stats['max_tokens']}")
    print("-" * 68)
    print(f" Chunks / Episode (min):  {stats['chunks_per_doc_min']}")
    print(f" Chunks / Episode (med):  {stats['chunks_per_doc_median']:.1f}")
    print(f" Chunks / Episode (mean): {stats['chunks_per_doc_mean']:.1f}")
    print(f" Chunks / Episode (max):  {stats['chunks_per_doc_max']}")
    print("-" * 68)
    print(" Token Distribution Bins:")
    print(f"   < 200 tokens:          {bin_lt_200:>5} ({bin_lt_200 / n * 100:.1f}%)")
    print(f"   200 - 349 tokens:      {bin_200_349:>5} ({bin_200_349 / n * 100:.1f}%)")
    print(f"   350 - 450 tokens:      {bin_350_450:>5} ({bin_350_450 / n * 100:.1f}%)  [TARGET WINDOW]")
    print(f"   451 - 500 tokens:      {bin_451_500:>5} ({bin_451_500 / n * 100:.1f}%)")
    print(f"   > 500 tokens:          {bin_gt_500:>5} ({bin_gt_500 / n * 100:.1f}%)")
    print("=" * 68)

    print("\nSAMPLE CHUNKS:")
    for idx, sample in enumerate([sample_1, sample_2, sample_3], 1):
        print(f"\n--- Sample Chunk {idx} (Index {sample.chunk_index}, Tokens: {sample.token_count}, Speaker: {sample.speaker}) ---")
        print(f"Character Offsets: [{sample.start_char}:{sample.end_char}]")
        snippet = sample.text.replace("\n", " ")
        if len(snippet) > 220:
            snippet = snippet[:220] + "..."
        print(f"Text Preview: {snippet}")

    if update_docs_path:
        update_data_notes_doc(update_docs_path, stats)

    return stats


def update_data_notes_doc(docs_path: Path, stats: dict[str, Any]) -> None:
    """Append or replace Section 7 in docs/DATA_NOTES.md with empirical results."""
    content = docs_path.read_text(encoding="utf-8")

    # Format the 3 sample chunks for Markdown
    s1: ChunkDraft = stats["sample_1"]
    s2: ChunkDraft = stats["sample_2"]
    s3: ChunkDraft = stats["sample_3"]

    s1_preview = "\n> ".join(s1.text.split("\n")[:8])
    s2_preview = "\n> ".join(s2.text.split("\n")[:8])
    s3_preview = "\n> ".join(s3.text.split("\n")[:8])

    total_chunks = stats["total_chunks"]

    section_7 = f"""## 7. Corpus Chunking Statistics (P3b Empirical Results)

The parser and chunker were executed across all 50 podcast transcripts in `data/lenny-source/podcasts/` without database writes or embedding calls.

### 7.1 Quantitative Corpus Metrics
- **Total Documents Analyzed:** {stats['doc_count']}
- **Total Valid Speaker Turns:** {stats['total_turns']:,}
- **Empty Turns Filtered (Sponsor Artifacts):** {stats['empty_turns_dropped']}
- **Total Chunks Produced:** {stats['total_chunks']:,}
- **Chunk Token Statistics (words * 1.3 approximation):**
  - **Minimum:** {stats['min_tokens']} tokens
  - **10th Percentile (p10):** {stats['p10']:.1f} tokens
  - **25th Percentile (p25):** {stats['p25']:.1f} tokens
  - **Median (p50):** **{stats['median_tokens']:.1f} tokens** (target: ~350–450)
  - **Mean:** **{stats['mean_tokens']:.1f} tokens**
  - **75th Percentile (p75):** {stats['p75']:.1f} tokens
  - **90th Percentile (p90):** {stats['p90']:.1f} tokens
  - **95th Percentile (p95):** {stats['p95']:.1f} tokens
  - **Maximum:** {stats['max_tokens']} tokens
- **Chunks per Episode:** Min: {stats['chunks_per_doc_min']}, Median: {stats['chunks_per_doc_median']:.1f}, Mean: {stats['chunks_per_doc_mean']:.1f}, Max: {stats['chunks_per_doc_max']}

### 7.2 Token Distribution Bins
| Token Range | Chunk Count | Percentage | Note |
|---|---|---|---|
| < 200 tokens | {stats['bin_lt_200']:,} | {stats['bin_lt_200'] / total_chunks * 100:.1f}% | Outro tails and short boundary transitions |
| 200 – 349 tokens | {stats['bin_200_349']:,} | {stats['bin_200_349'] / total_chunks * 100:.1f}% | Short topic transitions or multi-turn boundaries |
| **350 – 450 tokens** | **{stats['bin_350_450']:,}** | **{stats['bin_350_450'] / total_chunks * 100:.1f}%** | **Primary target window** |
| 451 – 500 tokens | {stats['bin_451_500']:,} | {stats['bin_451_500'] / total_chunks * 100:.1f}% | Extended single turns packed to threshold |
| > 500 tokens | {stats['bin_gt_500']:,} | {stats['bin_gt_500'] / total_chunks * 100:.1f}% | Monologue sub-turns split at sentence bounds |

### 7.3 Three Representative Sample Chunks

#### Sample Chunk 1 (Episode Introduction & Initial Dialogue)
- **Chunk Index:** {s1.chunk_index} | **Token Count:** {s1.token_count} | **Primary Speaker:** {s1.speaker}
- **Character Offsets:** [{s1.start_char} : {s1.end_char}]
- **Verbatim Excerpt:**
> {s1_preview}

#### Sample Chunk 2 (Mid-Episode Core Discussion)
- **Chunk Index:** {s2.chunk_index} | **Token Count:** {s2.token_count} | **Primary Speaker:** {s2.speaker}
- **Character Offsets:** [{s2.start_char} : {s2.end_char}]
- **Verbatim Excerpt:**
> {s2_preview}

#### Sample Chunk 3 (Episode Tail / Outro Dialogue)
- **Chunk Index:** {s3.chunk_index} | **Token Count:** {s3.token_count} | **Primary Speaker:** {s3.speaker}
- **Character Offsets:** [{s3.start_char} : {s3.end_char}]
- **Verbatim Excerpt:**
> {s3_preview}
"""

    if "## 7. Corpus Chunking Statistics" in content:
        # Replace existing section 7
        prefix = content.split("## 7. Corpus Chunking Statistics")[0].rstrip()
        new_content = prefix + "\n\n" + section_7
    else:
        new_content = content.rstrip() + "\n\n" + section_7

    docs_path.write_text(new_content, encoding="utf-8")
    print(f"\nUpdated {docs_path} with Section 7 (Corpus Chunking Statistics).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute corpus chunking statistics across transcripts.")
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data/lenny-source/podcasts",
        help="Path to podcasts directory containing .md transcripts",
    )
    parser.add_argument(
        "--update-docs",
        type=str,
        default="docs/DATA_NOTES.md",
        help="Path to DATA_NOTES.md to update with Section 7",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent.parent
    podcasts_dir = (project_root / args.data_dir).resolve()
    if not podcasts_dir.exists():
        podcasts_dir = Path(args.data_dir).resolve()

    docs_path = None
    if args.update_docs:
        docs_path = (project_root / args.update_docs).resolve()
        if not docs_path.exists():
            docs_path = Path(args.update_docs).resolve()

    run_corpus_analysis(podcasts_dir=podcasts_dir, update_docs_path=docs_path)


if __name__ == "__main__":
    main()
