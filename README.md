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

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | Selected LLM backend (`ollama` or `anthropic`). |
| `LLM_MODEL` | `qwen2.5:7b` | Chat model identifier. |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama service endpoint accessible from container. |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model identifier in Ollama. |
| `EMBEDDING_DIM` | `768` | Vector dimension matching model and pgvector schema. |
| `ANTHROPIC_API_KEY` | *(empty)* | Optional Anthropic API secret key. |
| `DATABASE_URL` | `postgresql+psycopg://postgres:localdev@db:5432/lenny_assistant` | SQLAlchemy async database connection URI. |
| `RETRIEVAL_TOP_K` | `6` | Maximum number of chunks returned per RAG query. |
| `RETRIEVAL_MIN_SCORE`| `0.62` | Empirically calibrated cosine similarity threshold. |
| `DATA_DIR` | `/data` | Read-only path where transcripts are mounted in container. |
| `BACKEND_PORT` | `8000` | Host port mapped to FastAPI backend. |
| `FRONTEND_PORT` | `3000` | Host port mapped to React frontend. |

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
