import sys
from pathlib import Path

sys.path.insert(0, "backend")
from app.rag.chunking import chunk_document
from app.rag.parser import parse_transcript_file

podcasts_dir = Path("data/lenny-source/podcasts")
non_punct = []
monologue_subturn_count = 0

for f in sorted(podcasts_dir.glob("*.md")):
    doc = parse_transcript_file(f)
    chunks = chunk_document(doc)
    for idx, c in enumerate(chunks):
        tail = c.text.strip()
        last_char = tail[-1]
        if last_char not in [".", "!", "?", '"', "'", "”", "’", "…"]:
            non_punct.append((f.name, idx, last_char, repr(tail[-60:])))

print(f"Total non-punct chunks: {len(non_punct)}")
for name, idx, ch, tail in non_punct[:15]:
    print(f"File: {name} | Chunk: {idx} | Last char: {ch!r} ({ord(ch)}) | End snippet: {tail}")
