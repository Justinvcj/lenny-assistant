# The Lenny Growth Assistant

A production-grade, domain-specific AI assistant and knowledge engine grounded in transcripts from **Lenny's Podcast** (303 episode files, 302 valid transcripts ingested (one promo teaser excluded), comprising 21,994 pgvector chunks).

Built for the Forward Deployed Engineer take-home assignment, featuring:
- **FastAPI** backend with asynchronous request routing, strict validation, and structured telemetry.
- **PostgreSQL 16 + pgvector** vector storage with cosine similarity search and content-hash idempotency.
- **Dual Model Architecture**: Native local **Ollama** (`qwen2.5:7b` + `nomic-embed-text`) with zero cloud cost, plus opt-in cloud provider support (**Anthropic Claude 3.5 Sonnet**).
- **React 18 + Vite** desktop/mobile responsive UI featuring real-time diagnostics, citation chips with verbatim podcast quotes, interactive chat composer, and sandboxed artifact rendering.
- **One-Command Startup**: Fully dockerized deployment with automated migrations and ingestion pipelines.

---

## 1. System Architecture Overview

```
                      ┌───────────────────────────────────────┐
                      │          React 18 Web Client          │
                      │   (Sidebar / Chat Area / Artifacts)   │
                      └──────────────────┬────────────────────┘
                                         │ HTTP / JSON
                                         ▼
                      ┌───────────────────────────────────────┐
                      │          FastAPI Backend Engine       │
                      │  - Health Diagnostics & Config        │
                      │  - Session & Metadata Management      │
                      │  - Deterministic Intent Router        │
                      └─────────────┬───────────────────┬─────┘
                                    │                   │
                  SQLAlchemy / async│                   │ Embeddings / Chat
                                    ▼                   ▼
     ┌────────────────────────────────────┐       ┌────────────────────────┐
     │      PostgreSQL 16 (pgvector)      │       │     Model Providers    │
     │  - documents & chunks (768-dim)    │       │  - Ollama (Local Host) │
     │  - sessions (JSONB user_metadata)  │       │    qwen2.5:7b          │
     │  - messages & artifacts            │       │    nomic-embed-text    │
     └────────────────────────────────────┘       │  - Anthropic (Cloud)   │
                                                  └────────────────────────┘
```

---

## 2. Prerequisites & System Specifications

### Minimum Hardware Specifications
- **Operating System**: Linux (Ubuntu 22.04+), macOS (13+ Ventura / Apple Silicon), or Windows 10/11 with WSL2 / PowerShell.
- **CPU**: 4 cores minimum (8 cores recommended for CPU inference).
- **RAM**: 16 GB minimum (32 GB recommended when running local 7B models with concurrent pgvector queries).
- **Disk Space**: 15 GB free disk space (Docker container layers, PostgreSQL volume, transcripts, and Ollama model weights).
- **Software**:
  - [Docker Engine & Docker Compose v2](https://docs.docker.com/engine/install/)
  - [Ollama](https://ollama.ai/) (v0.3.0 or later)
  - Git

### Measured First-Run Benchmarks
Measured on modern workstation (Windows 11 / AMD Ryzen 9 / SSD):
- **Docker Images Build Time**: 42 seconds (Node 20 multi-stage build + Python 3.11-slim).
- **Database Initial Migration**: 1.8 seconds (Alembic automatic migration).
- **Transcript Download (`fetch_data.py`)**: 12.4 seconds (303 episode files, shallow clone).
- **Full Ingestion Pipeline**: **645.60 seconds (~10 min 45 sec)** with `nomic-embed-text` (batch size: 32) across **303 episode files, 302 valid transcripts ingested (one promo teaser excluded)**.
- **Corpus Chunk Count**: **21,994 chunks** (verified via `GET /health` reporting `vector_count: 21994`). One file (`episodes/teaser_2021/transcript.md`) is a short promo teaser for "The Room Where It Happens" without episode metadata or speaker turns and is intentionally excluded by the parser.
- **Subsequent Idempotent Ingestion**: **4.20 seconds** (all 302 documents recognized by content hash and skipped).
- **Retrieval P95 Latency**: 24 milliseconds for cosine similarity top-6 lookup across 21,994 pgvector rows.

> **Windows Git Bash / MSYS2 Path Conversion Note**:
> When running Docker Compose or test commands via Git Bash / MSYS2 on Windows, POSIX-style paths such as `/tmp` or `/data` are automatically rewritten into Windows host paths (e.g., `<user home>/AppData/Local/Temp`) by MSYS2 path translation. This causes Docker volume mounts or container-internal test paths to fail. To prevent automatic path conversion, prefix commands with `MSYS_NO_PATHCONV=1` (e.g. `MSYS_NO_PATHCONV=1 docker compose ...`), or run commands from native Windows PowerShell where no POSIX path conversion occurs.

---

## 3. Local Model Setup (Ollama)

By default, the assistant runs 100% locally using Ollama for both chat completions and embeddings.

### 1. Install & Launch Ollama
Install Ollama from [ollama.ai](https://ollama.ai). Make sure the daemon is running:
```bash
ollama serve
```

### 2. Pull Required Models
Pull the primary reasoning model and the 768-dimensional embedding model:
```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

### 3. Context Length Configuration
For optimal retrieval processing of multiple transcript passages, configure Ollama with an 8,192 token context window:
```bash
# Windows: setx OLLAMA_CONTEXT_LENGTH 8192
# Linux / macOS: export OLLAMA_CONTEXT_LENGTH=8192
```

> **Why 8192 (and NOT 16384)?**:
> On consumer GPUs with 6GB VRAM (such as the NVIDIA GeForce RTX 4050 Laptop GPU), `qwen2.5:7b` Q4_K_M model weights consume ~4.7 GB of VRAM. An 8,192 token context window requires ~1.2 GB of VRAM for the KV cache, bringing total GPU memory usage to ~5.9 GB—fitting 100% within VRAM for pure GPU inference. Setting `OLLAMA_CONTEXT_LENGTH=16384` expands the KV cache to ~2.4 GB (~7.1 GB total), exceeding the 6GB VRAM boundary and forcing Ollama to offload model layers from GPU VRAM to CPU and system RAM. This offloading triggers an immediate 5x–10x latency penalty, slowing inference from ~25 tokens/s down to 3–5 tokens/s. Therefore, `8192` is recommended consistently across all platforms.

### 4. Container-to-Host Ollama Networking
The backend runs containerized while Ollama typically runs directly on the host machine to utilize native GPU hardware acceleration:
- **Docker Desktop (macOS & Windows)**: The container connects to the host via `http://host.docker.internal:11434`. This is pre-configured out-of-the-box in `docker-compose.yml` (`extra_hosts: ["host.docker.internal:host-gateway"]`).
- **Linux Docker Engine**: On Linux, Docker containers resolve `host.docker.internal` via the `host-gateway` mapping. In addition, ensure Ollama listens on all host network interfaces:
  ```bash
  OLLAMA_HOST=0.0.0.0:11434 ollama serve
  ```
  *(Note: Linux host-gateway interface configuration is marked **[UNVERIFIED in this Windows test environment]**).*

---

## 4. Cloud Model Setup (Optional Anthropic Claude)

The application supports switching to Anthropic Claude 3.5 Sonnet for cloud-based inference while retaining local pgvector embeddings (`nomic-embed-text`).

### Exact Environment Variables
To enable Anthropic Claude, configure these exact variables in `.env`:
```env
LLM_PROVIDER=anthropic
LLM_MODEL=claude-3-5-sonnet-20241022
ANTHROPIC_API_KEY=sk-ant-api03-your-actual-api-key
```

### Graceful Startup & Error Handling
- **Graceful Startup**: If `LLM_PROVIDER=anthropic` is set but `ANTHROPIC_API_KEY` is missing, empty, or invalid, the application starts normally without crashing (`AnthropicProvider.__init__` does not raise exceptions).
- **Diagnostics via `/health`**:
  - Missing key: `GET /health` returns HTTP 200 with `status: "degraded"` and typed reason `"missing_api_key"` (accessible at `reason` and `provider.reason`).
  - Invalid key: `GET /health` tests credentials against Anthropic's model API, handles the 401 response cleanly, and returns HTTP 200 with `status: "degraded"` and typed reason `"invalid_api_key"`.
- **Chat Error Envelope**:
  - Any chat request (`POST /sessions/{id}/messages`) made with a missing or invalid Anthropic key returns a clean HTTP 502 Bad Gateway response within the standard error envelope:
    ```json
    {
      "error": {
        "code": "bad_gateway",
        "message": "Anthropic API key is not configured. Please set ANTHROPIC_API_KEY in environment.",
        "status_code": 502
      }
    }
    ```
  - Zero stack traces or internal secrets are leaked in error responses or logs.

### Testing & Evaluation Disclosure
This cloud provider path is fully implemented, verified with automated unit tests (`backend/tests/test_anthropic_provider.py`, `backend/tests/test_health.py`, `backend/tests/test_llm.py`), and verified through live fault-injection runs (with missing keys and invalid keys returning clean 502 responses). However, in accordance with the zero-cloud-budget constraint of this project, this path is **NOT tested with a valid, paid Anthropic API key**.

---

## 5. One-Command Startup (First-Run)

### Linux / macOS (Makefile)
```bash
make first-run
```
This single command:
1. Creates `.env` from `.env.example` if missing.
2. Dynamically detects remote default branch and downloads the transcripts repository into `./data/lenny-chatprd`.
3. Builds and launches `lenny-db`, `lenny-backend`, and `lenny-frontend` containers.
4. Waits for the backend and database health check to report healthy.
5. Ingests all 300+ podcast episodes into PostgreSQL pgvector.

### Windows (PowerShell)
```powershell
.\scripts\first-run.ps1
```

### Manual Step-by-Step Setup
If you prefer running commands manually without Makefile or PowerShell scripts:
1. Copy environment variables:
   ```bash
   # Windows Command Prompt:
   copy .env.example .env
   # Windows PowerShell:
   Copy-Item .env.example .env
   # Linux / macOS:
   cp .env.example .env
   ```
2. Pull required Ollama models and set context length:
   ```bash
   ollama pull qwen2.5:7b
   ollama pull nomic-embed-text
   # Recommended context length (8192 for 100% GPU VRAM fit on 6GB GPUs):
   # Windows: setx OLLAMA_CONTEXT_LENGTH 8192
   # Linux / macOS: export OLLAMA_CONTEXT_LENGTH=8192
   ```
3. Fetch transcript dataset:
   ```bash
   python scripts/fetch_data.py
   ```
4. Build and start containers:
   ```bash
   docker compose up -d --build
   ```
5. Ingest transcript corpus into pgvector:
   ```bash
   docker compose exec backend python -m scripts.ingest
   ```

Once completed, open your browser:
- **Frontend Web UI**: http://localhost:3000
- **Backend Health Check**: http://localhost:8000/health
- **Interactive Swagger Docs**: http://localhost:8000/docs

---

## 6. Daily Run Commands

| Task | Make Target | Direct Command |
|---|---|---|
| Start services | `make up` | `docker compose up -d` |
| Stop services | `make down` | `docker compose down` |
| View service logs | — | `docker compose logs -f backend` |
| Re-run ingestion | `make ingest` | `docker compose exec -T backend python -m scripts.ingest` |
| Run backend tests | `make test-backend` | `docker compose exec -T backend pytest` |
| Run frontend tests | `make test-frontend` | `cd frontend && npm test` |

---

## 7. Environment Variables Reference

| Variable | Requirement | Default | Purpose |
|---|---|---|---|
| `LLM_PROVIDER` | Required | `ollama` | Selected LLM backend (`ollama` or `anthropic`). |
| `LLM_MODEL` | Required | `qwen2.5:7b` | Chat model identifier. |
| `OLLAMA_BASE_URL` | Required (if Ollama) | `http://host.docker.internal:11434` | Ollama service endpoint accessible from container. |
| `EMBEDDING_MODEL` | Required | `nomic-embed-text` | Embedding model identifier in Ollama. |
| `EMBEDDING_DIM` | Required | `768` | Vector dimension matching model and pgvector schema. |
| `DATABASE_URL` | Required | `postgresql+psycopg://postgres:localdev@db:5432/lenny_assistant` | SQLAlchemy async database connection URI. |
| `ANTHROPIC_API_KEY` | Optional | *(empty)* | Anthropic API key (required only when `LLM_PROVIDER=anthropic`). |
| `RETRIEVAL_TOP_K` | Optional | `6` | Maximum number of chunks returned per RAG query. |
| `RETRIEVAL_MIN_SCORE`| Optional | `0.62` | Empirically calibrated cosine similarity threshold. |
| `HISTORY_TURNS` | Optional | `6` | Conversational history window for query contextualization. |
| `AGENT_TIMEOUT_S` | Optional | `120` | Maximum agent execution timeout in seconds before degraded fallback. |
| `ESSAY_TIMEOUT_S` | Optional | `420` | Extended timeout in seconds for multi-section Ship 30 essay generation. |
| `ARTIFACT_MAX_BYTES`| Optional | `200000` | Security size guard for generated HTML/Markdown artifacts. |
| `DATA_DIR` | Required | `/data` | Read-only path where transcripts are mounted in container. |
| `BACKEND_PORT` | Optional | `8000` | Host port mapped to FastAPI backend. |
| `FRONTEND_PORT` | Optional | `3000` | Host port mapped to React frontend. |
| `VITE_API_BASE_URL`| Optional | `http://localhost:8000` | API base URL baked into frontend build. |

*Note: PostgreSQL is **not** published to the host port by default (`127.0.0.1:5432` is commented out) to prevent host port collisions. Backend connects over the internal Docker network.*

### Host Port Configuration
Host ports are fully configurable via `.env`:
- `BACKEND_PORT`: Host port mapping for the FastAPI backend (default: `8000`).
- `FRONTEND_PORT`: Host port mapping for the Vite React frontend (default: `3000`).

To avoid port collisions or manual configuration desynchronization when overriding `BACKEND_PORT`:
1. `docker-compose.yml` dynamically evaluates `VITE_API_BASE_URL: ${VITE_API_BASE_URL:-http://localhost:${BACKEND_PORT:-8000}}` for both frontend build args and container environment variables. When `BACKEND_PORT` is overridden (e.g. `BACKEND_PORT=8001`), the frontend automatically points to `http://localhost:8001` without requiring manual edits to `VITE_API_BASE_URL`.
2. `scripts/first-run.ps1` dynamically parses `BACKEND_PORT` and `FRONTEND_PORT` from `.env`, polls `http://localhost:$backendPort/health` during startup, and displays the correct active URLs upon completion.
3. `Makefile` includes `.env` and exports `BACKEND_PORT` and `FRONTEND_PORT` (defaulting to 8000/3000), ensuring printed endpoints match active host bindings.

---

## 8. Fallback Behavior & Degradation Modes

The system is strictly designed with predictable degradation and zero silent switching:

1. **System Never Silently Switches Providers**:
   If `LLM_PROVIDER=ollama` is configured and Ollama fails, the application **never** attempts to silently fallback to Anthropic (which could leak user queries or incur unbudgeted API fees). The system reports `502 Bad Gateway` with error code `llm_unavailable`.
2. **Ollama Down / Unreachable**:
   - `/health` endpoint returns HTTP 200 with `status: "degraded"` and `ollama.reachable: false`.
   - Frontend displays amber warning status dot in the header.
   - User queries receive a clear, friendly error banner: *"Ollama local LLM is unavailable. Please verify Ollama is running with qwen2.5:7b."*
3. **Empty Knowledge Base / Ingestion Not Run**:
   - The backend does **not** crash if the database has 0 chunks.
   - `/health` explicitly reports `ingested: false`.
   - The frontend UI displays an informational banner alerting the user that transcripts have not been ingested and provides the exact command (`make ingest`).
4. **Missing or Invalid Cloud API Key**:
   - When `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` is empty or invalid, the backend immediately fails fast with a structured validation error `401 Unauthorized` / `invalid_api_key`.
5. **Model Timeout / Long Inference**:
   - Configurable timeout via `AGENT_TIMEOUT_S` (default: 120s). If the local model stalls, the request terminates with `504 Gateway Timeout` (`agent_timeout`) and a retry prompt is displayed to the user.

---

## 9. Troubleshooting Guide

### 1. `Cannot connect to Ollama at http://host.docker.internal:11434`
- **Cause**: Ollama is not running on host or Docker cannot reach host IP.
- **Fix**:
  1. Verify Ollama is running: run `ollama list` in host terminal.
  2. If on Linux, ensure Ollama is listening on all interfaces: `OLLAMA_HOST=0.0.0.0:11434 ollama serve`.
  3. Verify `curl http://localhost:11434/api/tags` returns HTTP 200 from host.

### 2. `Embedding model 'nomic-embed-text' not found`
- **Cause**: The embedding model was not pulled before ingestion.
- **Fix**: Run `ollama pull nomic-embed-text` on the host, then run `make ingest`.

### 3. Port Conflicts (`8000` or `3000` already in use)
- **Cause**: Another local service is using port 8000 or 3000.
- **Fix**: Update `BACKEND_PORT=8001` or `FRONTEND_PORT=3001` in `.env` and rerun `docker compose up -d`. `docker-compose.yml` automatically forwards the new backend port to `VITE_API_BASE_URL` without requiring manual frontend changes.

### 4. Database Connection Refused
- **Cause**: `lenny-db` container is still initializing or volume permissions error.
- **Fix**: Check `docker compose logs db`. Ensure healthy status via `docker compose ps`.

---

## 10. Documentation & Deliverables

All core architectural, security, and project specifications live under `docs/` and `playbook/`:

| Document | Purpose |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | Product Requirements Document, user journeys, assumptions, and out-of-scope boundaries. |
| [`docs/architecture.md`](docs/architecture.md) | Technical architecture, database schema, API contracts, deterministic router, and fallback matrices. |
| [`docs/design.md`](docs/design.md) | UI/UX design specification, design tokens, Information Architecture, and Design Decisions table. |
| [`docs/security.md`](docs/security.md) | Threat model (T1–T12), sandboxed iframe CSP specification, input sanitization, and prompt injection defense. |
| [`docs/DATA_NOTES.md`](docs/DATA_NOTES.md) | Transcript corpus audit, schema inspection, speaker-turn parsing rules, and retrieval calibration. |
| [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md) | Automated test strategy and manual browser-based verification checklist (M1–M11). |
| [`docs/BRIEF_COMPLIANCE.md`](docs/BRIEF_COMPLIANCE.md) | Exhaustive compliance matrix auditing every brief requirement with empirical evidence and known gaps. |
| [`transcripts/README.md`](transcripts/README.md) | Index of real agent execution transcripts, failed spikes, diagnostic traces, and codebase fixes. |
| [`playbook/START_HERE.md`](playbook/START_HERE.md) | Candidate implementation playbook and step-by-step developer guidelines. |
| [`playbook/PROMPTS.md`](playbook/PROMPTS.md) | Complete sequential engineering prompts and verification recipes (P1–P13). |

---

## 11. Known Limitations and Technical Debt

1. **Module File Sizes (`chat.py` & `verify.py`)**:
   - `backend/app/routers/chat.py` (956 lines) and `backend/app/agent/verify.py` (865 lines) exceed the ~300-line general guideline in `SPEC.md`.
   - **Rationale**: Kept intentionally cohesive to ensure the end-to-end multi-turn conversation lifecycle (intent classification, query rewriting, retrieval gating, SDK orchestration, citation verification, and DB persistence) and the citation verification/repair engine remain traceable within unified domains rather than artificially fragmented across multiple shallow files.
2. **Essay Generation Latency on 6GB GPUs**:
   - Generating a full Ship 30 essay using the local `qwen2.5:7b` model on a 6GB GPU (RTX 4050) takes between **120 and 250 seconds** due to generating five sequential sections (headline, lead-in, core tenets, counter-intuitive insight, and conclusion) with local FP16/Q4 compute limits. The timeout is explicitly governed by `ESSAY_TIMEOUT_S=420` in `.env`.
3. **Cloud Provider Testing with Live API Key**:
   - The `AnthropicProvider` (Claude 3.5 Sonnet) is fully implemented and validated with automated unit tests (`backend/tests/test_anthropic_provider.py`) and live fault injection (testing graceful startup and clean HTTP 502 responses with missing and invalid keys). However, due to the strict zero-cloud-budget constraint of this project, it has not been tested with an active paid Anthropic API key.
4. **7B Local Model Faithfulness Mitigations**:
   - Small local 7B models can occasionally reverse causal statements (e.g., claiming retention drives activation instead of activation driving retention) or hallucinate citations if asked open-ended questions.
   - **Mitigations Employed**:
     - Pre-retrieval cosine similarity gating (`RETRIEVAL_MIN_SCORE=0.62` floor) to return immediate canonical refusal with 0 LLM calls on out-of-domain queries.
     - Directional system prompts enforcing anti-reversal constraints ("state relationships exactly as the source states them") and mandatory `[S#]` claim tags.
     - Automated citation verification (`verify.py`) cross-referencing `[S#]` tags against database chunk rows, stripping invalid citations, and triggering automatic retry if zero valid citations are found.

