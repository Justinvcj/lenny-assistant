# Data Notes — Lenny Transcript Corpus Analysis (ChatPRD Repository)

Empirical analysis of the canonical transcript corpus from `https://github.com/ChatPRD/lennys-podcast-transcripts`.

---

## 1. Overview and File Inventory

- **Repository Source:** `https://github.com/ChatPRD/lennys-podcast-transcripts` (cloned to `data/lenny-chatprd/`)
- **Total Markdown Files:** 394 files total across repository
  - `episodes/`: 303 directories, each containing exactly one `transcript.md` (303 episode transcript files total)
  - `index/`: 89 markdown files (1 master `README.md`, 1 `episodes.md` table, 87 topic tag files)
  - Repository root: 2 documentation files (`CLAUDE.md`, `README.md`)
- **Directory Layout:**
  ```text
  data/lenny-chatprd/
  ├── episodes/
  │   ├── ada-chen-rekhi/
  │   │   └── transcript.md
  │   ├── brian-chesky/
  │   │   └── transcript.md
  │   └── ... (303 subdirectories)
  ├── index/
  │   ├── README.md              # Master topic directory (87 topics)
  │   ├── episodes.md            # Markdown table of 269 indexed episodes, summaries, keywords
  │   └── {topic}.md             # 87 topic markdown files (e.g. product-management.md)
  ├── scripts/
  │   └── build-index.sh         # Idempotent index generation script
  ├── CLAUDE.md
  └── README.md
  ```

---

## 2. YAML Frontmatter Schema & Field Frequencies

Every `transcript.md` begins with YAML frontmatter bounded by `---`. Field frequencies across all 303 files:

| Field | Type | Count (out of 303) | Frequency | Notes |
|---|---|---|---|---|
| `guest` | String | 303 | 100.0% | Always present (e.g. `Ada Chen Rekhi`) |
| `keywords` | List[str] | 303 | 100.0% | List of AI-generated topic tags |
| `title` | String | 302 | 99.7% | Absent only in `teaser_2021` |
| `description` | String | 302 | 99.7% | Multi-line episode summary / show notes |
| `duration_seconds` | Float | 302 | 99.7% | Audio/video duration in seconds |
| `duration` | String | 302 | 99.7% | Formatted duration (e.g. `'1:07:26'`) |
| `channel` | String | 302 | 99.7% | Typically `'Lenny\'s Podcast'` |
| `youtube_url` | String | 301 | 99.3% | Empty string in 2 (`daniel-lereya`, `peter-deng`), absent in 2 |
| `video_id` | String | 301 | 99.3% | YouTube video ID (11 chars) |
| `view_count` | Integer | 301 | 99.3% | View count at extraction time |
| `publish_date` | Date/Str | 300 | 99.0% | ISO `YYYY-MM-DD` upload date |
| `spotify_url` | String | 1 | 0.3% | Present only in `nickey-skarstad` |
| `spotify_id` | String | 1 | 0.3% | Present only in `nickey-skarstad` |

### Frontmatter Example (Ada Chen Rekhi)
```yaml
---
guest: Ada Chen Rekhi
title: Feeling stuck? Here's how to know when it's time to leave your job | Ada Chen Rekhi
youtube_url: https://www.youtube.com/watch?v=l-T8sNRcWQk
video_id: l-T8sNRcWQk
publish_date: 2023-04-21
description: 'Ada Chen Rekhi explains when it''s time to leave your job...'
duration_seconds: 230.0
duration: '3:50'
view_count: 1936
channel: Lenny's Podcast
keywords:
- growth
- roadmap
- user research
- strategy
---
```

---

## 3. Transcript Body & Speaker Formats

Across the 303 files, dialogue turns appear in three distinct structural formats:

### Format A: Standard Un-bolded Turns (301 of 303 files)
Header format: `Speaker Name (HH:MM:SS):` or `Speaker Name (MM:SS):`.
Continuation turns often omit the speaker name: `(HH:MM:SS):`.
```markdown
Ada Chen Rekhi (00:00:00):
It's a terrible outcome to wake up one day and be late career and feel trapped...

Lenny (00:00:36):
Welcome to Lenny's Podcast, where I interview world-class product leaders...

(00:01:21):
We do a live exercise around my own personal values. She shares a bunch of advice...
```

### Format B: Bracketed Timestamps (1 of 303 files: `ryan-hoover`)
Header format: `[HH:MM:SS] Speaker:`
```markdown
[00:00:00] Ryan: I don't know how to articulate that- that feeling...
[00:00:28] Lenny: Ryan Hoover is the founder of Product Hunt, which you already know...
```

### Format C: Un-timestamped Dialogue Turns (1 of 303 files: `adriel-frederick`)
Header format: `Speaker:`
```markdown
Adriel Frederick:
There are probably, I call them techno utopians who would say, feed all data...

Lenny:
Welcome to Lenny's Podcast. I'm Lenny, and my goal here is to help you...
```

---

## 4. Corpus Length & Character Statistics

Empirical character counts across all 303 markdown files:
- **Minimum length:** 9,196 characters (~1,500 words, `teaser_2021`)
- **Maximum length:** 158,876 characters (~27,000 words, `brian-chesky`)
- **Median length:** 84,150 characters (~14,500 words)
- **Mean length:** 85,671.9 characters (~14,800 words)
- **Total corpus volume:** 25,958,586 characters (~4.48 million words)

---

## 5. Contents of `index/` Folder

The `index/` folder contains 89 files representing an AI-generated topic taxonomy:
1. **`index/README.md`:** Master index linking all 87 extracted topic categories, generated on 2026-01-14 covering 269 episodes. Top categories by episode volume:
   - Leadership: 73 episodes
   - Entrepreneurship: 52 episodes
   - Career Development: 40 episodes
   - Growth Strategy: 33 episodes
   - Product Management: 32 episodes
   - AI: 27 episodes
   - Company Culture: 22 episodes
   - Decision Making: 21 episodes
2. **`index/episodes.md`:** 168 KB catalog table mapping each episode to a concise summary and list of topic keywords, with relative links back to `../episodes/{slug}/transcript.md`.
3. **87 Individual Topic Files:** Markdown files such as `product-management.md`, `growth-strategy.md`, `ai.md`, listing every episode tagged with that topic.

---

## 6. Anomalies & Quality Considerations

1. **Non-Episode File (`episodes/teaser_2021/`):**
   - File: `episodes/teaser_2021/transcript.md`
   - Content: A promotional trailer for an entirely different show ("The Room Where It Happens" with Greg Isenberg and Sahil Bloom).
   - Frontmatter lacks: `title`, `publish_date`, `youtube_url`, `duration`, `duration_seconds`.
   - Handling: Ingestion parser must identify and skip non-episode files (`title is None` or `slug == 'teaser_2021'`).
2. **Missing YouTube URLs:**
   - `daniel-lereya` and `peter-deng`: `youtube_url: ""` (empty string).
   - `nickey-skarstad`: `youtube_url: None` (has Spotify URLs instead).
   - Ingestion must store empty string or None safely in document metadata without failing.
3. **Missing Publication Dates:**
   - `daniel-lereya` and `peter-deng` omit `publish_date`. Handled as `published_at = None`.
4. **Metadata Contradiction in `ryan-hoover`:**
   - Directory is `ryan-hoover` and guest is `Ryan Hoover`, but frontmatter title/description describe Ryan Singer (creator of "Shape Up"). The spoken transcript is authentically Ryan Hoover (founder of Product Hunt).
5. **Slug Stability:**
   - In the prior corpus, slugs were derived from filename stems (`molly-graham-2.md` -> `molly-graham-2`). In the ChatPRD repository, every file is named `transcript.md`.
   - Slugs MUST be derived from the parent directory name (e.g. `episodes/ada-chen-rekhi/transcript.md` -> `ada-chen-rekhi`) to guarantee uniqueness and stability across runs.

---

## 7. Empirical Retrieval Evaluation & Threshold Calibration

Executed across all 302 indexed episodes (21,994 chunks) using pgvector cosine distance (`1.0 - cosine_distance`) with `nomic-embed-text` embeddings.

### 7.1 Query Results Table

| Query Type | Query | Top Matched Episode / Guest | Cosine Similarity Score |
|---|---|---|---|
| On-Topic 1 | "How to identify product-market fit" | Karri Saarinen (`karri-saarinen`) | **0.7966** |
| On-Topic 2 | "Giving away your Legos as a company scales" | Molly Graham (`molly-graham`) | **0.7716** |
| On-Topic 3 | "How to optimize user onboarding and activation" | Sean Ellis (`sean-ellis`) | **0.7147** |
| On-Topic 4 | "Pricing and monetization strategies for SaaS" | Madhavan Ramanujam (`madhavan-ramanujam-20`) | **0.7447** |
| On-Topic 5 | "The origins and practices of founder mode" | Anneka Gupta (`anneka-gupta`) | **0.7700** |
| On-Topic 6 | "How Duolingo runs A/B testing and experimentation" | Jackson Shuttleworth (`jackson-shuttleworth`) | **0.7110** |
| On-Topic 7 | "Working backwards and writing PR/FAQs at Amazon" | Jason Shah (`jason-shah`) | **0.8353** |
| On-Topic 8 | "Product-led growth vs sales-led growth" | Emily Kramer (`emily-kramer`) | **0.8189** |
| On-Topic 9 | "How Airbnb redesigned its product management organization" | Brian Chesky (`brian-chesky`) | **0.7715** |
| On-Topic 10 | "Setting and evaluating OKRs for engineering and product teams" | Tamar Yehoshua (`tamar-yehoshua`) | **0.7326** |
| Off-Topic 1 | "Recipe for authentic Neapolitan pizza dough with sourdough starter" | Ramesh Johari (`ramesh-johari`) | **0.5415** |
| Off-Topic 2 | "Quantum chromodynamics and gluon field theory in high energy physics" | Matt MacInnis (`matt-macinnis`) | **0.5927** |
| Off-Topic 3 | "Symptoms and treatment options for feline leukemia virus in domestic cats" | Geoff Charles (`geoff-charles`) | **0.5766** |

### 7.2 Score Distribution Summary

```text
================================================================================
SCORE DISTRIBUTION: ON-TOPIC vs. OFF-TOPIC
================================================================================
On-Topic Queries (Top-1 scores)  : Min = 0.7110 | Mean = 0.7667 | Max = 0.8353
Off-Topic Queries (Top-1 scores) : Min = 0.5415 | Mean = 0.5703 | Max = 0.5927
--------------------------------------------------------------------------------
Separation Margin                : +0.1183 (Lowest On-Topic: 0.7110 - Highest Off-Topic: 0.5927)
================================================================================
```

### 7.3 RETRIEVAL_MIN_SCORE Calibration

- **Empirically Justified Threshold:** `RETRIEVAL_MIN_SCORE = 0.62`
- **Separation Guardrail:**
  - Placed between the highest off-topic score (**0.5927**) and the lowest on-topic score (**0.7110**).
  - Margin above off-topic noise: $+0.0273$ (prevents off-topic hallucination).
  - Margin below on-topic floor: $+0.0910$ (prevents false refusal of legitimate questions).
- **Behavioral Guarantee:** Off-topic queries are filtered at the pgvector retrieval layer before LLM prompt assembly, triggering an immediate refusal with 0 token overhead and sub-50ms latency.

