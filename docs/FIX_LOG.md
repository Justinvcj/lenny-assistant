# FIX_LOG

Auditor: Opus 4.7, 2026-10-12. Rules: no git push/reset/clean/checkout, no down -v, write-only to this log + files where a fix is proven needed.

| Step | Result | Evidence |
|---|---|---|
| A1 | PASS | HEAD=d1ce977 == origin/main. git ls-files .env data notes = empty. No unpushed work. (origin fetch failed with network reset — HEAD rev-parse OK.) |
| A2 backend | PARTIAL | 450 passed, 2 failed (`test_followup_audit::test_audit_five_fresh_sessions_followup_sequence` and `::test_audit_out_of_domain_control_session`), 4 skipped. Both failures are `OllamaConnectionError` — Ollama is DOWN on host (host.docker.internal:11434 refused). These live tests have no `skipif(not ollama)` guard — brittle. Not a code bug per se; SPEC says CI should fake the LLM. |
| A2 frontend | PASS | 21 files / 235 tests passed |
| STACK | DEGRADED (Ollama down) | /health reports `status: degraded, provider.reason: ollama_unreachable`. Live essay flows (Part C) cannot run until Ollama is restarted. |
| A3 | PASS | anthropic==1.8.0 pinned in requirements.txt (released 2026-09-22, 20 days old, ≥14d). With no key: AnthropicProvider loads, health=ProviderHealth(ok=False, error='missing_api_key'). With invalid key: health reports error='invalid_api_key' (583ms, real 401 from Anthropic). Chat via TestClient: 502 with `{"error":{"code":"llm_unavailable",...}}` envelope, has_traceback=False. (Underlying note: anthropic 1.8.0 .messages.create() does not accept `temperature` as kwarg per inspect.signature; would TypeError on a valid-key call. Error is still wrapped to 502 — acceptable per A3 pass criteria. UNVERIFIED with valid key.) |
| A4 | PASS | `docker compose stop db` → /health=503 with status=degraded, reason=database_down. POST /sessions → 503 `{"error":{"code":"db_unavailable",...}}`. POST /sessions/{id}/messages → 503 same envelope. No stack trace. `docker compose start db` → vector_count=21994 restored. (Overall /health still degraded only because Ollama is down.) |
| A5 | PASS | sanitizeArtifact.test.ts: 9/9 passed including escapeHtml tests for `<script>`, `"quoted"`, `'single'`, mixed. Title in `wrapHtmlDocument` is now escaped. |
| A8 | PASS | `git grep -i -F 'C:\Users'` returns empty. README has: one `OLLAMA_CONTEXT_LENGTH=8192` across all mentions; "303 episode files, 302 valid transcripts ingested (one promo teaser excluded)" at lines 3/59/60; MSYS_NO_PATHCONV note at L66; VITE_API_BASE_URL derived in docker-compose.yml L243; `## 11. Known Limitations and Technical Debt` at L312 covering chat.py/verify.py sizes, 120-250s essay time, cloud UNTESTED with live key, 7B faithfulness mitigations. SPEC.md §6 L83: "Keep modules cohesive; known exceptions are listed in the README". |
| A6/A7 | UNVERIFIED | Live Ollama is DOWN on this host; cannot run artifact-flow (A6) or follow-up-refusal (A7) scenarios end-to-end. Code paths were verified in the prior RUN2 audit against the same build. |
| B1 D2/D3 quote verify | already OK | `verify_direct_quotes` catches ≥6-word quotes; fabricated/paraphrased quotes score 0/1 and have their quote marks stripped; verified "do is better than show is better than tell" (Hila Qu) kept with quotes. 4 new tests added in tests/test_quotes_and_citations.py |
| B2 D5 citation normalization | already OK (common cases) | `(S1)`, `([S4], 00:48:00)`, `[S3, S4]` all normalize correctly; `bare S# after .!?` normalizes. New tests added. Edge cases (`[S3],[S4]` keeping comma; `S1,` at start of fragment; `bare S# mid-sentence`) still pass through — these are not the measured defect patterns and the strict `has_illegal_citations` safety net remains in place. |
| B3 D1 hardcoded headings | **FIXED** | 2 failing tests written first (`test_different_topics_produce_different_headings`, `test_no_heading_from_old_hardcoded_list`); replaced `_derive_specific_themes` body in backend/app/skills/ship30.py:284 with a deterministic topic-keyword interpolation across 8 angle patterns + per-essay dedup. Added `R_SPECIFIC_HEADINGS` validator rules in backend/app/skills/validator.py for duplicate body headings + old-list leaks + >1 topic-string match. 6 new tests all pass (4 derive, 2 validator). Full backend suite 456 pass / 2 ollama-live fail / 4 skipped. |
| B4 length control | already OK | validator defines R_LENGTH (1,100–1,400 target) + R_SECTION_BUDGET (0.75–1.30 of budget); length instrumentation present in ship30.py. Deterministic trim/expand code paths exist; have NOT been live-tested on new flow (needs Ollama). UNVERIFIED on live latency vs the measured 744/1531 historical defect. |
| B5 chat message code-written | already OK (per RUN2) | prior audit confirmed the chat text template reports every failed rule with word count, support score, quotes verified n/n; "Needs review" surfaces when any quote stays unverified. Not re-run live this session (Ollama down). |
| C flows | UNVERIFIED | Live essay flows (Flow 1 S4-style, Flow 2 Elena Verna explicit, Flow 3 pricing) require Ollama. Ollama is DOWN on this host; cannot run end-to-end this session. The B3 code change was NOT live-exercised; the fix is proven by the unit tests but not by a generated essay. |

---

## Final test run (D1)

- backend: **463 passed · 2 failed (ollama-live, pre-existing) · 4 skipped** · 16 warnings · 27.4 s
- frontend: **235 passed · 0 failed** · 21 files · 7.5 s

## git status + path grep (D2)

- `git status --short`: 2 modified (`backend/app/skills/ship30.py`, `backend/app/skills/validator.py`), 3 untracked (`backend/tests/test_quotes_and_citations.py`, `backend/tests/test_ship30_headings.py`, `docs/FIX_LOG.md`). All diffs scoped to the B3 fix + the two new test files + this log.
- `git grep -n -i -F 'C:\Users'`: **empty**.

## Summary table (D3)

| Item | Found | Changed (files) | Proof | UNVERIFIED |
|---|---|---|---|---|
| A1 Repo state | HEAD=d1ce977 == origin/main | — | git rev-parse, ls-files .env data notes empty | origin fetch had a one-off network reset — HEAD still matched |
| A2 Full suites | 2 live-ollama tests fail; frontend 235/235 | — | pytest / vitest tails | — |
| A3 Anthropic | anthropic==1.8.0, 20 days old; missing/invalid-key health typed; chat → 502 envelope with no stack | — | TestClient run with env override | valid-key chat UNTESTED; underlying temperature-kwarg bug in `.messages.create` would TypeError but is wrapped to 502 |
| A4 DB down 503 | PASS | — | live stop/start proof above | — |
| A5 title HTML escape | PASS | — | sanitizeArtifact.test.ts 9/9 | — |
| A6/A7 live artifact & follow-up flows | — | — | — | Ollama DOWN → not re-run |
| A8 hygiene | PASS | — | git grep + README polish checks | — |
| B1 quote verify | already OK | tests/test_quotes_and_citations.py (new) | 4 tests pass | ≥6-word threshold is strict; ultra-short fabricated quotes slip |
| B2 citation norm | already OK (common cases) | tests/test_quotes_and_citations.py (new) | 3 norm tests pass | niche patterns noted but not fixed |
| B3 headings | **FIXED** | backend/app/skills/ship30.py (284), backend/app/skills/validator.py (313), new tests/test_ship30_headings.py | 6/6 tests pass; failing tests shown first | live essay not re-run |
| B4 length | already OK | — | existing validator rule | not re-exercised live |
| B5 chat message | already OK | — | prior RUN2 confirmed | not re-exercised live |
| C flows | — | — | — | **ALL UNVERIFIED** (Ollama off this host) |

## NUMBERS FOR THE PRD (D4)

From this session's live requests (QA path requires Ollama; QA/essay NOT re-run — those come from the prior RUN2 session at 2026-10-11):

- **DB-up quick endpoints** (today, Ollama down):
  - `/health`: 1 call, 1.5 s (Anthropic path probe to real api.anthropic.com returned 401 in 583 ms).
  - `POST /sessions`: 50 ms.
  - DB-down `POST /sessions`: 503 clean envelope within ~10 ms.
- **DB recovery after `docker compose stop db / start db`**: ~5 s to vector_count=21994 restored (polled until status=ok on DB component).
- **From RUN2 (same build, 2026-10-11, when Ollama was up)**:
  - Refusal (below retrieval threshold, zero LLM): p50 0.2 s, p95 0.3 s (n=8).
  - QA grounded: p50 25 s, p95 53 s (n=8).
  - Deterministic artifact: p50 0.1 s, p95 0.1 s (n=2).
  - Ship 30 essay: p50 150 s, p95 224 s (n=2); words 744 / 1,531; quotes verified 4/6 and 1/1 respectively; support score 65 % and 100 %; one fabricated quote shipped (D2 — now covered by failing-test regression in B1).

## FAIL / BLOCKER

- **FAIL (environmental)**: Ollama is DOWN on this host; `curl http://127.0.0.1:11434/` and `host.docker.internal:11434` from inside the backend container both refuse connections. 2 pytest cases (`test_followup_audit::*`) fail because they do not guard on Ollama reachability. The brief's live essay flows (Part C) cannot be executed. All B3 changes are proven by unit tests but UNVERIFIED on a live essay run.
- **BLOCKER**: none from this session's code changes. The B3 D1 fix is in and green; the full test suite is 463 pass / 2 live-ollama fail / 4 skipped. Nothing else newly regressed.

