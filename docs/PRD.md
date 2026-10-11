# PRD — Lenny Growth Assistant

**Author:** ✏️ [Your name] · **Status:** Draft v0.1 · **Date:** 2026-10-10 · **For:** Oogway Labs take-home (FDE)

> ✏️ **Edit rule:** everything marked ✏️ must be rewritten in your own words and defended in interviews. Items marked **[CONFIRM]** must be checked against the original assignment email. Remove this box before submitting.

---

## 1. Forward Deployment Brief

### 1.1 Context (assumed client)
A product & growth team keeps a library of Lenny Rachitsky's podcast transcripts. Team members re-listen to or skim episodes to find advice before decisions and writing. The client wants a chat assistant that answers from those transcripts with traceable sources, and can turn a grounded answer into a polished written piece.

### 1.2 User and problem
**Primary user: product manager / growth lead** who needs a specific, defensible piece of advice (e.g. "how do top teams think about activation before retention?") in minutes, not an hour of re-listening.
- **Pain today:** finding the right episode and the right passage is slow; advice gets paraphrased from memory and loses its source.
- **Job to be done:** "Give me what the guests actually said about X, tell me where, and help me draft something from it."

**Secondary user: team lead/content owner** who wants first drafts of essays grounded in real quotes.

✏️ Add one sentence in your own words on why trust (not coverage) is the product.

### 1.3 Success metrics
| # | Metric | Target | How measured | Spike baseline |
|---|---|---|---|---|
| M1 | Retrieval hit@6: expected episode appears in top-6 chunks (in-scope eval questions) | ≥ 85% | `scripts/eval.py` | not yet measured |
| M2 | Citation validity: every non-refusal answer has ≥1 `[S#]` that maps to a retrieved chunk, and 0 invented sources | 100% | eval + unit tests | n/a (stub) |
| M3 | Refusal accuracy on out-of-scope questions | ≥ 90% | eval (≥5 OOS questions) | 10/10 with stub tool |
| M4 | Faithfulness: answer claim matches the source passage (manual review of sampled answers) | ≥ 85% | manual review of ≥10 answers, recorded in docs/EVAL_RESULTS.md | **80% (12/15)** — 2 reversed, 1 embellished |
| M5 | End-to-end latency for a cited answer on demo hardware | p50 ≤ 20 s, with progress shown | logs (`total_ms`) | 15.2 s with stub tool |
| M6 | Essay skill output within length and structure rules | 100% pass validator | unit tests + eval | not yet built |
| M7 | Time to a sourced answer vs re-listening | ✏️ state your assumed manual baseline (e.g. ≥10 min) vs ≤ 1 min | assumption, validated in demo | assumption |

**Why M4 exists:** a citation proves where the model looked, not that it read it correctly. The spike produced answers that cited the right episode but reversed the claim ("retention is driven by activation" → "activation is driven by retention"). A citation-only metric would have scored those as successes.

### 1.4 Assumptions (explicit, since the brief is incomplete)
| # | Assumption | Consequence if wrong |
|---|---|---|
| A1 | Transcript corpus cloned from ChatPRD/lennys-podcast-transcripts (302 podcast episodes parsed, 21,994 semantic chunks indexed into pgvector). HNSW indexing verified at full 302-episode scale with retrieval latency <25ms. | Performance and memory profile verified on local hardware. |
| A2 | Single team, no authentication, trusted network. Sessions are not private between users. | Multi-tenant needs auth + row-level isolation (out of scope). |
| A3 | Evaluator has Docker and Ollama installed natively, ≥16 GB RAM. NVIDIA GPU optional but slow without. | Container Ollama option documented as fallback. |
| A4 | An honest "I don't know" is better than a plausible wrong answer. | Lower coverage accepted for higher trust. |
| A5 | Essays are drafts for human editing, never auto-published. | Publishing workflow would need review gates. |
| A6 | English-only content and queries. | — |
| A7 | Source repository states transcripts are for personal and educational use. This repository does NOT redistribute or track raw transcript files (`data/` is gitignored); they are fetched dynamically via `scripts/fetch_data.py`. | Avoids IP exposure in the submission and complies with upstream personal/educational use conditions. |
| A8 | ~20 s latency is acceptable for cited answers if progress is visible. | Would need smaller model/streaming. |
| A9 | Ship 30 target length ≈ 1,250 words per the assignment. **[CONFIRM]** | Adjust `ship30_rules.yaml`. |
| A10 | Agent framework: Claude Agent SDK (chosen after a measured spike). **[CONFIRM wording in original email]** | — |
| A11 | Cloud provider path is implemented but UNTESTED (no budget, no API key). | Must be validated before client use. |
| A12 | Local Postgres in Docker rather than Supabase/Railway, for zero cost and reproducible one-command setup. | — |

### 1.5 Scope
**In:** grounded Q&A with citations; follow-up questions within a session; refusal on out-of-scope; session list/new/switch; Ship 30 essay skill; artifact generation + sandboxed viewer; Ollama/Anthropic toggle; Docker Compose; structured logs; graceful failure handling; tests; eval script.
**Out (with reasons):**
- Authentication / multi-tenant — demo scope, adds weeks of production concerns.
- Live transcript refresh / scheduled sync — ingestion is re-runnable and idempotent instead.
- Paid full archive — not available; design allows it.
- Streaming tokens — stretch; progress indicator used instead.
- Fine-tuning / reranker models — time; hybrid search is a documented next step.

### 1.6 Risks and trade-offs
| Risk | Evidence/likelihood | Mitigation | Residual |
|---|---|---|---|
| Hallucination by small local model | Spike: reversed claim 2/15 | Source-numbered prompts, `[S#]` validation, show source passage in UI, refusal without LLM call on weak retrieval, eval metric M4 | Not eliminated; disclosed |
| Tool-skipping by small model | Spike: skipped tool 4/4 on one question | Retrieval always runs in code (D1) | Low |
| Agent runtime overhead/confusion | Spike: 21.7k-token prompt with 26 built-in tools | Allowlist only our tools (D3), per-intent tool menu (D2) | Low |
| Latency on local model | 15 s for a stubbed call; real RAG slower | Progress UI, small context, p50 target 20 s | Medium on weak hardware |
| Cost of cloud API | Zero budget | Local default; cloud optional | — |
| Transcript IP leakage | Content is someone's IP | Not committed to repo; internal-use assumption | Client must confirm licensing |
| XSS from generated HTML | Model output is untrusted | Sandboxed iframe (no scripts, no same-origin) + DOMPurify + CSP | See security.md |
| Prompt injection via transcript text | Retrieved text enters the prompt | Treated as data in delimiters; agent has no side-effecting tools; locked-down runtime | Residual: could skew an answer |
| Ollama/DB down | Likely during demo | Health checks, typed errors, degraded mode | — |

### 1.7 Questions I would ask the client (and the assumption I made instead)
1. How many users and how sensitive is the content? → A2, A7.
2. What does a "good" answer look like — quote, summary, both? → cited summary with source passage.
3. Is silence better than a guess? → yes (A4).
4. What do essays feed into? → human-edited drafts (A5).
5. Where must it run? → client laptops, offline-capable (A3).
6. Which sources are allowed beyond the starter pack? → only starter pack (A1).

---

## 2. Discovery evidence (measured before building)
See SPEC.md §9 and `spike/SPIKE_LOG.md`. Key finding that shaped the design: **a 7B model through an agent framework is reliable only when (a) retrieval is forced in code and (b) the tool list is minimal.**

## 3. User flows
- **F1 First question:** user asks → router=QA → retrieve top-6 → agent answers with `[S#]` tags → UI shows answer, citation chips, source passages, latency.
- **F2 Follow-up:** "What about B2B?" → last N turns included → retrieval query rewritten using history → answer.
- **F3 Out-of-scope:** retrieval below threshold → refusal sentence, no LLM call, suggestion to rephrase.
- **F4 Essay:** "Turn that into a Ship 30 essay" → router=ESSAY → skill retrieves/uses prior grounded sources → drafts section by section → validator → essay stored as artifact → opens in viewer.
- **F5 Artifact:** "Make an HTML one-pager of this" → router=ARTIFACT → artifact saved → viewer renders sandboxed.
- **F6 New session:** new chat = new context; old sessions listed and restorable.
- **F7 Degraded:** Ollama down → clear error banner and health status; DB down → 503 with code; agent runtime failure → direct-provider fallback flagged `degraded`.

## 4. Functional requirements
FR1 Create/list/get sessions; persist messages with citations. FR2 Chat endpoint returns answer, citations (with passages), intent, latency, degraded flag. FR3 Ingestion CLI: parse → chunk → embed → store, idempotent by content hash. FR4 Retrieval with similarity score and threshold. FR5 Intent router (QA / ESSAY / ARTIFACT). FR6 Ship 30 skill with rule file + validator. FR7 Artifact CRUD (create/read) with type markdown|html. FR8 Provider toggle by config; `/config` reports active provider/model. FR9 `/health` reports db, ollama, embedding model, vector count. FR10 Frontend: chat, sessions, artifact panel, model badge, loading/error/empty states.

## 5. Non-functional requirements
Security per docs/security.md; structured JSON logs; no stack traces to clients; one-command start; tests runnable without Ollama; accessible UI (keyboard, contrast, live regions).

## 6. Acceptance criteria
- [ ] `docker compose up --build` starts db, backend, frontend; `GET /health` returns ok with Ollama running.
- [ ] Ingestion loads all available transcripts; re-running creates no duplicates.
- [ ] In-scope question returns an answer with ≥1 valid citation and visible source passage.
- [ ] Follow-up question uses session context.
- [ ] Out-of-scope question returns the refusal sentence and makes no LLM call (verified in logs).
- [ ] "Turn that into a Ship 30 essay" produces an essay passing the validator (length range, hook, headings, takeaway, citations).
- [ ] Generated HTML renders in the viewer; `<script>`, inline handlers, external requests are blocked (tested).
- [ ] Switching `LLM_PROVIDER` changes the active model shown in UI (anthropic path marked UNTESTED).
- [ ] Ollama stopped → friendly error, no crash; DB stopped → 503 error code.
- [ ] Automated tests pass; manual UI test plan executed and recorded.
- [ ] Eval run recorded in docs/EVAL_RESULTS.md with M1–M5.
- [ ] README lets a stranger run it from a fresh clone (tested).
- [ ] Agent transcripts (including failures) committed and scrubbed.
- [ ] 2–3 min camera-on demo uploaded to YouTube.

## 7. Implementation plan
Order and cut line live in `playbook/START_HERE.md`. **Never cut:** PRD, cited RAG, Ship 30 skill, artifact sandbox, README, video. **Cut first:** UI polish, extra tests, cloud provider testing, streaming.

## 8. Open items
- ✏️ Confirm original wording: agent framework, Ship 30 length, video rules, deliverables list, missing "Section 1".
- ✏️ Paste the Ship 30 source link and extract principles into `ship30_rules.yaml`.
- ✏️ Fill N episodes after ingestion; update M-baselines after first eval.
