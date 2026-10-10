# Lenny Growth Assistant — SESSION STATE
# ── Read this at the start of every new session ──

## Project
- **Repo**: `c:\Users\Justin\The Global Projects Folder\lenny-assistant`
- **GitHub**: https://github.com/Justinvcj/lenny-assistant.git  branch: `main`
- **Goal**: 100% local RAG conversational agent (Lenny's Podcast), zero-budget, Ollama qwen2.5:7b

## How to Resume in 30 Seconds
1. Read `AGENTS.md` and this file.
2. Read `SPEC.md` (source of truth).
3. Check git: `git log --oneline -8` to see last commit.
4. Run tests: `..\.venv\Scripts\python.exe -m pytest tests` (backend) and `npm test -- --run` in `frontend/`.
5. Then pick up **Next Action** below.

## Critical Rules (never violate)
- PowerShell only — NO `&&` or `||` command chaining (one command per shell call)
- Never commit `data/`, `notes/`, `.env`, any key
- Backend venv: `.venv\Scripts\python.exe` from repo root or `..\.venv\Scripts\python.exe` from `backend/`
- Git branch: `main` → `origin/main`
- Never enable built-in agent tools (`builtin_tools=[]` in orchestrator)
- No `allow-scripts`/`allow-same-origin` on artifact iframe

## Stack Snapshot
| Layer | Tech |
|---|---|
| Backend | FastAPI + SQLAlchemy async + pgvector + Alembic |
| LLM | Ollama `qwen2.5:7b` via `OllamaProvider`; Anthropic fallback |
| Embeddings | Ollama `nomic-embed-text` (768-dim) |
| DB | PostgreSQL 16 + pgvector (Docker, host `db:5432`) |
| Frontend | React 18 + TypeScript + Vite + Vitest |
| Tests | `pytest` (backend) + `vitest` (frontend) |

## Completed Phases (committed to `main`)
| Commit | Phase | Summary |
|---|---|---|
| `962a625` | P4a | Intent router, prompt engine, citation verifier |
| `b64fbb7` | P4b | LLM providers, MCP tools, Claude Agent orchestrator |
| `fe7c62d` | P4c | Chat endpoint, immediate refusal, citation retry |
| `fde0cd8` | P4d | Real E2E evaluation against qwen2.5:7b |
| `4c5e596`+ | P5 | Full React chat UI, 150/150 Vitest tests |
| `2bf3b28` | **P6** ✅ | Ship30 skill, validator, P6b tests, test infra fixes |

## Current Position: P7 — Artifact Panel Safe Viewer

### What was done this session
- ✅ `backend/app/skills/__init__.py` — made skills a package
- ✅ `backend/app/skills/ship30_rules.yaml` — rules (all DRAFT-UNVERIFIED, source missing)
- ✅ `backend/app/skills/validator.py` — pure-code essay validator (R_LENGTH, R_HOOK, R_STRUCTURE, R_FORMATTING, R_TAKEAWAY, R_CITATION)
- ✅ `backend/app/skills/ship30.py` — full pipeline: plan_outline → draft_section (per-section LLM calls) → assemble → validate → repair-once
- ✅ `backend/app/agent/tools.py` — `generate_ship30_essay` wired to real skill (graceful degradation if no sources/provider)
- ✅ `backend/app/routers/chat.py` — ESSAY deterministic fallback added; markdown artifact persistence; `artifact` response now returns `{id, title, type}`
- ✅ `backend/tests/test_ship30.py` — 14 tests: validator unit tests, plan_outline tests, E2E with FakeLLMProvider
- ✅ `backend/tests/conftest.py` — Windows `WindowsSelectorEventLoopPolicy` fix for asyncio tests
- ✅ `backend/tests/test_health.py` — fixed AsyncMock scalar coroutine bug
- ✅ `backend/tests/test_sessions.py` — rewritten to use `dependency_overrides` instead of `patch`
- ✅ `frontend/src/components/CitationChips.tsx` — fixed unhandled setTimeout after teardown (scroll ref)
- 🔲 **P6 real run** — two essay topics via live Ollama; results in `docs/AGENT_NOTES.md` (UNTESTED, DB not running locally)
- 🔲 **Commit + push** — `feat: ship30 skill` → `origin/main`
- 🔲 **P7** — Artifact panel safe viewer (frontend + backend)

## Next Action
```
Commit P6b to main:
  git add -A
  git commit -m "feat(phase-6): ship30 essay skill, validator, P6b tests, test infra fixes"
  git push origin main

Then proceed to P7 (PROMPTS.md ## P7).
```

## P7 Brief (from PROMPTS.md)
Build the artifact panel safe viewer: fetch artifact by id, render HTML in sandboxed iframe (no `allow-scripts`, no `allow-same-origin`). Frontend `ArtifactPanel` already scaffolded in P5. Wire `GET /artifacts/{id}` to it and add tests.

## Known Gaps / Tech Debt
- `ship30_rules.yaml` rules are DRAFT-UNVERIFIED (source file `notes/ship30_source.md` was never provided)
- Real Ship 30 run requires Postgres + Ollama running (Docker); not run locally this session — marked UNTESTED
- `RuntimeWarning: coroutine never awaited` in ingest tests — pre-existing, not blocking
- P5 teamwork subagent hit quota limit repeatedly — P5 work was already done, subagent was auditing

## Test Commands (verify before commit)
```powershell
# Backend (run from repo root)
..\.venv\Scripts\python.exe -m pytest tests

# Frontend (run from frontend/)
npm test -- --run
npm run build
```

## Git Push Troubleshooting (if push hangs/fails)
```powershell
git config http.postBuffer 524288000
git config http.version HTTP/1.1
git config http.sslbackend openssl
git push origin main
```
