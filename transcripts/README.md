# Agent Transcripts & Failure Post-Mortem

This directory contains empirical agent execution transcripts recorded during the development and hardening of the Lenny Growth Assistant. Each transcript captures real model behavior against local Ollama (`qwen2.5:7b`), documenting specific failure modes, diagnostic findings, and how they were systematically corrected in the production codebase.

---

## Index of Saved Transcripts

| Transcript File | Phase / Context | Primary Failure Observed | Codebase Resolution |
|-----------------|-----------------|--------------------------|---------------------|
| [`01_spike_builtin_tools_failure.log`](file:///c:/Users/Justin/The%20Global%20Projects%20Folder/lenny-assistant/transcripts/01_spike_builtin_tools_failure.log) | Phase 4 Spike (Agent SDK Initial Setup) | Context bloat (21,690 tokens), tool confusion (`ScheduleWakeup`, `Skill`), turn exhaustion (`error_max_turns`), latency timeout (56.3s). | Explicit runtime lockdown: `builtin_tools=[]`, isolated empty temporary `cwd`, zero host tool exposure. |
| [`02_spike_locked_tools_success.log`](file:///c:/Users/Justin/The%20Global%20Projects%20Folder/lenny-assistant/transcripts/02_spike_locked_tools_success.log) | Phase 4 Spike (Tool Lockdown Verification) | Baseline comparison: verified tool invocation after removing default built-ins. | Context dropped to 384 tokens (98.2% reduction); latency dropped to 15.2s with 100% clean tool execution. |
| [`03_spike_reliability_claim_reversals.log`](file:///c:/Users/Justin/The%20Global%20Projects%20Folder/lenny-assistant/transcripts/03_spike_reliability_claim_reversals.log) | Phase 4 Spike (Multi-turn Reliability Suite) | Semantic claim reversal (causal inversion: "activation driven by retention") and stochastic tool calling on out-of-domain queries. | Deterministic code-level retrieval before LLM invocation + directional prompt constraint ("Never reverse cause and effect"). |

---

## Detailed Post-Mortem per Transcript

### 1. `01_spike_builtin_tools_failure.log` — Default Agent SDK Built-in Tools Explosion

#### Context & Setup
During initial integration of the Claude Agent SDK (`claude_code_version 2.1.294`) with local Ollama (`qwen2.5:7b`), the SDK was instantiated with default settings while registering a single in-process MCP tool (`mcp__lenny__search_transcripts`).

#### What Failed
1. **Severe Context Bloat**: The SDK injected 26 built-in host operating system tools into the system prompt (`Task`, `Bash`, `CronCreate`, `Edit`, `Glob`, `Grep`, `PowerShell`, `WebFetch`, `Write`, etc.), inflating the prompt from ~380 tokens to **21,690 input tokens**.
2. **Tool Hallucination & Confusion**: The local 7B model was overwhelmed by the 27 available tools. Instead of calling `mcp__lenny__search_transcripts`, it hallucinated background tasks:
   - Call 1: `ScheduleWakeup(delaySeconds=1200, prompt='/loop review changes')`
   - Call 2: `Skill(skill='code_review', args='check_pull_request_12345')` (failed: unknown skill)
   - Call 3: `Workflow(script='format_document...')` (failed: permission denied)
3. **Execution Failure**: The agent hit `error_max_turns` (reached turn limit of 4) after **55.18 seconds** without answering the user query.
4. **Security Risk**: Exposing `Bash` and `PowerShell` tools created an immediate Remote Code Execution (RCE) vector.

#### How It Was Corrected
- In `backend/app/agent/orchestrator.py`:
  - Enforced `builtin_tools = []` to strip all default host tools before the model ever sees them.
  - Configured agent `cwd` to an isolated, empty temporary directory (`tempfile.TemporaryDirectory()`).
  - Restricted exposed tools strictly to intent-specific MCP tools (`QA`: `search_transcripts`; `ESSAY`: `generate_ship30_essay`; `ARTIFACT`: `create_artifact`).

---

### 2. `02_spike_locked_tools_success.log` — Lockdown Verification

#### Context & Setup
Re-running the exact same query (`"activation first week podcast"`) immediately following the tool lockdown fix.

#### What Succeeded
- **Prompt Token Reduction**: Input prompt plummeted from 21,690 tokens to **384 tokens** (a **98.2% reduction**).
- **Tool Precision**: The model called `mcp__lenny__search_transcripts` on turn 1 with `query='activation first week podcast'`.
- **Latency & Reliability**: Completed in **15.2 seconds** (14,087 ms API duration) with zero permission errors and zero retries.

---

### 3. `03_spike_reliability_claim_reversals.log` — Claim Inversion & Stochastic Tool Skipping

#### Context & Setup
A 25-turn reliability battery (5 repeated runs across 3 domain queries and 2 off-topic queries) evaluating `qwen2.5:7b` tool invocation rate, citation faithfulness, and out-of-domain refusals.

#### What Failed
1. **Claim Reversal (Causal Inversion)**:
   - The source transcript (Episode 12, Guest A) states: *"Retention is driven by activation within the first week."*
   - In Run 1 and Run 2, the model output:
     > *"Activation within the first week is driven by retention, according to the information from Episode 12 (Guest A)."*
   - The citation was accurate (Episode 12 was indeed referenced), but the causal claim was backwards. A naive automated test checking only citation existence would have falsely passed this turn.
2. **Stochastic Tool Skipping on Off-Domain Queries**:
   - For `"How do I bake sourdough bread?"`, the model skipped tool calling 3 out of 5 times (runs 3, 4, 5), answering from pre-training memory instead of consulting the index.

#### How It Was Corrected
1. **Directional Anti-Reversal Constraint**:
   - Added an explicit rule in `backend/app/agent/prompts.py`:
     > *"State relationships exactly as the source states them. Never reverse cause and effect."*
   - Added automated prompt regression verification in `eval/eval_e2e.py`.
2. **Deterministic Pre-LLM Retrieval Architecture**:
   - Rather than allowing the LLM to choose whether or not to retrieve, `backend/app/routers/chat.py` executes vector retrieval deterministically in Python application code before invoking the model.
   - If the top chunk cosine similarity falls below `RETRIEVAL_MIN_SCORE` (`0.62`), the system refuses immediately without making any LLM call (<15 ms latency, 0 tokens wasted).
   - If above threshold, sources are formatted in `<source id="S#">` blocks.
3. **Database-Backed Citation Resolution & Retry Loop**:
   - Citations are parsed via regex (`[S#]`) and resolved directly against PostgreSQL records in `backend/app/agent/verify.py` (preventing hallucinated quotations).
   - If an answer lacks valid citations, a 1-turn retry with an explicit grounding reminder triggers automatically. If that fails, the answer is replaced with the exact refusal string.
