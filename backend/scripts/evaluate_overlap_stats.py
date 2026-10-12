import sys
from pathlib import Path

sys.path.insert(0, "backend")
from app.rag.chunking import chunk_document
from app.rag.parser import parse_transcript_file

podcasts_dir = Path("data/lenny-source/podcasts")

total_transitions = 0
exact_1_turn_overlaps = 0
zero_overlaps = 0
multi_turn_overlaps = 0
subturn_transitions = 0

for f in sorted(podcasts_dir.glob("*.md")):
    doc = parse_transcript_file(f)
    chunks = chunk_document(doc)
    for idx in range(len(chunks) - 1):
        total_transitions += 1
        c_curr = chunks[idx]
        c_next = chunks[idx + 1]
        
        # Check overlap between c_curr.turns and c_next.turns
        curr_turn_indices = [t.turn_index for t in c_curr.turns]
        next_turn_indices = [t.turn_index for t in c_next.turns]
        
        # Overlapping indices
        intersection = set(curr_turn_indices).intersection(set(next_turn_indices))
        
        if len(intersection) == 0:
            zero_overlaps += 1
        elif len(intersection) == 1:
            exact_1_turn_overlaps += 1
        else:
            multi_turn_overlaps += 1

print(f"Total chunk transitions across 50 podcasts: {total_transitions}")
print(f"Exact 1-turn overlaps: {exact_1_turn_overlaps} ({exact_1_turn_overlaps/total_transitions*100:.1f}%)")
print(f"Zero overlaps (0-turn): {zero_overlaps} ({zero_overlaps/total_transitions*100:.1f}%)")
print(f"Multi-turn overlaps (>1-turn): {multi_turn_overlaps} ({multi_turn_overlaps/total_transitions*100:.1f}%)")
