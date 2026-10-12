# VERIFICATION_RUN2 — Completing the gaps from AUDIT_FINAL

Auditor: Opus 4.7, read-only pass against `main` @ `739ec90`.
Date: 2026-10-11. Host: Windows 11, Docker Desktop, native Ollama. Rules: READ-ONLY repo (only this file written); no destructive git/docker on main; `-p audit` for the fresh clone, torn down with `-v` afterwards.

## 0. One-glance summary table

| Check | PASS/FAIL | Evidence (one line) |
|---|---|---|
| Main stack healthy before/after | PASS | `curl /health` returns `ok, vector_count=21994` both before and after fresh-clone phase |
| Clean `git status` at end | PASS | only untracked files are `docs/AUDIT_FINAL.md` + this file |
| **A. Fresh clone from GitHub** | **PASS with 4 README gaps** | clone 2 s / fetch 12 s / build 85 s / up 12 s / ingest-10 20 s / first cited answer 36 s |
| S3 pronoun follow-ups (grounded) | PASS | "Why is that?" / "What about for B2B?" / "Can you give an example of that?" all returned 1–4 cits via SDK |
| S3 "Why is that?" after refused cooking | PASS | 199 ms, 0 LLM, exact refusal sentence |
| S4 reference → essay topic separation | PASS | S4 essay cites Sean Ellis/Hila Qu/Rahul Vohra/Ben Williams; Elena Verna (A's unique guest) absent |
| S4 essay time < 120 s | **FAIL** | 224.3 s (hypothesis #4's "~250 s" essentially unchanged) |
| S5 explicit-topic essay cites Elena Verna | PASS | 5 of 5 citations are Elena Verna's episodes |
| S5 essay explains loop mechanics | PARTIAL | "loop" appears 9×, but 0 mentions of self-serve/viral/freemium |
| S5 essay time | PASS | 74.9 s (under 120 s) |
| S6 empty-session essay prompts for topic, no LLM | PASS | 5 ms, "What topic would you like me to write an essay about?…" |
| Essay — duplicate paragraphs = 0 | PASS (both) | S4 and S5 artifact bodies: 0 duplicates |
| Essay — H1 present | PASS (both) | 1 H1 in each |
| Essay — template-heading bleed | **FAIL** | **S4 and S5 share IDENTICAL 5 body H2 headings** — hardcoded at `backend/app/skills/ship30.py:287`. Hypothesis #4 "template headings" **NOT fixed.** |
| Essay — only `[S#]` citations | S4 PASS / S5 FAIL per validator | S4: `[S#]=22, (S#)=0`; S5 validator reports `R_CITATION_FORMAT FAIL — Detected non-standard … like [S1] or ([S4]...)` |
| Essay — misattributed quote | **FAIL** | S4 essay quotes `"activation is just so critical"` attributed to Sean Ellis — SQL `ILIKE` search finds **ZERO** chunks containing that string → **fabricated quote**. Also `"When do we think they've had a good enough experience…"` presented as Ellis's verbatim; the only matching chunk is Ellis saying `"like when do I think they've had a good enough experience…"` — a paraphrase, not verbatim |
| Essay — old-topic bleed (S4) | PASS | activation sources only; no PLG-loop-only sources leaked in |
| Essay — model-written chat text | PASS | chat `content` is deterministic: `"Your Ship 30 essay is ready: … (N words). **Status: Needs review**"` + per-rule PASS/FAIL list. No `"Certainly!"`, no `"Hook:"/"Body:"` labels |
| Essay — profane heading | PASS | none observed |
| Exactly ONE essay generation per request | PASS | `tool_trace` shows a single `ship30_generate_essay` entry per essay request; no duplicate run |
| **C. Ollama unreachable** | PASS | `OllamaProvider` health returns `ok=False, error='All connection attempts failed'`; chat raises `ConnectError` cleanly |
| C. DB stopped → /health | PASS | `status=degraded, database.connected=false` while db is down |
| C. DB stopped → request | PARTIAL | 500 `internal_server_error` with no stack trace — but should be 503 `db_unavailable` per `docs/architecture.md §10` |
| C. DB recovery after restart | PASS | health flips back to `ok, vector_count=21994` in ~6 s |
| C. Invalid/missing cloud key (anthropic path) | **FAIL** | `AnthropicProvider(…)` raises `RuntimeError: The 'anthropic' package is not installed. Install it with: pip install anthropic` — the package is **missing from requirements.txt** → `LLM_PROVIDER=anthropic` hard-fails on startup, not a graceful "missing key" error |
| C. Forced timeout flag + log | PASS (code path) | `_run_degraded(reason='test', exc_type='TestError')` returns `degraded=True, runtime='degraded', tool_trace=[{degraded, degraded_reason, degraded_exc_type}]` and logs ERROR line |
| C. Empty retrieval refusal | PASS | 6 off-topic questions → exact refusal, 0 LLM calls (175–249 ms) |
| C. Unknown session id | PASS | 404 `session_not_found`, no stack trace |
| C. Malformed JSON | PASS | 422 `validation_error` body |
| C. Oversized message | PASS | 422 `validation_error: body.content: String should have at most 4000 characters` |
| C. Embedding-dim mismatch (audit copy) | UNVERIFIED | not re-run; the audit copy was torn down after proving fresh clone |
| C. Empty knowledge base | PASS (observed in A) | audit-stack `/health` reported `ingested: false, vector_count: 0` before ingestion |

---

## 1. Phase A — Fresh clone from GitHub

Executed from `C:\Users\Justin\AppData\Local\Temp\lenny-fresh` with compose project name `-p audit` on ports `8010`/`3010`.

### Timings (seconds)

| Step | Seconds |
|---|---|
| `git clone --depth 1` | 2 |
| `python scripts/fetch_data.py` (transcript repo, shallow clone) | 12 |
| `docker compose -p audit --env-file .env build` | 85 |
| `docker compose -p audit --env-file .env up -d` | 12 |
| `docker compose -p audit --env-file .env exec -T backend python -m scripts.ingest --limit 10` | 20 (10 docs / 739 chunks) |
| First cited answer (`POST /sessions/{id}/messages` on `"What does the podcast say about product-market fit?"`) | 36 (`degraded=false`, 3 cits, `Adam Grenier`-led) |

**Note**: a full ingest of all 394 markdown files was NOT run; the README's "limited-run option" (`--limit 10`) was used to prove the pipeline end-to-end within budget. The README documents a full-ingest time of ~645 s (10 min 45 s).

### README gaps (CONFIRMED)

| # | Gap | Impact |
|---|---|---|
| G1 | **`.env.example` sets `VITE_API_BASE_URL=http://localhost:8000` as a literal, not derived from `BACKEND_PORT`.** When the evaluator overrides `BACKEND_PORT=8010`, the frontend keeps calling `:8000` and all UI requests 404. The README's "Host Port Configuration" section advertises port-override but neglects to warn about this. | Will silently break the frontend on port conflicts. |
| G2 | **`OLLAMA_CONTEXT_LENGTH` guidance is inconsistent**: §3 says `export OLLAMA_CONTEXT_LENGTH=8192`; §5 step 2 says `setx OLLAMA_CONTEXT_LENGTH 16384`. Also neither value is enforced by the stack: `/health` doesn't check it. | Confusion; probably harmless since Ollama runs server-side. |
| G3 | **README §2 benchmarks claim "303 episode directories"** — the ChatPRD transcript repo cloned contains 394 `.md` files across `episodes/<slug>/transcript.md` plus some `README.md`/`CLAUDE.md`/`LICENSE.md`. Parser excludes those correctly (`parser.py:127`), but the "303" is stale. Also, my main stack's ingested count is 302 documents / 21,994 chunks — matches the brief. | Minor doc inconsistency. |
| G4 | **No mention of Windows `MSYS_NO_PATHCONV=1` or Git Bash path-translation gotchas** when running `docker compose exec` with `/tmp/...` paths. Evaluators on Git Bash will hit `No such file or directory` for `/tmp/...`. | Common Windows friction. |

### Teardown proof

`docker compose -p audit down -v` removed the audit project (container, volume, network). The fresh clone was deleted. `docker compose start` on main brought `db + backend + frontend` up healthy. `git status` is clean apart from untracked `docs/AUDIT_FINAL.md` + this file.

---

## 2. Phase B — Scenarios on the main stack

Live API against `localhost:8000`. Each row is one HTTP POST; `runtime` = `sdk` when `degraded=false`.

### S3 — pronoun follow-ups

| Q | Status | Elapsed | Intent | Degraded | SDK init tool list | Tools called | Cits | Guests |
|---|---|---|---|---|---|---|---|---|
| "What do guests say about product-led growth?" | 200 | 44.8 s | QA | false | `[search_transcripts]` | `[search_transcripts]` | 3 | Elena Verna, Elena Verna, Hila Qu |
| "Why is that?" | 200 | 16.7 s | QA | false | `[search_transcripts]` | `[]` | 3 | Julian Shapiro, Hila Qu, Elena Verna |
| "What about for B2B?" | 200 | 52.4 s | QA | false | `[search_transcripts]` | `[search_transcripts]` | 4 | Gina Gotthilf, Ethan Smith, Casey Winters, Various |
| "Can you give an example of that?" | 200 | 43.9 s | QA | false | `[search_transcripts]` | `[search_transcripts]` | 1 | Lauryn Isford |
| (new session) "How do I bake sourdough bread?" | 200 | 0.3 s | QA | false | `[]` | `[]` | 0 | — (exact refusal, zero LLM) |
| "Why is that?" (same session) | 200 | 0.2 s | QA | false | `[]` | `[]` | 0 | — (stays refused) |

**S3 verdict**: pronoun follow-ups resolve correctly in a grounded conversation, and do NOT inherit grounding from a refused turn. The P3-1 finding in AUDIT_FINAL ("Why is that?" refused after activation) does not reproduce here — appears to have been session-specific; the newer rewrite_query handles it.

### S4 — reference-to-essay

| Q | Status | Elapsed | Intent | Cits | Guests |
|---|---|---|---|---|---|
| "What do guests say about product-led growth loops?" | 200 | 15.4 s | QA | 3 | Hila Qu, Elena Verna, Elena Verna |
| "How should a startup think about activation?" | 200 | 21.2 s | QA | 3 | Sean Ellis, Sean Ellis, Hila Qu |
| "Turn that into a Ship 30 essay" | 200 | **224.3 s** | ESSAY | 5 | Sean Ellis, Sean Ellis, Hila Qu, Rahul Vohra, Ben Williams |

**Essay-S4 metrics** (artifact `bb56eb80-add5-451f-aa7e-99d587d7023a`):

| Metric | Value |
|---|---|
| Bytes | 10,233 |
| H1 count | 1 (PASS) |
| Total headings | 7 (1 H1 + 6 H2) |
| Words (excluding headings) | 1,577 (chat says 1,531 body words; both > 1,250 target) |
| Duplicate paragraphs | 0 (PASS) |
| Citation formats | `[S#]=22`, `(S#)=0`, bare `S#=0` (PASS by format; see fabricated quote below) |
| Unresolved tag ids (`[S99]` etc.) | 0 (PASS) |
| `Certainly!` / `Hook:` / `Body:` / `Takeaway:` labels in body | 0 (PASS) |
| Section budgets violated (validator) | 3 of 5 (`R_SECTION_BUDGET: FAIL`) |
| Grounded support score (validator) | 65 % (passes the 35 % threshold but 7 of 20 sentences unsupported) |
| Quotes verified verbatim (validator) | 4 of 6 |
| Topic bleed from A ("PLG loops") into B ("activation") | **none** — A's unique sources (Elena Verna) are absent from the essay's cited set |
| Fabricated quote found by SQL verification | **"activation is just so critical" → NOT FOUND in any chunk** (attributed to Sean Ellis in the essay) |
| Paraphrased quote presented as verbatim | **"When do we think they've had a good enough experience to really know it?"** — Sean Ellis actually says `"like when do I think they've had a good enough experience with the product to really know it?"` (I/we swap + truncation) |
| Essay time | **224 s — exceeds 120 s** |

**S4 chat message (user-visible text, truncated)**:

> Your Ship 30 essay is ready: '# For Product Leaders and Founders: How to Identify and Prioritize High-Leverage Activation Opportunities Through Experiments' (1531 words). **Status: Needs review**
> <details open>
>  <summary>Checks: Needs review (3 flagged)</summary>
>  - **Target Word Count (R_LENGTH):** FAIL — Essay has 1531 body words …
>  - **R_HEADLINE:** PASS; **R_HOOK:** PASS; **R_STRUCTURE:** PASS …
>  - **R_SECTION_BUDGET:** FAIL — 3 sections out of budget
>  - **R_GROUNDED_SUPPORT:** FAIL — Support 65 % … Quotes verified 4/6
> …

Code-written template; no model persona leakage; failed rules named honestly. **PASS** on the user-facing chat-text historical defect, **FAIL** on fabricated/paraphrased quote attribution.

### S5 — explicit-topic essay

Q: "Write a Ship 30 essay about product-led growth loops featuring Elena Verna's ideas"

| Metric | Value |
|---|---|
| Elapsed | 74.9 s (PASS) |
| Intent | ESSAY |
| Citations | 5 of 5 — **all Elena Verna** (`elena-verna`, `elena-verna-20`, `elena-verna-30` episodes) |
| Bytes | 5,260 |
| H1 | 1 (PASS) |
| Headings | 7 (1 H1 + 6 H2) |
| Elena Verna mentions in body | 4 |
| Loop mentions | 9 |
| `self-serve` / `viral` / `freemium` mentions | 0 / 0 / 0 (incomplete mechanics) |
| Body words | 744 (chat says 744; **FAILS the 1,250 target**) |
| Section budgets violated | 5 of 5 (every section too short) |
| `R_CITATION_FORMAT` | **FAIL** — validator reports "Detected non-standard citation formats like [S1] or ([S4]...)" (likely a `([S4]…)` wrapper somewhere in the body) |
| Headings | **IDENTICAL to S4's**: `Defining the Core Value Moment Early` / `Measuring Leading Indicators vs. Vanity Metrics` / `Compounding Feedback Loops and Team Workflows` / `Friction Reduction and Operational Pitfalls` / `Tactical Execution: From Pilot to Scaling` / `Actionable Takeaways` → **template bleed**, source at `backend/app/skills/ship30.py:287` where these 5 strings are hardcoded. Hypothesis #4 "template headings" is **NOT FIXED**. |

### S6 — empty session + "Turn that into a Ship 30 essay"

| Metric | Value |
|---|---|
| Elapsed | 5 ms |
| Intent | ESSAY (classified correctly) |
| SDK init tool list | `[]` (no LLM call) |
| Content | `"What topic would you like me to write an essay about? Please provide a topic or ask a question first so I can ground the response in relevant podcast transcripts."` |
| Refusal sentence used? | No (correct) |

**S6 PASS** — zero LLM, no refusal-sentence leak, topic prompt returned.

---

## 3. Phase C — Resilience

| Scenario | Expected | Observed |
|---|---|---|
| Ollama unreachable (`OllamaProvider(base_url=":1", …)`) | typed error, graceful | `ProviderHealth(ok=False, error='All connection attempts failed')`; `chat()` raises `httpx.ConnectError`. Chat route catches this and would surface 502 `llm_unavailable` per `routers/chat.py`. **PASS** |
| DB stopped (`docker compose stop db`) → `/health` | degraded, no stack trace | `status=degraded, database.connected=false` — **PASS** |
| DB stopped → session create | 503 db_unavailable per architecture.md | **500 `internal_server_error`** with correct envelope and no stack trace. **PARTIAL** — status code wrong (should be 503). |
| DB restart → recovery | health flips back to ok | `vector_count=21994, status=ok` within ~6 s after `docker compose start db`. **PASS** |
| Invalid/missing cloud key via `LLM_PROVIDER=anthropic` | typed startup/health error | `AnthropicProvider.__init__` raises `RuntimeError: The 'anthropic' package is not installed`. **FAIL** — package missing from `backend/requirements.txt`; brief requires a cloud provider "integrated". Setting the var in production would prevent startup. |
| Forced-timeout code path (`_run_degraded(reason='test', exc_type='TestError')`) | degraded flagged, ERROR log | `degraded=True, runtime='degraded', tool_trace[0]={degraded, degraded_reason, degraded_exc_type}` and `ERROR orchestrator: degraded fallback engaged exc_type=TestError reason=test`. **PASS** on the code path. **UNVERIFIED** on a live timeout: a true round-trip timeout would require editing `.env` + restarting the backend. |
| Empty retrieval → refusal | zero LLM, exact refusal | S2 (6 refusals in earlier audit): off-topic in 175–249 ms. **PASS** |
| Unknown session id | 404 session_not_found | **PASS** |
| Malformed JSON | 422 validation_error | **PASS** |
| Oversized message (5,000 chars) | 422 content length | **PASS** — `body.content: String should have at most 4000 characters` |
| Embedding-dim mismatch | fails fast at startup | **UNVERIFIED** — not re-run on the audit copy (torn down before this test was reached) |
| Empty knowledge base | /health ingested=false, refusals | **PASS (indirect)** — the audit stack's `/health` reported `ingested=false, vector_count=0` before ingestion |

### Stack-trace leak check

`POST /sessions/<unknown-uuid>/messages` body: `{"error":{"code":"session_not_found","message":"…"}}` — nothing resembling `Traceback (most recent call last)` or `File "…", line …` observed in any response body across all 30+ error scenarios run.

---

## 4. Latency summary (p50 / p95, seconds)

Measured across this run (small samples; indicative only).

| Request type | n | p50 | p95 |
|---|---|---|---|
| Immediate refusal (below retrieval threshold, zero LLM) | 8 | 0.2 | 0.3 |
| QA (grounded) | 8 | 25 | 53 |
| Artifact (deterministic HTML/Markdown summary, no LLM) | 2 | 0.1 | 0.1 |
| Ship 30 essay | 2 | 150 | 224 |
| Empty-session essay prompt | 1 | 0.005 | 0.005 |

Compared to README §2 "Measured First-Run Benchmarks": retrieval p95 "24 ms" is unverified end-to-end here, but the overall QA path (which includes model generation) hits 25–53 s — the README's retrieval-only latency is honest; nothing is overclaimed on the LLM latency side.

---

## 5. Findings table (new or re-confirmed in RUN2)

| ID | Severity | Area | Finding | Evidence |
|---|---|---|---|---|
| R2-F1 | **HIGH** | Ship 30 skill | **Hardcoded template headings bleed between topics.** `backend/app/skills/ship30.py:287` hardcodes 5 body H2 strings. S4 ("activation") and S5 ("PLG loops featuring Elena Verna") produced the *same* 5 body headings. Hypothesis #4 "template headings" **NOT fixed**. | ship30.py:287–291 + S4/S5 heading arrays |
| R2-F2 | **HIGH** | Grounding faithfulness | **Fabricated quote with explicit attribution.** The S4 essay places `"activation is just so critical"` in quotation marks and attributes it to Sean Ellis. SQL `ILIKE '%activation is just so critical%'` across all 21,994 chunks returns **0 rows**. Validator's `Quotes Verified 4/6` partially caught it, but the surfaced essay still contains it. | S4 artifact body + Postgres full-text search |
| R2-F3 | **HIGH** | Grounding faithfulness | **Paraphrased quote presented as verbatim.** S4 essay: `"When do we think they've had a good enough experience to really know it?"` attributed to Ellis. The actual Ellis line is `"like when do I think they've had a good enough experience with the product to really know it?"` — pronoun flip (`I` → `we`) and truncation. | S4 artifact body + chunks table |
| R2-F4 | HIGH | Cloud provider | **`anthropic` package missing from `backend/requirements.txt`.** `LLM_PROVIDER=anthropic` hard-fails on first import. Brief says "at least one cloud provider integrated." | `docker compose exec backend python -c 'from app.llm.anthropic_provider import AnthropicProvider; AnthropicProvider(…)'` raises `RuntimeError: anthropic not installed` |
| R2-F5 | **HIGH** | Essay latency | Ship 30 essay still takes 224 s on the "Turn that into…" path (S4) despite the round-2 timing instrumentation. Hypothesis #4 "~250 s" essentially unchanged on the two-topic chain. | S4 elapsed 224.3 s, `latency_ms=224324` |
| R2-F6 | MEDIUM | Essay quality | S5 essay is 744 words, 42 % of the 1,250 target; all 5 section budgets violated. The validator correctly flags it but still ships the artifact. | S5 chat message: `R_LENGTH FAIL`, 5× `R_SECTION_BUDGET FAIL` |
| R2-F7 | MEDIUM | Grounding | S5 validator reports `R_CITATION_FORMAT FAIL — Detected non-standard citation formats like [S1] or ([S4]...)` — the mixed `([S#]…)` wrapper historical defect reappeared in at least one place. | validator report in S5 chat message |
| R2-F8 | MEDIUM | Operability | DB-unavailable request returns `HTTP 500 internal_server_error` instead of `HTTP 503 db_unavailable` documented in `docs/architecture.md §10`. Envelope is correct and no stack leaks, but the status code is wrong. | `curl -X POST /sessions` while db stopped |
| R2-F9 | LOW | README | `VITE_API_BASE_URL` isn't templated from `BACKEND_PORT`; port override breaks the UI silently (G1). | fresh clone .env experiment |
| R2-F10 | LOW | README | `OLLAMA_CONTEXT_LENGTH` guidance inconsistent (8192 vs 16384) and ignored by stack (G2). | README §3 and §5 |
| R2-F11 | LOW | README | "303 episode directories" vs actual 302 ingested documents / 394 raw `.md` files (G3). | README §2 vs `/health` vector_count |
| R2-F12 | LOW | Windows docs | README does not warn about Git Bash `/tmp` path translation when using `docker compose exec` (G4). | reproduction in this run |

---

## 6. UNVERIFIED in RUN2

- Embedding-dimension mismatch (would require re-booting a temp stack with a bad `EMBEDDING_DIM`).
- A true round-trip timeout from the live route (would require editing `.env` + backend restart; the degraded code path is proven in-process, which is a lower-confidence signal).
- Browser visual verification of the artifact panel for the two new essays (no browser session this run; the sanitize + sandbox checks were done in AUDIT_FINAL Phase 7).
- 8-of-8 S1 deep-faithfulness pass per transcript (not re-run; only the two essays were verified by chunk lookups, and both surfaced issues).
- Full 302-file ingestion time on the fresh clone (used `--limit 10` to stay within budget).

---

## 7. Minimum must-fix before submitting (ordered)

1. **R2-F2 / R2-F3 (fabricated + paraphrased quote)** — tighten the quote-verbatim rule: FAIL (not "Needs review") on ≥1 unverified direct quote; strip or paraphrase-mark the sentence before storing the artifact. 2 h.
2. **R2-F1 (hardcoded template headings)** — delete the string list at `ship30.py:287` and derive headings from the retrieval/outline step so S4 and S5 produce distinct section titles. 2 h.
3. **R2-F4 (missing anthropic package)** — add `anthropic>=0.34` to `backend/requirements.txt`; prove with `LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-ant-badkey` that `/health` goes degraded with a typed error rather than crashing. 30 m.
4. **R2-F8 (wrong 500 on DB down)** — in `routers/chat.py`'s session lookup, catch `OperationalError`/`DBAPIError` and raise `AppException(code="db_unavailable", status_code=503)`. 20 m.
5. **R2-F5 (essay latency)** — the 224 s on "Turn that into…" is model-bound. Options: (a) parallelize section drafts (same per-section LLM calls, concurrently); (b) switch essay model to `qwen2.5:3b` for a time/quality trade-off; (c) write a shorter 800-word Ship 30 variant for the "Turn that into…" shortcut and only run the 1,250-word one on explicit requests. 2–4 h.
6. **R2-F9 (`VITE_API_BASE_URL` port drift)** — compute it in `scripts/first-run.ps1` and `Makefile` from `BACKEND_PORT`, or document the fix in README §7. 15 m.
7. **R2-F10 / R2-F11 / R2-F12 (README polish)** — unify `OLLAMA_CONTEXT_LENGTH`, correct the 303/302 number, add a Git Bash warning line. 15 m.
8. **R2-F6 (essay length)** — ensure the "needs expansion" repair pass raises body words to the 1,100 floor on short essays. 1 h.
9. **R2-F7 (`[S1]` vs `([S4]…)` leaks)** — strip wrapper patterns before validator rules, or FAIL hard on their detection. 30 m.
10. (optional) Embed-dim mismatch resilience test on a temp stack with `EMBEDDING_DIM=1024`. 30 m.

---

## 8. VERDICT after RUN2

**Still NO-GO without R2-F1 / R2-F2 / R2-F3 / R2-F4 fixed.**

The agent layer (SDK path, D1–D3) is sound. The brittle, user-visible edges remain:

- The two new essays both exhibit template-heading bleed (same 5 H2 titles for different topics).
- One essay contains a quote the transcripts never recorded; another presents a paraphrase as verbatim. For an FDE take-home where grounding is a core criterion, these two defects are the most dangerous things in the repo.
- The cloud provider path cannot run — `anthropic` package not installed.
- A fresh evaluator *can* clone and run the stack following the README (with the four G-level nicks).

Everything else is small polish. Fix items 1–4 above and this becomes a GO.
