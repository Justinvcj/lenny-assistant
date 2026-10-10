from pathlib import Path
import sys

sys.path.insert(0, "backend")
from app.rag.parser import parse_transcript_file
from app.rag.chunking import chunk_document

podcasts_dir = Path("data/lenny-source/podcasts")

total_chunks = 0
invalid_bounds = 0
header_mismatches = 0
out_of_range = 0
empty_chunks = 0

for f in sorted(podcasts_dir.glob("*.md")):
    raw = f.read_text(encoding="utf-8")
    doc = parse_transcript_file(f)
    chunks = chunk_document(doc)
    total_chunks += len(chunks)
    
    for idx, c in enumerate(chunks):
        if c.start_char < 0 or c.end_char > len(raw):
            out_of_range += 1
        if c.start_char >= c.end_char:
            invalid_bounds += 1
        if not c.text.strip():
            empty_chunks += 1
            
        # Sliced text from raw markdown
        sliced = raw[c.start_char : c.end_char]
        
        # Sliced text should contain the first turn's speaker
        first_turn = c.turns[0]
        if first_turn.speaker not in sliced:
            header_mismatches += 1

print(f"Total chunks checked: {total_chunks}")
print(f"Out of range [0, len(raw)]: {out_of_range}")
print(f"Invalid bounds (start >= end): {invalid_bounds}")
print(f"Empty chunks: {empty_chunks}")
print(f"Header mismatches (speaker missing in slice): {header_mismatches}")
