# WORK SPLIT — who builds what, in what order

Today is Sat 10 Oct. Deadline: Mon 12 Oct end of day. You have today, Sunday, and Monday morning. Aim to submit Monday by early afternoon.

## The rule
- **Antigravity = volume work** (scaffolding, UI, Docker, boilerplate, tests, doc syncing). Use it first and for most tasks.
- **Claude Code = the hard, risky parts** where quality matters and re-work is expensive (ingestion/citations, agent orchestrator, Ship 30 skill, security review, final audit). Your usage limit is small, so you only spend it on these 5 sessions.
- **You = decisions and proof.** You run every verify step, read every diff, commit after each task, and save transcripts.

I can't see Antigravity's current model choices or quotas. If it lets you pick a model, pick the strongest available for P3/P4 style work only if you choose to try them there, and keep Claude Code for the ones marked CC.

## Task table
| ID | Task | Tool | Est. | Why this tool |
|---|---|---|---|---|
| P0 | Session starter (paste at the start of every new session) | both | 2 min | Gives context cheaply |
| P1 | Scaffold: backend, frontend, Docker Compose, config, logging, /health | Antigravity | 45 min | Boilerplate |
| P2 | Alembic schema + sessions/messages API + tests | Antigravity | 45 min | Standard CRUD |
| P3 | Data inspection + ingestion + chunking + embeddings + retrieval | **Claude Code** | 60–90 min | Core quality; real data format unknown |
| P4 | Intent router + agent orchestrator + grounding + citation verifier + fallback | **Claude Code** | 90 min | Heart of the system; spike lessons apply |
| P5 | Chat UI, sessions UI, model badge, states | Antigravity | 60 min | UI volume |
| P6 | Ship 30 skill (rules file + pipeline + validator) | **Claude Code** | 60 min | Needs care with a 7B model |
| P7 | Artifact panel + sandbox viewer | Antigravity | 45 min | Spec is exact |
| P8 | Security review + adversarial tests + fixes | **Claude Code** | 45 min | Second pair of eyes on risky code |
| P9 | Ops hardening: resilience, logs, health, compose healthchecks | Antigravity | 45 min | Mechanical |
| P10 | Tests + manual UI test plan | Antigravity | 45 min | Volume |
| P11 | Eval questions + eval script + EVAL_RESULTS | Antigravity | 45 min | You review the questions |
| P12 | Sync README/architecture/design with real code | Antigravity | 45 min | Doc volume |
| P13 | Final audit: fresh-clone simulation, secrets scan, deliverables checklist | **Claude Code** | 30 min | Independent check |
| PX | Interview-prep explainer (run after every phase) | Antigravity | 10 min each | Makes you able to defend the code |

## Schedule
**Saturday (today):** Phase 0 setup → P1 → P2 → P3 → P4 → P5. If P4 works end-to-end with the UI before bed, you are ahead.
**Sunday:** P6 → P7 → P8 → P9 → P10 → P11 → edit PRD ✏️ items → P12.
**Monday morning:** P13 → fix punch list → fresh-clone test → record video → upload → submit before noon-ish.
**If you fall behind (cut in this order):** UI polish → extra tests → streaming → cloud provider testing. Never cut PRD, cited RAG, Ship 30 skill, sandbox, README, video.

## The loop for every task (do not skip)
1. Open the tool on the repo folder. Start a NEW session per task (saves tokens, keeps context clean).
2. Paste P0, then the task prompt (from PROMPTS.md). Let it plan and work. If it asks a question, answer in one line.
3. Run the "You verify" checklist from the prompt. Paste failures back; do not proceed with red tests.
4. Read the diff summary. Open the 2–3 most important files and read them.
5. Commit: `git add . && git commit -m "<message from prompt>"`.
6. Save the transcript (below). Keep failures.
7. Every phase boundary (after P2, P4, P7, P10): run PX and skim the answers.

## Guardrails (these protect you in the interview)
- **You must be able to explain** the router rules, why retrieval is forced in code, the chunking choice, the citation verifier, and the sandbox attributes. If you cannot, run PX and read until you can.
- **Do not let the tool change the architecture.** The prompts say: if SPEC conflicts with reality, stop and report.
- **Do not trust "done".** Only trust commands you ran yourself.
- **Never paste real keys into a tool.** You don't have any; keep it that way.
- **Don't let docs claim untested features.** Anthropic provider stays marked UNTESTED.

## Saving agent transcripts (deliverable #6)
- Create `transcripts/` in the repo.
- **Claude Code:** sessions are saved locally as JSONL under your user folder, `C:\Users\Justin\.claude\projects\...` (the path appeared in your SDK output as `memory_paths`). Copy the relevant `.jsonl` files into `transcripts/claude-code/`. Your spike sessions are already there, including the failed run — keep them.
- **Antigravity:** export or copy each conversation into `transcripts/antigravity/P#-name.md` (copy-paste the chat if there's no export; screenshots as a last resort). I can't verify its export feature from here.
- Also keep `spike/SPIKE_LOG.md`.
- Before committing: search the files for `key`, `token`, `password`, your Windows username in paths if you want it hidden, and remove. The dummy `ollama` token is fine.

## Phase 0 — do this first (20 minutes, by hand)
1. Unzip the kit and copy its contents into `C:\Users\Justin\The Global Projects Folder\lenny-assistant\` (so `SPEC.md`, `CLAUDE.md`, `AGENTS.md`, `docs\`, `playbook\` sit next to `spike\`).
2. Make sure `.gitignore` in the repo root contains:
   ```
   .venv/
   __pycache__/
   .env
   node_modules/
   data/
   notes/
   *.pyc
   ```
3. Clone the data (from the repo root):
   ```
   mkdir data
   git clone --depth 1 https://github.com/LennysNewsletter/lennys-newsletterpodcastdata data\lenny-source
   dir data\lenny-source
   ```
   If "repository not found", find the exact link in the original email.
4. Start the database and verify pgvector:
   ```
   docker --version
   docker run -d --name lenny-db -e POSTGRES_PASSWORD=localdev -e POSTGRES_DB=lenny_assistant -p 5432:5432 pgvector/pgvector:pg16
   docker exec -it lenny-db psql -U postgres -d lenny_assistant -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extversion FROM pg_extension WHERE extname='vector';"
   ```
   (P1's Compose file will replace this container later: run `docker rm -f lenny-db` before the first `docker compose up`.)
5. Make sure Ollama is running with the context raised (`OLLAMA_CONTEXT_LENGTH` was set earlier) and models pulled: `ollama list` shows `qwen2.5:7b`, `nomic-embed-text`.
6. Create folders: `mkdir transcripts notes eval`
7. Commit: `git add . && git commit -m "chore: add spec, docs, playbook"`

Then open Antigravity on the repo folder and start with P1.
