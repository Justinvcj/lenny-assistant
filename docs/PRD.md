# PRD — Lenny Growth Assistant

**Status:** Final · **Date:** 2026-10-12 · **For:** Oogway Labs take-home (FDE)

---

## 1. Forward Deployment Brief

### 1.1 Context (assumed client)
A product & growth team keeps a library of Lenny Rachitsky's podcast transcripts. Team members re-listen to or skim episodes to find advice before decisions and writing. The client wants a chat assistant that answers from those transcripts with traceable sources, and can turn a grounded answer into a polished written piece.

### 1.2 User and problem
**Primary user: product manager / growth lead** who needs a specific, defensible piece of advice (e.g. "how do top teams think about activation before retention?") in minutes, not an hour of re-listening.
- **Pain today:** finding the right episode and the right passage is slow; advice gets paraphrased from memory and loses its source.
- **Job to be done:** "Give me what the guests actually said about X, tell me where, and help me draft something from it."

**Secondary user: team lead/content owner** who wants first drafts of essays grounded in real quotes.

Trust (not coverage) is the product: a smaller set of answers that are provably grounded in the transcripts, with visible source passages, is more useful than a larger set where any single claim may silently drift from the source.

### 1.3 Success metrics
| # | Metric | Target | How measured | Spike baseline |
|---|---|---|---|---|
| M1 | Retrieval hit@6: expected episode appears in top-6 chunks (in-scope eval questions) | ≥ 85% | `scripts/eval.py` | not yet measured |
| M2 | Citation validity: every non-refusal answer has ≥1 `[S#]` that maps to a retrieved chunk, and 0 invented sources | 100% | eval + unit tests | n/a (stub) |
| M3 | Refusal accuracy on out-of-scope questions | ≥ 90% | eval (≥5 OOS questions) | 10/10 with stub tool |
| M4 | Faithfulness: answer claim matches source; essays' support score (sentences supported by cited chunks) | ≥ 70% support score on essays (set at build time; **known miss** — not relaxed, see §9) | validator R_GROUNDED_SUPPORT; manual review for QA | Spike QA: 80% (12/15) — 2 reversed, 1 embellished. **RUN3 live essays: 12.5% (PLG) and 18.5% (pricing)** — well below 70%. Essays pass length/citation/no-fabricated-quote checks but the sentence-level support overlap is weak because the model paraphrases around the `[S#]` anchors. Target intentionally **not** adjusted downward; disclosed as a residual defect. |
| M5 | End-to-end latency on demo hardware (Ollama local, qwen2.5:7b) | QA p50 ≤ 20 s | logs (`total_ms`) | **RUN3 live: refusal p50 0.0 s; grounded QA p50 ≈ 13 s, p95 ≈ 38 s (n = 12 across 6 live sessions); deterministic artifact 0.1 s.** |
| M6 | Essay skill output within length and structure rules | Body words in canonical 1,100–1,400 range | validator R_LENGTH | **RUN3 live: Flow 2 (PLG) 1,119 body words; Flow 3 (pricing) 1,122 body words — both in range after expansion loop.** |
| M7 | Time to a sourced answer vs re-listening | ≥10 min manual baseline → ≤ 1 min with the assistant for cached, previously-grounded questions | assumption, demo evidence | Assumption; not instrumented against users. |
| M8 | Short follow-up handling ("Why is that?", "Can you explain that more?") on a grounded QA turn | ≥ 80% grounded, remainder refused rather than hallucinated | live multi-turn audit | **RUN3 live: grounded in about 4 of 6 live runs; the remaining 2 refused via the verifier's "retries once, then refuses" allowance.** |

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
| A9 | Ship 30 target length: canonical 1,100–1,400 body words (centre 1,250), with `review_floor` 1,000 and `trim_target` 1,350. | Change in `ship30_rules.yaml` metadata. |
| A10 | Agent framework: Claude Agent SDK (chosen after a measured spike; see spike/SPIKE_LOG.md). | — |
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
| Hallucination by small local model | Spike: reversed claim 2/15 | Source-numbered prompts, `[S#]` validation, show source passage in UI, refusal without LLM call on weak retrieval, eval metric M4 | **Material**: RUN3 essays scored 12.5% / 18.5% on sentence support (target 70%). See §9. |
| Essay headings leak templated placeholders ("Angle N on <topic>") | RUN3 live: both Flow 2 and Flow 3 failed R_SPECIFIC_HEADINGS; `derive_heading_from_section` returns empty when a section's first sentence has no `[S#]` tag | Validator flags the leak; no runtime remediation yet | **Material** — disclosed in §9 |
| Short follow-up refusals ("Why is that?") after a grounded answer | RUN3 live: 2 of 6 Q2 turns refused even after the R1 score-gate bypass | Verifier allowed to refuse after one retry; prompt-side investigation open | Medium |
| Tool-skipping by small model | Spike: skipped tool 4/4 on one question | Retrieval always runs in code (D1) | Low |
| Agent runtime overhead/confusion | Spike: 21.7k-token prompt with 26 built-in tools | Allowlist only our tools (D3), per-intent tool menu (D2) | Low |
| Latency on local model | RUN3: QA p50 ≈ 13 s / p95 ≈ 38 s; essays 155-163 s with GPU | Progress UI, small context, retrieval-first | Medium on CPU-only hardware |
| Cost of cloud API | Zero budget | Local default; cloud optional | Anthropic path UNTESTED with a real key |
| Transcript IP leakage | Content is upstream repo's IP | Not committed to repo; `./data/` gitignored; fetched on first-run | Client must confirm licensing for their use |
| XSS from generated HTML | Model output is untrusted | Sandboxed iframe (`sandbox=""`, no scripts, no same-origin) + DOMPurify + CSP | See docs/security.md |
| Prompt injection via transcript text | Retrieved text enters the prompt | Treated as data in delimiters; agent has no side-effecting tools; locked-down runtime | Residual: could skew an answer, not escape the sandbox |
| Ollama/DB down | Likely during demo | Health checks, typed errors, 503 db_unavailable, 502 llm_unavailable, agent-runtime timeout → degraded mode | Verified in RUN3 |

### 1.7 Questions I would ask the client (and the assumption I made instead)
1. How many users and how sensitive is the content? → A2, A7.
2. What does a "good" answer look like — quote, summary, both? → cited summary with source passage.
3. Is silence better than a guess? → yes (A4).
4. What do essays feed into? → human-edited drafts (A5).
5. Where must it run? → client laptops, offline-capable (A3).
6. Which sources are allowed beyond the starter pack? → only starter pack (A1).

---

## 2. Discovery evidence (measured before building)
See SPEC.md §9 and `spike/SPIKE_LOG.md`. Key finding that shaped the design: **a 7B model through an agent framework is reliable only when (a) retrieval is forced in code and (b) the tool list is minimal.** Measured corpus (RUN3 live, verified via `/health`): **302 transcript documents, 21,994 vector chunks** indexed in pgvector; 768-dim `nomic-embed-text` embeddings; HNSW retrieval latency under 25 ms.

Audit trail for every live number in this document: [docs/FIX_LOG.md](FIX_LOG.md) RUN3.

## 3. User flows
- **F1 First question:** user asks → router=QA → retrieve top-k → agent answers with `[S#]` tags → UI shows answer, citation chips, source passages, latency.
- **F2 Follow-up — standalone:** "What about B2B?" / "Can you give an example of that?" → `rewrite_query` enriches with prior Q + ~200 chars of prior answer + cited guest/title → retrieval + normal score gate.
- **F2' Follow-up — short/anaphoric (R1 bypass):** "Why is that?" / "Can you explain that more?" when the last assistant turn was a grounded answer with ≥1 citation → bypass the retrieval score gate, merge the prior answer's cited chunks with fresh retrieval (dedupe, cap at `retrieval_top_k`) → normal agent + verifier (one retry allowed, then refusal).
- **F3 Out-of-scope:** retrieval below threshold → refusal sentence, **no LLM call**, logged as `refusal_below_retrieval_threshold`.
- **F4 Essay:** "Turn that into a Ship 30 essay" → router=ESSAY → skill plans outline, drafts per section, up to 2 expansion passes (unused sources only), repair pass, trim pass → validator → essay stored as artifact → opens in viewer.
- **F5 Artifact:** "Make an HTML one-pager of this" → router=ARTIFACT → **deterministic** Markdown → HTML build from the prior grounded answer (no new LLM call) → viewer renders sandboxed.
- **F6 New session:** new chat = new context; old sessions listed and restorable.
- **F7 Degraded:** Ollama down → `/health` degraded, 502 `llm_unavailable`; DB down → 503 `db_unavailable`; agent-runtime failure → direct-provider fallback flagged `degraded: true`. **Never a silent switch between providers.**

## 4. Functional requirements
- **FR1 Sessions**: create / list / get; persist messages with citations (chunk_id, title, guest, passage).
- **FR2 Chat endpoint**: returns `{content, citations, intent, latency_ms, degraded, warnings, artifact?}`.
- **FR3 Ingestion CLI**: parse → chunk → embed → store, idempotent by content hash; `--reset` flag.
- **FR4 Retrieval**: cosine similarity, top-k, `RETRIEVAL_MIN_SCORE` floor, source-numbered output.
- **FR5 Intent router**: deterministic rule-based QA / ESSAY / ARTIFACT classification.
- **FR6 Ship 30 skill**: `ship30_rules.yaml` + validator (R_LENGTH, R_HEADLINE, R_HOOK, R_STRUCTURE, R_SPECIFIC_HEADINGS, R_SECTION_BUDGET, R_NO_DUPLICATE_PARAGRAPHS, R_CITATION_FORMAT, R_FORMATTING, R_TAKEAWAY, R_CITATION, R_GROUNDED_SUPPORT).
- **FR7 Artifacts**: CRUD (create / read) with type `markdown` or `html`; deterministic summary pipeline; `ARTIFACT_MAX_BYTES` gate.
- **FR8 Provider toggle**: `LLM_PROVIDER` env; `/health` and the UI badge report the active provider/model.
- **FR9 Health probe**: `/health` reports `database.{connected, vector_count, ingested}`, `provider.{name, model, ok, reason}`, `ollama.{reachable, llm_model_present, embedding_model_present}`.
- **FR10 Frontend**: chat, sessions, artifact viewer (sandboxed iframe), model badge, loading / error / empty / degraded states; accessible (keyboard, contrast, live regions).

## 5. Non-functional requirements
Security per docs/security.md; structured JSON logs; no stack traces to clients; one-command start; tests runnable without Ollama; accessible UI (keyboard, contrast, live regions).

## 6. Acceptance criteria
| Criterion | Status | Evidence |
|---|---|---|
| `docker compose up --build` starts db, backend, frontend; `/health` ok with Ollama running | Met | /health returns status=ok, vector_count=21,994 |
| Ingestion loads all available transcripts; re-running creates no duplicates | Met | 302 episodes, 21,994 chunks; content-hash dedupe path exercised in tests |
| In-scope question returns an answer with ≥1 valid citation and visible source passage | Met | Live RUN3 Q1 responses carried 1–5 citations |
| Follow-up question uses session context (standalone/anaphoric) | Met | `rewrite_query` enriches with prior Q + ~200 chars of prior answer + cited guest/title |
| Short follow-ups ("Why is that?", "Can you explain that more?") after a grounded answer | **Partially met**: grounded in about 4 of 6 live runs; the rest are refused (verifier allowed to refuse after one retry) | docs/FIX_LOG.md RUN3 R1; backend/tests/test_grounded_followup.py |
| Out-of-scope question returns the refusal sentence and makes no LLM call | Met | immediate-refusal path logs `top_score=... < threshold`; 0 LLM calls |
| "Ship 30 essay" produces an essay passing length/structure/citation rules | **Partially met**: body in 1,100–1,400 range after expansion loop; 0 raw unverified quotes; citations only `[S#]`. R_SPECIFIC_HEADINGS failed in both live flows (headings leaked full topic string in >1 heading); R_GROUNDED_SUPPORT below 70% target (12.5% PLG, 18.5% pricing) | docs/FIX_LOG.md RUN3 R4 |
| Generated HTML renders in the viewer; `<script>`, inline handlers, external requests blocked | Met | sanitizeArtifact.test.ts (frontend) + viewer sandbox attribute empty |
| Switching `LLM_PROVIDER` changes the active model shown in UI | Partial | ollama path tested; anthropic path implemented and typed-error-handled but **UNTESTED** with a valid key |
| Ollama stopped → friendly error, no crash; DB stopped → 503 error code | Met | docs/FIX_LOG.md A4 proof; typed `db_unavailable` envelope |
| Automated tests pass | Met | backend 510 pass / 0 fail / 0 skip; frontend 235 pass / 0 fail |
| README lets a stranger run it from a fresh clone | Met (this document + README.md) | commands verified via `docker compose config` and script `--help` where available |
| Agent transcripts committed and scrubbed | Met | docs/FIX_LOG.md; `git grep -i -F 'C:\Users'` empty outside the log itself |

## 7. Implementation plan
Discovery evidence lives in `spike/SPIKE_LOG.md`; the ordering heuristic ("never cut PRD, cited RAG, Ship 30 skill, artifact sandbox, README, video; cut UI polish, extra tests, cloud provider testing, streaming first") is documented in `transcripts/process/` (see `START_HERE.md`).

## 8. Open items (deferred, not blocking submission)
- Headings: content-first heading generator for the sections where `derive_heading_from_section` returns empty (see §9).
- Support score: evidence-first drafting prompt or sentence-level verifier gate (see §9).
- Cloud provider: a single sanity run with a real Anthropic key (budget-permitting).
- Trim pass: exercise the >1,400-word path on a real essay to validate paragraph-removal ordering (currently only unit-tested).

## 9. Known limitations and technical debt
- **Essay heading quality**: when a drafted body section's first sentence has no `[S#]` tag, `derive_heading_from_section` returns empty and the plan's placeholder title ("Angle N on <topic>") persists. The validator's `R_SPECIFIC_HEADINGS` flags this but no runtime remediation re-tries derivation. Both RUN3 live essays failed this rule.
- **Essay support score below target**: Flow 2 (PLG + Elena Verna) 12.5% and Flow 3 (pricing) 18.5% versus a 70% target. Sentences carry correct `[S#]` tags, but the sentence-level overlap check (`verify_essay_groundedness`) marks most sentences as paraphrased rather than directly supported.
- **Short follow-ups partially met**: ~2 of 6 live Q2 "Why is that?" turns refuse after passing the score-gate bypass because the model/verifier chooses to refuse rather than ground on the merged sources. Allowed by spec but surfaces as a user-visible refusal.
- **File sizes not split**: `backend/app/routers/chat.py` (~1,200 lines) and `backend/app/agent/verify.py` (~700 lines) grew during the fix passes and were intentionally not refactored to avoid behavioural regressions late in the project. Both are listed as cohesion exceptions in the README.
- **Anthropic provider UNTESTED**: `AnthropicProvider` loads, surfaces typed health errors for missing/invalid keys, and wraps API failures as 502 envelopes, but no run with a real key was performed.
- **Trim path not re-exercised live**: the `trim_essay_sections` path was not triggered during RUN3 (no essay exceeded 1,400 words); covered only by unit tests.
- **Grounded follow-up score-gate bypass is session-local**: the detector relies on the stored prior assistant message's `citations` field; cross-session or stale sessions are not merged.
