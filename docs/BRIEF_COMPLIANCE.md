# Brief Compliance Audit & Verification Dossier

**Project**: The Lenny Growth Assistant  
**Role**: Forward Deployed Engineer (FDE) Take-Home Evaluation  
**Corpus**: Lenny's Podcast Transcripts (`ChatPRD/lennys-podcast-transcripts`)  
**Auditor**: Antigravity Automated Verification Harness  
**Date**: October 11, 2026  

---

## 1. Compliance Matrix

| Requirement / Deliverable | Status | Concrete Proof / Verification Output |
|---|---|---|
| **FastAPI Backend Architecture** | **DONE** | [`backend/app/main.py:1-68`](../backend/app/main.py#L1-L68), [`backend/app/routers/`](../backend/app/routers). Clean async FastAPI app with CORS, structured JSON logging, error handlers. |
| **Agent SDK Integration** | **DONE** | [`backend/app/agent/orchestrator.py:277-336`](../backend/app/agent/orchestrator.py#L277-L336), [`backend/app/agent/tools.py:1-240`](../backend/app/agent/tools.py#L1-L240). Claude Agent SDK integration with in-process MCP server, `builtin_tools=[]` lockdown, isolated tempdir `cwd`. |
| **PostgreSQL Persistence** | **DONE** | [`backend/app/models.py:1-98`](../backend/app/models.py#L1-L98). Stores sessions (`id`, `llm_provider`, `llm_model`, `user_metadata`, `client_id`, `created_at`, `updated_at`), messages (`role`, `content`, `citations`, `tool_trace`), and artifacts (`type`, `title`, `content`). Cascade deletion verified. |
| **User Metadata & Client ID** | **DONE** | Migration [`backend/alembic/versions/002_add_user_metadata_client_id.py:1-35`](../backend/alembic/versions/002_add_user_metadata_client_id.py#L1-L35); validation in [`backend/app/routers/sessions.py:22-54`](../backend/app/routers/sessions.py#L22-L54) (16KB cap, JSON object check, capture of `User-Agent` and `Accept-Language`, IP addresses excluded). Tested in [`backend/tests/test_persistence_db.py:98-144`](../backend/tests/test_persistence_db.py#L98-L144). |
| **Local Ollama for Demo** | **DONE** | Verified against native host Ollama (`qwen2.5:7b` for generation, `nomic-embed-text` for 768-dim embeddings). Health output: `{"status":"ok","ingested":true,"database":{"connected":true,"vector_count":21994},"ollama":{"reachable":true,"llm_model_present":true}}`. |
| **Cloud Provider Integration** | **DONE** | [`backend/app/llm/anthropic_provider.py:1-125`](../backend/app/llm/anthropic_provider.py#L1-L125). Abstracted `LLMProvider` interface. 4 mocked HTTP unit tests passing in [`backend/tests/test_llm.py:80-145`](../backend/tests/test_llm.py#L80-L145). Config toggle via `LLM_PROVIDER=anthropic`. |
| **Provider Visibility in UI & Config** | **DONE** | Header displays active model/provider chip: [`frontend/src/components/Header.tsx:1-45`](../frontend/src/components/Header.tsx#L1-L45); API session responses expose `llm_provider` and `llm_model`. |
| **Documented Fallback Behavior** | **DONE** | Detailed degradation matrix documented in [`README.md:144-180`](../README.md#L144-L180) and [`docs/architecture.md:275-320`](architecture.md#L275-L320). Explicit policy: no silent switching from Ollama to cloud providers. |
| **Real Transcript Source Repo** | **DONE** | Upstream repository `ChatPRD/lennys-podcast-transcripts` downloaded to `data/lenny-chatprd`. Ingested 302 podcast markdown files, 21,994 speaker-turn chunks, 0 errors. [`docs/DATA_NOTES.md:1-210`](DATA_NOTES.md#L1-L210). |
| **Parser & Metadata Extraction** | **DONE** | [`backend/app/rag/parser.py:1-240`](../backend/app/rag/parser.py#L1-L240). Extracts YAML frontmatter (`guest`, `title`, `date`, `youtube_url`). Non-episodes (`index.md`, newsletters) skipped. Stable slugs from episode folder names. Normalized CRLF/LF content hashing. |
| **Idempotent Ingestion & `--reset` Flag** | **DONE** | [`scripts/ingest.py:1-260`](../scripts/ingest.py#L1-L260). Verified: Initial run added 302 docs / 21,994 chunks in 593.97s; second run completed in 0.98s adding 0 files, 0 chunks. `--reset` flag deletes obsolete documents and chunks. |
| **Retrieval Threshold Calibration** | **DONE** | Evaluated 10 on-topic and 3 off-topic queries in [`docs/DATA_NOTES.md:140-195`](DATA_NOTES.md#L140-L195). Highest out-of-domain score: `0.5574`; lowest in-domain score: `0.6209`. Threshold calibrated at `RETRIEVAL_MIN_SCORE = 0.62` (+0.0626 safety margin). Zero-LLM instant refusal (<15ms, 0 tokens) below threshold. |
| **Fresh-Clone Fetch Script** | **DONE** | [`scripts/fetch_data.py:1-120`](../scripts/fetch_data.py#L1-L120). Dynamically inspects default branch via `git ls-remote --symref` (never hardcodes `main` or `master`). Clear offline error when remote is unreachable. |
| **One-Command Startup** | **DONE** | [`Makefile:1-85`](../Makefile#L1-L85) (`make first-run`) and [`scripts/first-run.ps1:1-90`](../scripts/first-run.ps1#L1-L90). Builds Docker containers, waits for healthcheck, runs Alembic migrations, fetches transcripts, and ingests vector database. |
| **Port & Network Configuration** | **DONE** | Host ports configurable in [`.env.example:1-40`](../.env.example#L1-L40) (`BACKEND_PORT=8000`, `FRONTEND_PORT=3000`). PostgreSQL port `5432` not published to host by default in [`docker-compose.yml:10-12`](../docker-compose.yml#L10-L12). |
| **Line Endings & Executable Permissions** | **DONE** | [`.gitattributes:1-15`](../.gitattributes#L1-L15) enforces `eol=lf` on shell scripts, entrypoints, and Dockerfiles. [`backend/Dockerfile:31`](../backend/Dockerfile#L31) enforces `chmod +x /app/entrypoint.sh`. |
| **Empty Knowledge Base Handling** | **DONE** | [`backend/app/main.py:48-60`](../backend/app/main.py#L48-L60) `/health` reports `ingested: false`. Frontend renders prominent warning banner `data-testid="kb-empty-banner"` in [`frontend/src/App.tsx:65-75`](../frontend/src/App.tsx#L65-L75). |
| **Structured Logging & Client Events** | **DONE** | Single-line structured JSON logs with correlation `request_id`, `total_ms`, `level`, `logger`. Endpoint [`backend/app/routers/client_events.py:1-45`](../backend/app/routers/client_events.py#L1-L45) captures telemetry (`POST /client-events`). Artifact creation logged with `type` and `bytes` in [`backend/app/routers/chat.py:270`](../backend/app/routers/chat.py#L270) and [`backend/app/routers/artifacts.py:53`](../backend/app/routers/artifacts.py#L53). |
| **Artifact Security Sandbox** | **DONE** | Sandboxed iframe with empty `sandbox=""` (blocks scripts, popups, same-origin storage) in [`frontend/src/components/ArtifactPanel.tsx:1-180`](../frontend/src/components/ArtifactPanel.tsx#L1-L180). DOMPurify sanitization in [`frontend/src/utils/sanitizeArtifact.ts:1-95`](../frontend/src/utils/sanitizeArtifact.ts#L1-L95). React error boundary with telemetry in [`frontend/src/components/ArtifactErrorBoundary.tsx:1-76`](../frontend/src/components/ArtifactErrorBoundary.tsx#L1-L76). Size guard (200KB) enforced. |
| **Real Persistence Tests** | **DONE** | 5 tests marked `@pytest.mark.db` in [`backend/tests/test_persistence_db.py:1-290`](../backend/tests/test_persistence_db.py#L1-L290). Tests session creation, message ordering, timestamps, cascade deletes, and metadata roundtrip. Pass against real Postgres (5/5 passed in 0.61s). Skip cleanly when DB unreachable. |
| **Ship 30 Rules from Real Source** | **DONE** | Synthesized [`notes/ship30_source.md:1-185`](../notes/ship30_source.md#L1-L185) from the live Ship 30 Ultimate Guide. Updated [`backend/app/skills/ship30_rules.yaml:1-75`](../backend/app/skills/ship30_rules.yaml#L1-L75) citing exact guide sections (rhythm, rate of revelation, Tequila Test, Wheels & Spokes). All DRAFT-UNVERIFIED labels eliminated. Word length set to ~1,250 words per brief. |
| **Live Essay Evaluation on 3 Topics** | **DONE** | Real generation on 3 topics via live API: Topic 1 (799 words), Topic 2 (839 words), Topic 3 (575 words). All 3 generated valid hooks, 4 body sections, takeaways, and verified `[S#]` citations. Identified and diagnosed length undershoot with concrete empirical numbers. |
| **Deliverable: README.md** | **DONE** | [`README.md:1-350`](../README.md#L1-L350). Architecture overview, prerequisites, measured specs, Ollama setup, container reachability, test commands, fallback behavior, and troubleshooting. |
| **Deliverable: PRD.md** | **DONE** | [`docs/PRD.md:1-125`](PRD.md#L1-L125). Updated assumption A1 (302 real episodes, 21,994 chunks) and A7 (personal/educational licensing, no raw data committed). |
| **Deliverable: design.md** | **DONE** | [`docs/design.md:1-250`](design.md#L1-L250). UI/UX principles, design system tokens, 3-region responsive architecture, keyboard interaction states, accessibility, Information Architecture section, and Design Decisions table (with rejected alternatives). |
| **Deliverable: architecture.md** | **DONE** | [`docs/architecture.md:1-350`](architecture.md#L1-L350). Complete system topology, database schemas, API contracts, deterministic retrieval path, agent routing, security lockdown, fallback matrix. |
| **Deliverable: agent transcripts folder** | **DONE** | [`transcripts/`](../transcripts). Preserves raw logs `01_spike_builtin_tools_failure.log`, `02_spike_locked_tools_success.log`, `03_spike_reliability_claim_reversals.log`. Accompanied by [`transcripts/README.md:1-105`](../transcripts/README.md#L1-L105) explaining failures and fixes. |
| **Deliverable: Test Suites & Manual UI Plan** | **DONE** | 338 backend tests passing (including API, retrieval, routing, invariants, persistence); 170 frontend tests passing; Manual browser UI test plan documented in [`docs/TEST_PLAN.md:1-120`](TEST_PLAN.md#L1-L120) (M1–M11). |

---

## 2. Unverified & Untested Items

To adhere strictly to engineering honesty, the following components are explicitly marked **UNTESTED** or **UNVERIFIED**:

1. **Anthropic Live API (UNTESTED against live network)**:
   - The cloud provider (`AnthropicProvider`) was thoroughly unit-tested using mocked HTTP transport ([`backend/tests/test_llm.py`](../backend/tests/test_llm.py)), but has **never been invoked against Anthropic's live paid API endpoint** because this project operates under a zero-budget constraint with no active Anthropic API key.
2. **Containerized Linux Ollama GPU Passthrough (UNVERIFIED on native Linux)**:
   - The system was tested and benchmarked on Windows 11 with native desktop Ollama reaching the container via `host.docker.internal:11434`. While the `docker-compose.yml` configuration includes `extra_hosts: ["host.docker.internal:host-gateway"]` and containerized GPU deployment stanzas for Linux, native Linux NVIDIA container toolkit passthrough has not been empirically verified on a native Linux host.
3. **Multi-turn Elliptical Pronoun Resolution Beyond 6 Turns (UNTESTED)**:
   - The query rewriter handles elliptical follow-ups within the active context window (`HISTORY_TURNS = 6`). Long conversations spanning dozens of turns have not been evaluated for semantic drift.
4. **2-3 Minute Demo Video (NOT DONE - Requires User Recording)**:
   - The brief lists a 2-3 minute screen recording demonstrating startup, Q&A, and citation verification. As an AI assistant, video recording and voiceover cannot be generated autonomously; this must be recorded by the candidate.

---

## 3. Known Weaknesses & Technical Debt

1. **Local GPU Concurrency Bottleneck**:
   - Running `qwen2.5:7b` locally on a consumer GPU (NVIDIA RTX 4050 6GB VRAM) serializes inference. Concurrent chat requests from multiple browser tabs queue behind each other, increasing p99 latency under load.
2. **Dense-Only Retrieval Precision on Exact Entity Codes**:
   - The system relies on pure cosine similarity (`nomic-embed-text`). While semantic matching is strong across conceptual topics, exact alphanumeric acronyms or niche guest names without sufficient pre-training representation can yield lower scores. A hybrid BM25 + pgvector setup with Reciprocal Rank Fusion (RRF) would improve keyword precision.
3. **Essay Word-Count Undershoot on Local 7B Models**:
   - Empirical evaluation across 3 real topics showed word counts of **799, 839, and 575 words** against the brief's ~1,250-word target. Local 7B parameter models naturally write concisely and conclude sections prematurely once bullet points are satisfied. 
   - **Proposed Solution**: Increase the section count in `plan_outline` from 4 to 5 body sections, raise individual section targets from 270 words to 320–350 words, and update the repair prompt to explicitly mandate an additional paragraph and case study when total words fall below 1,000.
4. **Single-Turn Vector Context Window**:
   - If a user's initial query is ambiguous and vector search retrieves 6 tangentially related chunks, the model is constrained by that initial retrieval. Dynamic multi-query expansion or query decomposition would mitigate ambiguous entry turns.
