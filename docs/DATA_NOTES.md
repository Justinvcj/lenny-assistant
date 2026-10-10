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

## 7. Corpus Chunking Statistics (P3b Empirical Results)

The parser and chunker were executed across all 50 podcast transcripts in `data/lenny-source/podcasts/` without database writes or embedding calls.

### 7.1 Quantitative Corpus Metrics
- **Total Documents Analyzed:** 50
- **Total Valid Speaker Turns:** 12,034
- **Empty Turns Filtered (Sponsor Artifacts):** 55
- **Total Chunks Produced:** 3,888
- **Chunk Token Statistics (words * 1.3 approximation):**
  - **Minimum:** 99 tokens
  - **10th Percentile (p10):** 312.0 tokens
  - **25th Percentile (p25):** 365.0 tokens
  - **Median (p50):** **413.0 tokens** (target: ~350–450)
  - **Mean:** **400.3 tokens**
  - **75th Percentile (p75):** 446.0 tokens
  - **90th Percentile (p90):** 463.0 tokens
  - **95th Percentile (p95):** 474.0 tokens
  - **Maximum:** 554 tokens
- **Chunks per Episode:** Min: 46, Median: 77.0, Mean: 77.8, Max: 127

### 7.2 Token Distribution Bins
| Token Range | Chunk Count | Percentage | Note |
|---|---|---|---|
| < 200 tokens | 19 | 0.5% | Outro tails and short boundary transitions |
| 200 – 349 tokens | 710 | 18.3% | Short topic transitions or multi-turn boundaries |
| **350 – 450 tokens** | **2,341** | **60.2%** | **Primary target window** |
| 451 – 500 tokens | 787 | 20.2% | Extended single turns packed to threshold |
| > 500 tokens | 31 | 0.8% | Monologue sub-turns split at sentence bounds |

### 7.3 Three Representative Sample Chunks

#### Sample Chunk 1 (Episode Introduction & Initial Dialogue)
- **Chunk Index:** 0 | **Token Count:** 426 | **Primary Speaker:** Adam Mosseri
- **Character Offsets:** [335 : 2270]
- **Verbatim Excerpt:**
> **Adam Mosseri** (00:00:00):
> No, I think taste matters a ton. In a world where it's easier to build things, it's more important to make sure that your time is spent figuring out what you should be building in the first place. The people who I think are going to make the most of it are the ones who are clear-eyed about what AI is good at and what it's not good at, and also have an instinct or a nose for what it will be good at and not good at.
> 
> **Lenny Rachitsky** (00:00:23):
> What's something that the Instagram algorithm knows about human behavior that people may not realize?
> 
> **Adam Mosseri** (00:00:30):
> I think people assume that there's a much more detailed semantic understanding of everybody's interests and preferences in the algorithm than there is.

#### Sample Chunk 2 (Mid-Episode Core Discussion)
- **Chunk Index:** 105 | **Token Count:** 432 | **Primary Speaker:** Jason Lemkin
- **Character Offsets:** [117142 : 118975]
- **Verbatim Excerpt:**
> **Lenny Rachitsky** (01:42:22):
> The Terminal List?
> 
> **Jason Lemkin** (01:42:24):
> The Terminal List, yeah. I'm not into the Chris Pratt. I'm not into that goofy superhero movies he does, and I know people like it, but The Terminal List, it's pretty, it's I got it, it's written by this ex Navy SEAL that I think tech people don't read the... Everyone, but outside of tech reads this author, but Amazon did this thing with The Terminal List and I think the reason it gripped me, it's like this post, it's like a lot of tech is right now is we're trying to do the right things, but are we doing the right things? It's just confusing. So this one, I couldn't put down, The Terminal List. That was my favorite show. The other one, the one I liked that I couldn't believe. You want the second one? Even though as product people, Maverick, and I'll tell you why. This movie Maverick, okay, you wouldn't think I'd be a Maverick guy, but the quality of this product, it was so high.
> 
> **Jason Lemkin** (01:43:18):
> And what's interesting, you remember Maverick was supposed to come out before COVID, right? And Tom Cruise said no. He's like, "This is such a good product, we're going to wait years for this thing to come out." I'm like, " I'm not going to like this. I mean, cocktail was pretty good, but I'm not going to..." But as a product, when... I've watched this movie three times from a product perspective and just like software, when something is done that well, no wasted calories, no... You see everything tied together. That's the kind of software we love, right? It just delights us when it works better than we expected. So, those are my two.

#### Sample Chunk 3 (Episode Tail / Outro Dialogue)
- **Chunk Index:** 54 | **Token Count:** 290 | **Primary Speaker:** Lenny Rachitsky
- **Character Offsets:** [80098 : 81340]
- **Verbatim Excerpt:**
> **Lenny Rachitsky** (01:14:14):
> Amazing. I just love how much you're giving away and how useful that's going to be to so many people. So again, we'll link to that in the show notes. Zevi, you're awesome. Thank you so much for being here. Thank you so much for sharing so much. This is going to help, I think, a lot of people and I think it's going to help people get over the hump on. Okay, I see all these people doing cool stuff. Here's how I can actually do this stuff. So thank you so much for being here and for sharing so much.
> 
> **Zevi Arnovitz** (01:14:35):
> Thank you for having me. And if you build something cool with some stuff that I learned here, hit me up, send me. I'd love to see.
> 
> **Lenny Rachitsky** (01:14:43):
> Amazing. Zevi, thank you so much for being here.
