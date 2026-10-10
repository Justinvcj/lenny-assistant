# START HERE (Antigravity-only plan)

Read this whole file once, top to bottom. Nothing in it assumes you know a term I haven't explained.

## 1. What this kit is
Your project is built by an AI coding tool (Antigravity) that you direct. You do not write the code from scratch. You:
1. paste a **prompt** (a block of instructions) into Antigravity,
2. let it work,
3. **run a short check** to prove it works,
4. **save your progress** with git,
5. move to the next prompt.

## 2. What "P0, P1, P2 ..." mean
"P" = **Prompt**. They are numbered in the order you use them. All of them live in ONE file next to this one: **`PROMPTS.md`**. Open it. Each prompt has a heading (like `## P1 — Scaffold`) and the text you copy is inside the **grey code box** under the heading.
Letters after a number (P3a, P3b, P3c) are parts of one job. You paste them one after another **in the same chat**, checking after each part.

## 3. Phase 0 — one-time setup by hand (about 20 minutes)
Do these in Command Prompt, in order.

1. Unzip `lenny-kit.zip`. Copy everything inside the `lenny-kit` folder into the **root** of your project:
   `C:\Users\Justin\The Global Projects Folder\lenny-assistant\`
   After this, `SPEC.md`, `docs\` and `playbook\` sit next to your `spike\` folder. (Do not overwrite anything of yours; `KIT_README.md` is just a note, you can delete it.)
2. Open the file `.gitignore` in the project root (create it if missing) and make sure it contains these lines:
   ```
   .venv/
   __pycache__/
   .env
   node_modules/
   data/
   notes/
   *.pyc
   ```
3. Download the transcripts:
   ```
   cd "C:\Users\Justin\The Global Projects Folder\lenny-assistant"
   mkdir data
   git clone --depth 1 https://github.com/LennysNewsletter/lennys-newsletterpodcastdata data\lenny-source
   dir data\lenny-source
   ```
   If it says "repository not found", find the real link in the original assignment email and use that.
4. Check Docker is installed: `docker --version`. If not found, install Docker Desktop for Windows, restart the PC, open Docker Desktop once, and try again.
5. Start the database and prove it works:
   ```
   docker run -d --name lenny-db -e POSTGRES_PASSWORD=localdev -e POSTGRES_DB=lenny_assistant -p 5432:5432 pgvector/pgvector:pg16
   docker exec -it lenny-db psql -U postgres -d lenny_assistant -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extversion FROM pg_extension WHERE extname='vector';"
   ```
   You should see a version number. (Prompt P1 will replace this container; before your first `docker compose up` run `docker rm -f lenny-db`.)
6. Check Ollama has your models: `ollama list` must show `qwen2.5:7b` and `nomic-embed-text`. Also make sure the context setting from earlier is in place: `setx OLLAMA_CONTEXT_LENGTH 16384`, then quit and reopen Ollama.
7. Make folders and save: 
   ```
   mkdir transcripts notes eval
   git add .
   git commit -m "chore: add spec, docs, playbook"
   ```
8. Open **Antigravity**, choose "open folder", and pick `lenny-assistant`.

## 4. The loop you repeat for every prompt
1. Start a **NEW chat/session** in Antigravity (one per prompt, except parts a/b/c/d stay in one chat).
2. Paste **P0** (always first in a new chat) and send. Read its reply. If it lists conflicts, tell it to follow SPEC.md.
3. Paste the task prompt (P1, P2, ...) and send. Let it work. If it asks a question, answer in one line. If it asks permission to run a command, allow it (you can read the command first).
4. Do the **"You verify"** list printed under that prompt in `PROMPTS.md`. These are commands you run yourself. **Only believe what you ran.**
5. If something fails, paste the exact error into the chat and say: "Fix this. Show me the cause first." (Or use the rescue prompts S1–S3 at the end of `PROMPTS.md`.)
6. When it works, save progress: `git add .` then `git commit -m "<message printed under the prompt>"`.
7. Save the chat as a transcript (section 7 below).

Settings note: I can't see your version of Antigravity. If it offers a "planning" mode and a choice of model, use planning mode and the strongest model offered for P3 and P4.

## 5. Order, with what each prompt builds
| Step | Prompt | Builds | Time | Done when |
|---|---|---|---|---|
| 1 | P1 | Empty skeleton: backend, frontend, Docker, health page | 45 min | `docker compose up --build` works, health page opens |
| 2 | P2 | Database tables, sessions API, tests | 45 min | tests pass, you can create a session |
| 3 | P3a, P3b, P3c | Loads and searches the transcripts | 90 min | ingestion runs, search results make sense |
| 4 | P4a, P4b, P4c, P4d | The brain: router, agent, citations, chat endpoint | 2 hrs | a question returns a cited answer, a cooking question is refused |
| 5 | PX | Explains steps 1–4 to you (interview prep) | 15 min | you read it |
| 6 | P5 | Chat screen | 60 min | you can chat in the browser |
| 7 | P6a, P6b | Ship 30 essay writer | 75 min | "turn that into an essay" works |
| 8 | P7 | Safe preview panel for generated pages | 45 min | HTML renders safely |
| 9 | P8 | Security self-review and tests | 45 min | tests pass, table of results |
| 10 | P9 | Error handling, logging, README | 45 min | stopping Ollama gives a friendly error |
| 11 | P10 | Test suite and manual test plan | 45 min | tests green, plan filled |
| 12 | P11 | Evaluation script and results | 45 min | EVAL_RESULTS.md exists |
| 13 | P12 | Docs match the code | 45 min | discrepancy table reviewed |
| 14 | P13 | Final "pretend I'm the evaluator" audit | 30 min | punch list done |
| 15 | You | Edit the PRD (✏️ marks), record video, submit | 2 hrs | submitted |

## 6. Schedule (today is Saturday 10 Oct; deadline Monday 12 Oct, end of day)
- **Saturday:** Phase 0, P1, P2, P3, P4, PX.
- **Sunday:** P5, P6, P7, P8, P9, then edit the PRD in the evening (30–45 min).
- **Monday morning:** P10, P11, P12, P13, fix the punch list, fresh-clone test, record video, submit by early afternoon.
- **If behind, cut in this order:** P11 (shrink to 10 questions) → P10 extras → UI polish. **Never cut:** P3, P4, P6, P7, README, PRD, video.
- If Antigravity's usage runs out, tell me where you are; we switch to Claude Code for that prompt.

## 7. Saving transcripts (a required deliverable, failures included)
Create `transcripts\antigravity\` in the project. After each prompt, copy the chat text into a file like `transcripts\antigravity\P3-ingestion.md` (export if Antigravity has an export option; I can't confirm it does, so copy-paste works). Keep the failed attempts and the fixes. Your earlier spike logs (`spike\SPIKE_LOG.md`) also count. Before committing, search the transcripts for any key/password text and delete it. The dummy word `ollama` used as a token is fine.

## 8. Rules to protect you in interviews
- Read the main files the tool writes. After P4 and P6 you must be able to explain, in your own words: why retrieval runs in code, what the router does, how citations are checked, and what the sandbox blocks.
- Do not let it change the plan. The prompts tell it to stop and report if reality disagrees with `SPEC.md`.
- Anything not tested stays marked **UNTESTED** (for example the cloud model option).

## 9. Claude Code later
When Antigravity is done (or you hit a problem it can't fix), we bring Claude Code back for three review jobs: review of P3/P4, a second security review, and the final audit. Their prompts are at the end of `PROMPTS.md` under "LATER".
