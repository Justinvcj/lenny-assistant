# SPEC — Lenny Growth Assistant (READ THIS FIRST, EVERY SESSION)

A grounded chat assistant over Lenny's Podcast transcripts, built as a take-home for Oogway Labs (Forward Deployed Engineer). Deadline: Mon 12 Oct 2026, end of day. Zero budget. Demo MUST run on local Ollama with no API keys.

Source of truth order: this file > docs/architecture.md > docs/security.md > docs/design.md > docs/PRD.md.
If you find a conflict or an unknown, STOP and list it. Do not guess silently.

## 1. Non-negotiables (from the assignment)
- Backend: FastAPI. Database: PostgreSQL. Persist sessions + messages.
- Agent layer: Claude Agent SDK (`claude-agent-sdk`). Skills/tools, not a bare API call.
- LLM toggle: Ollama (default, demo) and a cloud provider, switched by config only.
- Knowledge base: Lenny transcripts, chunked, embedded, indexed, cited back to the source episode.
- Assistant must refuse honestly when transcripts don't cover a question.
- "Ship 30 for 30" essay skill: writing principles encoded as structured rules, not a one-off prompt.
- Artifact viewer: renders generated Markdown/HTML beside the chat, safely (untrusted HTML).
- One-command start (`docker compose up`), `.env.example`, structured logs, graceful failures.
- Deliverables: repo, README, PRD, design.md, architecture.md, agent transcripts (failed attempts too), tests, 2-3 min demo video.

## 2. Stack (fixed)
- Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, psycopg 3, `pgvector` python package.
- Postgres via image `pgvector/pgvector:pg16` (vectors live in the same DB; no Chroma).
- Ollama runs NATIVELY on the host (GPU). Containers reach it at `http://host.docker.internal:11434`.
- Chat model: `qwen2.5:7b`. Embeddings: `nomic-embed-text` (dimension verified in code, expected 768).
- Agent: `claude-agent-sdk` pointed at Ollama via `ANTHROPIC_BASE_URL` + dummy `ANTHROPIC_AUTH_TOKEN=ollama`.
- The SDK needs the Claude Code CLI: backend image installs Node 20 + `npm i -g @anthropic-ai/claude-code`.
- Frontend: React + Vite + TypeScript, `react-markdown`, `dompurify`. No UI framework required.
- Tests: pytest, httpx, (frontend) vitest. Lint: ruff.

## 3. Repo layout
```
lenny-assistant/
  SPEC.md  CLAUDE.md  AGENTS.md  README.md  .env.example  docker-compose.yml  .gitignore
  backend/
    Dockerfile  requirements.txt  alembic/  alembic.ini
    app/
      main.py  config.py  db.py  models.py  schemas.py  logging_setup.py  errors.py
      routers/  health.py  sessions.py  chat.py  artifacts.py
      llm/      base.py  ollama_provider.py  anthropic_provider.py  factory.py
      rag/      parser.py  chunking.py  embeddings.py  ingest.py  retrieval.py
      agent/    router.py  orchestrator.py  tools.py  prompts.py  verify.py
      skills/   ship30.py  ship30_rules.yaml
    scripts/    ingest.py  eval.py
    tests/
  frontend/     (Vite app)
  eval/         questions.json
  docs/         PRD.md  architecture.md  design.md  security.md  TEST_PLAN.md  EVAL_RESULTS.md  DATA_NOTES.md
  transcripts/  (agent logs, scrubbed, incl. failed attempts)
  data/         (GITIGNORED: transcript source files)
  spike/        (kept as evidence)
  notes/        (GITIGNORED: personal interview prep)
```

## 4. Key design decisions (all measured in the spike; do not change without asking)
- D1 RETRIEVAL RUNS IN CODE. For knowledge and essay intents, retrieval always runs before the model. Spike: raw tool-calling skipped the tool 4/4 times on "activation in the first week".
- D2 TOOL MENU NARROWING. A deterministic intent router (rules) decides which 1-2 tools the agent may see per request. Fewer tools = reliable 7B behaviour.
- D3 LOCKED-DOWN AGENT. Use an allowlist of ONLY our MCP tools; disable all built-in SDK tools (Bash, Read, Write, Edit, WebFetch, etc). Spike: with ~26 built-ins the prompt was ~21.7k tokens and the model called irrelevant tools; with them off, 384 tokens and correct tool use. Also a security requirement (a server-side agent with Bash is remote code execution). Set the agent `cwd` to an empty temp dir so no project CLAUDE.md is injected into the model prompt.
- D4 GROUNDING PROTOCOL. Retrieved chunks are given to the model as numbered sources `[S1]..[Sn]`. The model must tag claims with `[S#]`. Code validates every tag against the retrieved set, builds the citation list from the database (never from model text), and attaches the source passage. If retrieval is empty or below `RETRIEVAL_MIN_SCORE`, return the refusal WITHOUT calling the LLM.
- D5 FAITHFULNESS IS NOT CITATION. Spike found 2/15 answers cited the right episode but reversed the claim. UI must show the source passage next to each citation so the user can check.
- D6 Providers: `ollama` (default, tested) and `anthropic` (implemented, UNTESTED without a key; say so everywhere). No OpenAI path (the Agent SDK is Anthropic-protocol only).
- D7 Artifacts are untrusted. Sandboxed iframe, no `allow-scripts`, no `allow-same-origin`, DOMPurify, CSP inside srcdoc. See docs/security.md.
- D8 Degraded mode: if the agent runtime fails (CLI missing/timeout), fall back to a direct provider call with the same grounded prompt and flag `degraded: true` in the response.

## 5. Configuration (all via env; mirror in `.env.example`)
| Var | Default | Notes |
|---|---|---|
| LLM_PROVIDER | ollama | ollama / anthropic |
| LLM_MODEL | qwen2.5:7b | for anthropic set a current Claude model id |
| OLLAMA_BASE_URL | http://host.docker.internal:11434 | native Ollama on host |
| EMBEDDING_MODEL | nomic-embed-text | |
| EMBEDDING_DIM | 768 | verified at startup against a live embed call |
| DATABASE_URL | postgresql+psycopg://postgres:localdev@db:5432/lenny_assistant | local throwaway password |
| ANTHROPIC_API_KEY | (empty) | optional, only for anthropic provider |
| RETRIEVAL_TOP_K | 6 | |
| RETRIEVAL_MIN_SCORE | tune on eval | cosine similarity floor for answering |
| HISTORY_TURNS | 6 | prior messages included in the prompt |
| AGENT_TIMEOUT_S | 120 | |
| ARTIFACT_MAX_BYTES | 200000 | |
| CORS_ORIGINS | http://localhost:5173,http://localhost:3000 | |
| DATA_DIR | /data | transcript source files |
| LOG_LEVEL | INFO | |

## 6. Conventions
- Type hints everywhere, small functions, one responsibility per module. Keep modules cohesive; known exceptions are listed in the README.
- Errors: JSON `{"error": {"code": "...", "message": "..."}}` with correct HTTP status. Never leak stack traces.
- Logs: JSON, one line per event. Required fields where relevant: `request_id, session_id, intent, provider, model, retrieval_ms, llm_ms, total_ms, n_chunks, top_score, degraded, error_code`.
- No secrets in repo. `.env` ignored. Placeholder values only in `.env.example`.
- Every feature ships with at least one test. Fake the LLM in unit tests (no Ollama needed in CI).
- Comments explain WHY (trade-offs), not what.

## 7. Definition of done (per task)
Runs locally; tests pass; lint passes; relevant doc section updated; no TODO left silently; short summary of what changed and how to verify.

## 8. Do-not list
- Do not add services/frameworks not listed here (no Chroma, Redis, Celery, LangChain).
- Do not enable any built-in agent tools. Do not use `allow-scripts` or `allow-same-origin` on the artifact iframe.
- Do not commit `data/`, `.env`, `notes/`, or any real key.
- Do not claim something works unless it was run. Mark untested things `UNTESTED`.
- Do not fabricate Ship 30 principles; they come from the linked source (see playbook P6).

## 9. Measured facts from the spike (hardware: RTX 4050 6GB, 16GB RAM)
- qwen2.5:7b at num_ctx 4096: 5.1 GB, 82% GPU / 18% CPU.
- Raw tool-calling: "retention" question called the tool 4/4; "activation in the first week" 0/4.
- SDK with all built-in tools: ~21.7k input tokens per call, tool never called, hit max turns after 56 s.
- SDK with built-ins disabled: 384 input tokens, tool called, 15.2 s end to end (stub tool).
- Reliability (5 runs x 5 questions): in-scope tool use 15/15; off-topic refusals 10/10; 2/15 answers reversed the source claim; 1/15 embellished.
- Embedding: first call ~15 s (model load); later calls fast.
