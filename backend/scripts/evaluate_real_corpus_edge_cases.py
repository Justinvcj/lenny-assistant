import re
import sys
from pathlib import Path

sys.path.insert(0, "backend")
from app.rag.parser import parse_transcript_file

podcasts_dir = Path("data/lenny-source/podcasts")
quote_misses = 0
quote_samples = []

for f in sorted(podcasts_dir.glob("*.md")):
    doc = parse_transcript_file(f)
    for t in doc.turns:
        matches = re.finditer(r'([\.!\?]["\'”’]\s+[A-Z])', t.text)
        for m in matches:
            quote_misses += 1
            if len(quote_samples) < 5:
                start = max(0, m.start() - 30)
                end = min(len(t.text), m.end() + 30)
                quote_samples.append((f.name, repr(t.text[start:end])))

print(f"Total sentence boundaries after quote marks in real corpus: {quote_misses}")
for sample in quote_samples:
    print(f"  Sample: {sample[0]} -> {sample[1]}")
