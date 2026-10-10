# Data Notes — Lenny Transcript Corpus Analysis

## 1. Overview and File Inventory
- **Total Transcript Files:** 60 files (50 podcast transcripts in `podcasts/`, 10 newsletter posts in `newsletters/`).
- **File Format & Naming:** Markdown (`.md`) files formatted as `podcasts/<guest-slug>.md` (e.g., `podcasts/molly-graham-2.md`, `podcasts/brian-chesky.md`).
- **Metadata Index:** `index.json` located at the root of the data repository.

## 2. Structure of index.json
The `index.json` file contains top-level keys: `schema_version`, `generated_at`, `podcasts`, and `newsletters`.
Each entry in the `podcasts` array provides:
- `title` (string)
- `filename` (relative path)
- `word_count` (integer)
- `date` (YYYY-MM-DD)
- `description` (summary text)
- `guest` (guest name)
- `post_url` (canonical URL)

### Example Entry 1
```json
{
  "title": "The grief, loneliness, and burnout sweeping through the tech industry right now | Molly Graham",
  "filename": "podcasts/molly-graham-2.md",
  "word_count": 18220,
  "date": "2026-09-27",
  "description": "The grief, loneliness, and burnout sweeping through the tech industry right now, covering team leadership, AI product work, and product design.",
  "guest": "Molly Graham",
  "post_url": "https://www.lennysnewsletter.com/p/the-grief-loneliness-and-burnout"
}
```

### Example Entry 2
```json
{
  "title": "A guide to building a career in product management | Jackie Bavaro",
  "filename": "podcasts/jackie-bavaro.md",
  "word_count": 14930,
  "date": "2026-09-20",
  "description": "Jackie Bavaro shares frameworks for breaking into product management, interviewing, and executive leadership.",
  "guest": "Jackie Bavaro",
  "post_url": "https://www.lennysnewsletter.com/p/jackie-bavaro"
}
```

## 3. Transcript Content and Speaker Format
Each file opens with YAML frontmatter matching the index fields, followed by speaker dialogue.
Turns are formatted consistently as `**Speaker Name** (HH:MM:SS):` followed by the spoken text.

### Sample Snippet (10 lines)
```markdown
**Lenny Rachitsky** (00:00:00):
So, we've been chatting about your famous giveaway, your Legos career advice, this idea of how this advice applies in today's very strange AI world.

**Molly Graham** (00:00:09):
The narrative right now is literally like, okay, we hired this new employee, this new employee is the smartest employee that you have ever met. I want you to pour every single thing that you know into this employee, and then they're going to take your job in six months. Who the [inaudible 00:00:25] wants to do that?

**Lenny Rachitsky** (00:00:26):
Here's the big question, Molly. Are there any Legos you should not give away?

**Molly Graham** (00:00:30):
In AI land, I think we got to caveat this. There are some Legos that shouldn't be given away.
```

## 4. Length and Corpus Statistics
Analysis over all 50 podcast transcripts:
- **Minimum length:** 64,091 characters (~12,000 words)
- **Maximum length:** 140,754 characters (~28,000 words)
- **Average length:** 94,661 characters (~18,000 words)
- **Total characters across corpus:** ~4.73 million characters (~900,000 words)

## 5. Anomalies and Data Quality
- **Frontmatter Presence:** 50/50 (100%) podcast files contain valid frontmatter.
- **Speaker Turns:** 50/50 (100%) files cleanly follow the `**Speaker** (timestamp):` turn regex.
- **Missing or Corrupted Files:** None. No empty files or broken encodings detected.

## 6. Parsing & Chunking Proposal
1. **Parser (`rag/parser.py`):**
   - Extract frontmatter (`title`, `guest`, `date`, `post_url`, `description`).
   - Derive slug from filename (e.g., `molly-graham-2`).
   - Compute deterministic SHA-256 `content_hash` over raw file bytes.
   - Regex split on `(?m)^\*\*([^*]+)\*\*\s*\(([^)]+)\):\s*` to extract ordered speaker turns with `speaker`, `timestamp`, `start_char`, and `end_char`.
2. **Chunker (`rag/chunking.py`):**
   - Speaker-turn aware grouping targeting 350–450 tokens (using words * 1.3 approximation).
   - Never break sentences across chunks.
   - Maintain 1 speaker turn overlap between consecutive chunks.
   - Preserve `start_char`, `end_char`, and primary speaker.
3. **Architecture Impact:** No changes required to `docs/architecture.md` section 5.
