# Lenny Growth Assistant — SESSION STATE
# ── Read this at the start of every new session ──

## Project
- **Repo**: `<project folder>`
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
| `2bf3b28` | P6 | Ship30 skill, validator, P6b tests, test infra fixes |
| *(pending)* | **P7** ✅ | Artifact panel safe viewer, sandboxed iframe CSP, 166/166 vitest, 307/307 pytest |

## Current Position: P8 — Security Self-Review & Adversarial Audit

### What was done in P7
- ✅ `backend/app/routers/artifacts.py` — added `POST /artifacts` with `ARTIFACT_MAX_BYTES` (413 `artifact_too_large`) and type `{markdown, html}` validation; `GET /artifacts/{id}`
- ✅ `backend/app/schemas.py` — `ArtifactCreate` and `ArtifactResponse` models
- ✅ `backend/app/routers/chat.py` — enforced artifact byte size cap (413) and type validation in persistence pipeline
- ✅ `backend/app/agent/tools.py` — `create_artifact` tool validated for type in `('html', 'markdown')`
- ✅ `backend/tests/test_artifacts.py` — 6 tests covering 200, 404, 201, 413, 422, and tool validation
- ✅ `frontend/src/utils/sanitizeArtifact.ts` — DOMPurify sanitization with forbidden tags/handlers/remote images, CSP meta tag wrapper, size guard
- ✅ `frontend/src/components/ArtifactPanel.tsx` — sandboxed iframe with empty `sandbox=""`, ReactMarkdown preview with safe links, Source tab, Copy and Download actions, size warning
- ✅ `frontend/src/components/MessageItem.tsx` — added "Open artifact: [Title]" button when message has an artifact
- ✅ `frontend/src/__tests__/ArtifactPanel.test.tsx` — 19 comprehensive tests for malicious payload corpus, CSP verification, empty sandbox tokens, download/copy buttons, and markdown link hardening
- ✅ `docs/TEST_PLAN.md` — added automated test summary and manual browser checklist (M1–M11)
- ✅ 307/307 backend pytest tests passing, 166/166 frontend vitest tests passing, production build passing

## Next Action
```
Commit P7 to main:
  git add -A
  git commit -m "feat(phase-7): artifact panel and sandboxed viewer"
  git push origin main

Then proceed to P8 (PROMPTS.md ## P8 Security self-review).
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
