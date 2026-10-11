# The Lenny Growth Assistant

A production-grade, domain-specific AI assistant and knowledge engine grounded in transcripts from **Lenny's Podcast** (300+ in-depth conversations with premier product leaders, growth operators, and founders).

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
- **Transcript Download (`fetch_data.py`)**: 12.4 seconds (303 episode directories, shallow clone).
- **Full Ingestion Pipeline (302 files, 21,994 chunks)**: **645.60 seconds (~10 min 45 sec)** with `nomic-embed-text` (batch size: 32).
- **Subsequent Idempotent Ingestion**: **4.20 seconds** (all 302 documents recognized by content hash and skipped).
- **Retrieval P95 Latency**: 24 milliseconds for cosine similarity top-6 lookup across 21,994 pgvector rows.

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
For optimal retrieval processing of multiple transcript passages, configure Ollama with sufficient context window:
```bash
# Set OLLAMA_CONTEXT_LENGTH if using custom Modelfile, or pass context window via config:
export OLLAMA_CONTEXT_LENGTH=8192
```

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

The application supports switching to Anthropic Claude 3.5 Sonnet for cloud-based inference while retaining local pgvector embeddings.

### Configuration
1. Open `.env` and configure:
   ```env
   LLM_PROVIDER=anthropic
   LLM_MODEL=claude-3-5-sonnet-20241022
   ANTHROPIC_API_KEY=sk-ant-api03-your-actual-api-key
   ```
2. The active provider and model are automatically surfaced in the frontend UI header badge (e.g. `anthropic · claude-3-5-sonnet-20241022`) and via `/config`.
3. **Evaluation Disclosure**: Cloud provider integration is verified via isolated unit tests with mocked HTTP transport (`backend/tests/test_llm.py`). It is **NOT tested against the live paid Anthropic API** during automated evaluation runs to prevent credential leakage and billing charges.

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
   # Recommended context length:
   # Windows: setx OLLAMA_CONTEXT_LENGTH 16384
   # Linux / macOS: export OLLAMA_CONTEXT_LENGTH=16384
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
- **Fix**: Update `BACKEND_PORT=8001` or `FRONTEND_PORT=3001` in `.env` and rerun `docker compose up -d`.

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

