# Lenny Growth Assistant: Product Requirements Document

**Author:** Justin · **Date:** 12 October 2026 · **For:** Oogway Labs, Forward Deployed Engineer take-home

---

## The short version

I built a chat assistant that answers product and growth questions from Lenny Rachitsky's podcast transcripts. It shows exactly where each answer came from, and when it can't ground an answer it says "I don't have information about that in the transcripts." It can also turn an answer into a Ship 30 for 30 style essay or a one-page HTML or Markdown document, which opens in a sandboxed viewer next to the chat.

It runs entirely on my laptop with a local model (Qwen 2.5 7B through Ollama), and a stranger can start it from a clean clone using only the README.

What works well: retrieval, citations, refusals, error handling and the start-up experience. What is weaker, and I say so throughout this document: a small model sometimes makes claims its sources don't support, essays are slow and only loosely grounded, and very short follow-ups such as "Why is that?" are answered in about two runs out of three.

---

## 1. The person and the problem

A product or growth lead keeps going back to Lenny's podcast for advice: how top teams define activation, when to change pricing, what a growth loop really is. The advice is in there somewhere, spread over about 300 episodes. The problem isn't a shortage of advice. It's the hour spent finding the right episode and the right moment, and remembering who said it. When the answer comes from memory, or from a chatbot, it loses its source.

This person needs an answer in minutes that they can defend in a meeting: what was said, by whom, in which episode, and the exact passage. If the transcripts don't cover the question, they need to hear that too. A confident wrong answer is worse than no answer, because it spends the trust the tool depends on. So the product is about **trust more than coverage**.

There is a second user: a team lead or content owner who wants a first draft of an essay or a one-pager built from real passages, and who must be able to check it. I treat generated writing as a draft for a person to edit, never something to publish.

---

## 2. What "good" means, and what I measured

I set targets before building. The measured column is what I actually observed on my laptop (RTX 4050 6 GB, 16 GB RAM, `qwen2.5:7b` through Ollama), with the sample size. Where I did not measure something properly, the table says so.

| # | What I wanted | Target | What I measured |
|---|---|---|---|
| M1 | Every grounded answer carries at least one citation that resolves to a real passage, built from database rows and never from model text | 100% | 10 of 10 in-scope answers in one live run, and 4 of 4 follow-ups in another, each with 1 to 6 valid citations |
| M2 | Clearly unrelated questions are refused without calling the model | 100% | 8 of 8 refused in 0.2 to 0.3 s with no model call. Plausible-but-absent topics rely on the prompt, and I did **not** measure them on a labeled set |
| M3 | Claims are faithful to the passage they cite | at least 85% | **Not measured on a labeled set.** My evidence is weaker: a spike with a stub scored 12 of 15 (80%), and an audit of generated essays found one fabricated quote and one paraphrase presented as verbatim |
| M4 | Time to a grounded answer, with progress shown | p50 up to 30 s, p95 up to 60 s | p50 13 to 25 s and p95 38 to 53 s across three live runs (n = 6, 8, 12). Refusals took 0.0 to 0.3 s. HTML and Markdown artifacts took about 0.1 s because code builds them. Essays took 155 to 328 s |
| M5 | A Ship 30 essay with a headline, specific headings, only `[S#]` citations, no duplicated paragraphs, no unverified quote, and a length near 1,250 words | all checks pass | Latest runs: 1,119 and 1,122 body words, 0 duplicate paragraphs, only `[S#]` citations, and no direct quote shipped (unverified quotes are deleted before saving; earlier runs shipped 1 to 2). Headings were the weakest part: placeholder titles such as "Angle 2 on pricing strategy" and sentence fragments appeared in live runs, and the final build rejects those, retries once and falls back to fixed labels. The validator's support score was low (12.5% and 18.5%). The score counts overlapping words and may under-count paraphrase, but I treat essays as drafts |
| M6 | A new person can run it from the README | passes | Verified from a clean GitHub clone: clone 2 s, data fetch 12 s, image build 85 s, start 12 s, 10-episode ingestion 20 s, first cited answer 36 s. A full ingestion of 302 episodes takes about 11 minutes; I did not repeat it in the audit |
| M7 | The knowledge base is complete and safe to re-run | no gaps | 302 documents, 21,994 chunks (about 73 per episode), 0 missing embeddings, vector index present. A second ingestion run skipped all 302 documents in about 5 s |
| M8 | Tests stay green | green | 510 backend and 235 frontend tests passed at the last full run. They cover the API, retrieval, routing, grounding checks, essay validation and persistence |

**Why I track faithfulness separately from citations.** A citation proves where the model looked. It doesn't prove the model read the passage correctly. In my spike the model cited the right episode and reversed the claim: "retention is driven by activation" came back as "activation is driven by retention." A metric that only counted citations would have scored that as a success.

---

## 3. What I assumed

The brief is intentionally incomplete, so I wrote my assumptions down. These are the ones that would change the design if wrong.

| # | Assumption | If I'm wrong |
|---|---|---|
| A1 | The knowledge base is the repository the brief links (ChatPRD/lennys-podcast-transcripts): 303 episode files, 302 valid transcripts, one promo teaser excluded | Coverage changes; the data path is configurable |
| A2 | One team, no logins, a trusted network. Sessions are separate conversations, not separate users | Multi-user use needs authentication and row-level isolation |
| A3 | The evaluator has Docker and Ollama installed and 16 GB of RAM. A GPU helps but isn't required | A containerised Ollama option is documented |
| A4 | An honest "I don't have that" beats a plausible wrong answer | I accept lower coverage for higher trust |
| A5 | Essays are drafts for a person to edit, never auto-published | Publishing would need review gates |
| A6 | English only | |
| A7 | The source repository says the transcripts are for personal and educational use. My repository does not redistribute them; a script downloads them | Licensing must be confirmed before real client use |
| A8 | Twenty to sixty seconds for a cited answer is acceptable if progress is visible, and a few minutes for a long essay if the screen shows stages | It would need a smaller model, parallel drafting or streaming |
| A9 | The essay target is about 1,250 words, from the brief | Adjust the rules file |
| A10 | The agent runs on the Claude Agent SDK, chosen after a measured spike (section 6) | |
| A11 | The cloud provider (Anthropic) is implemented, with typed errors for a missing or invalid key, but I never ran it with a valid key because I have no budget | It must be validated before real use |
| A12 | PostgreSQL runs locally in Docker (pgvector image), not on Supabase or Railway. The brief allows those but doesn't require them | Moving to hosted Postgres is a connection-string change |

---

## 4. What I built, and what I left out

**Built:** grounded question answering with citations and the exact source passage; follow-up questions inside a session; refusal outside the transcripts; sessions you can list, switch and delete, with user metadata stored; a Ship 30 essay skill; Markdown and HTML artifacts with a sandboxed viewer; an Ollama and Anthropic toggle shown in the UI; Docker Compose start-up; structured logs; typed errors; automated tests; a manual UI test plan.

**Left out, on purpose:**
- Logins and multi-user isolation. That's a production problem, and not what this demo is for.
- Live transcript refresh. Ingestion is safe to re-run instead.
- Token streaming. The screen shows progress stages.
- Reranking and hybrid keyword search. I note them as next steps.
- Splitting two large modules (`routers/chat.py`, `agent/verify.py`). I ran out of time and I list it as technical debt.

---

## 5. How it works, and why

- **Search happens in my code, not in the model.** Every question is embedded and searched in Postgres with pgvector (`nomic-embed-text`, 768 dimensions) before the model runs. In my spike the model skipped the search tool entirely on one question, so I stopped leaving that choice to it.
- **Each request type gets exactly one tool.** A simple rule-based router decides whether a message is a question, an essay request or an artifact request, and the agent sees only the tool that request needs.
- **The agent is locked down.** The Claude Agent SDK runs with every built-in tool disabled, an empty working folder and an allow-list of my tools. A server-side agent with a shell would be a security hole.
- **Answers are numbered and checked.** Retrieved passages are labelled `[S1]` to `[Sn]`, the model must tag its claims, and code resolves each tag to a database row to build the citation. The UI shows the passage next to the claim. If retrieval is weak, the system refuses without calling the model.
- **Two providers.** Ollama is the tested default. Anthropic is behind the same toggle, error-handled but never run with a valid key.
- **Artifacts are untrusted.** The viewer is a sandboxed iframe with an empty `sandbox` attribute, backed by a sanitizer and a content security policy. Summary artifacts are built by code from the grounded answer, with a numbered sources list, so no model writes HTML for them.
- **Degraded mode is visible.** If the agent times out or fails, the answer is flagged as degraded and the real reason is logged. The system never switches silently from the local model to a cloud one.

---

## 6. What I measured before I built

Hardware: RTX 4050 6 GB and 16 GB RAM, with `qwen2.5:7b` about 82% on the GPU at a 4096 context.

| Experiment | Result |
|---|---|
| Raw tool calling, no framework | The "retention" question called the tool 4 of 4 times. "Activation in the first week" called it 0 of 4 |
| Claude Agent SDK with all its default tools | About 21,700 input tokens per call, the wrong tools chosen, and it hit the turn limit after 56 s |
| The same SDK with built-in tools disabled | 384 input tokens, correct tool use, 15.2 s end to end |
| 5 runs of 5 questions with the narrowed tool list | In-scope tool use 15 of 15; off-topic refusals 10 of 10; 2 of 15 answers reversed the source claim and 1 embellished |

That spike shaped the whole design: a small model behind an agent framework is reliable only when search is forced in code and the tool list is minimal, and a citation does not prove a claim is faithful.

---

## 7. How I checked my own work, including what I got wrong

I used AI coding tools (Antigravity and Claude Code) to write much of the code. What I owned was the specification (`SPEC.md`), the measurements, the audits and the decision about what to trust. After building, I had separate sessions review the project with the instruction to assume nothing works. They found real problems, which I fixed:

- **The agent code called an SDK function that doesn't exist.** Every request silently fell back to a plain model call. I rewrote it to match the spike.
- **"Turn that into a Ship 30 essay" was refused** by the retrieval gate. The gate now applies only to questions.
- **Artifact creation failed** because the model passed an unsupported type. Types are now a closed set, and summary artifacts are built by code, which took them from minutes to about 0.1 s.
- **Essays had duplicated paragraphs, template headings, a quote credited to the wrong speaker and a fabricated quote.** Quotes that fail verification are now deleted before saving, citations are normalised to one format, and headings are validated.
- **A database outage returned HTTP 500** instead of the documented 503, and **the cloud provider crashed on start** because a package was missing. Both are fixed; a missing or invalid key now produces a typed error.
- **Short follow-ups were refused** by the retrieval gate. A grounded follow-up path now merges the previous answer's sources and skips the score gate. It answered about 4 of 6 live runs.
- **A clean-clone check** from GitHub confirmed that the README works and found documentation gaps, which I fixed.

The logs of this work, including failed attempts and corrections, are in `transcripts/`. The audit reports are in `docs/`.

---

## 8. What can go wrong

| Risk | What I saw | What I did about it | What's left |
|---|---|---|---|
| **Hallucination** | Spike: 2 of 15 claims reversed. An audit found a fabricated quote in an essay | Search in code, numbered sources, citations from the database, passages shown in the UI, quote and name checks for essays, refusal when retrieval is weak | Not eliminated, and I haven't measured it on a labeled set |
| **Local model quality** | A 7B model is slower and less careful than a hosted one | Narrow tool list, small prompts, deterministic code wherever a model isn't needed | Medium |
| **Latency** | Answers 13 to 25 s at the median; essays 155 to 328 s | Progress stages, a smaller context window (8192; 16384 pushed more of the model onto the CPU), code-built artifacts | Medium on weaker hardware |
| **Cost** | Zero budget | A local model by default; the cloud is optional | |
| **Data leakage** | The transcripts are someone else's content, and with the cloud provider enabled, prompts and retrieved passages leave the machine | Transcripts aren't committed, the source says personal and educational use, and the logs were checked for secrets and stack traces | The client must confirm licensing |
| **Unsafe generated HTML** | Model output is untrusted | Empty-sandbox iframe, sanitizer, a restrictive CSP, markdown rendered without raw HTML, escaped titles, code-built summaries | Verified by tests and code review, with no automated browser test |
| **Prompt injection** through transcript text | Retrieved text goes into the prompt | The text is delimited and marked untrusted, and the agent has no tool that can do harm beyond saving an artifact | Wording could still be skewed |
| **Dependencies failing** | Ollama or the database can be down | Model unreachable gives 502; database down gives 503 `db_unavailable`, and `/health` recovered in about 5 s | Low |
| **Hard to run elsewhere** | Windows line endings, port conflicts, Ollama reachability | `.gitattributes`, configurable ports, a first-run script, troubleshooting in the README, a clean-clone test | Tested on Windows only |

---

## 9. How someone uses it

- **Ask a question.** Search runs in code, the agent answers with numbered tags, and the screen shows the answer, citation chips, the exact passages and the time taken.
- **Follow up.** "What about for B2B?" is rewritten with recent context before searching.
- **Ask something outside the podcast.** If retrieval is below the threshold, the refusal sentence comes back without a model call.
- **Ask for an essay.** "Turn that into a Ship 30 essay" uses the latest answer's sources; "Write a Ship 30 essay about X" searches for X. The skill drafts section by section, repairs quotes, normalises citations and validates. The chat shows a short message with the checks, including "Needs review" when one fails.
- **Ask for a one-pager.** Code builds the page from the grounded answer and the viewer shows it beside the chat.
- **Start a new chat.** It's a separate context.
- **Something fails.** The answer is flagged degraded and the reason is logged.

---

## 10. Acceptance status

| Criterion | Status | Evidence |
|---|---|---|
| Starts from a clean clone using only the README | Verified | Independent clean-clone run |
| Ingestion loads all valid transcripts and can be re-run | Verified | 302 documents; the second run skipped all |
| Grounded answers carry valid citations with visible passages | Verified | Live runs and unit tests |
| Longer follow-ups use session context | Verified | Live runs |
| Very short follow-ups ("Why is that?") | **Partially met**: about 4 of 6 live runs answered; the rest were refused by the model or verifier | Live runs; 16 unit tests |
| Unrelated questions are refused with no model call | Verified | 8 of 8; logs |
| Essay checks (headline, headings, citations, duplicates, quotes) | **Partially verified**: citation format, duplicates and quotes pass in the latest runs; the support score was low | Validator report; transcript search |
| Essay length near 1,250 words | **Met in the latest runs**: 1,119 and 1,122 words; essays below 1,000 are marked "Needs review: shorter than target" | Live runs; unit tests |
| Generated HTML can't run scripts or call out | Verified by tests and code review, not by an automated browser test | Sandbox, CSP and sanitizer tests |
| Failures give typed errors, structured logs and no stack traces | Verified | Model unreachable, database down (503), unknown session, bad JSON, oversize input, missing or invalid cloud key |
| Cloud provider path | Implemented and error-handled, **never run with a valid key** | |
| Claims are faithful to their passages | **Not measured on a labeled set** | See M3 |

---

## 11. What's still weak, and what I'd do next

**Still weak**
- A 7B local model can still make unfaithful claims. My pipeline reduces them but can't remove them, and I have no labeled measure of how often they happen.
- Essays take about 2 to 5.5 minutes on a 6 GB GPU (155 to 328 s observed) and are only loosely grounded: the validator's support score was 12.5% and 18.5% in the latest runs. Because unverified quotes are deleted, the latest essays contain no direct quotes at all.
- Very short follow-ups are refused about a third of the time.
- I've only run the project on Windows 11 with Docker Desktop. The Linux and macOS steps are written but unverified.
- The cloud provider has never run with a valid key.
- `routers/chat.py` and `agent/verify.py` are larger than my 300-line guideline, and I didn't split them under deadline.
- There are no logins; one trusted team is assumed.

**What I'd do next, in this order**
1. Build a labeled set of about 50 questions, with the expected episode and the expected quote, so I can measure retrieval and faithfulness instead of estimating them.
2. Make short follow-ups reliable.
3. Raise essay grounding: score support with embedding similarity as well as word overlap, delete unsupported sentences, and speed up generation with parallel drafts or a faster model.
4. Add hybrid keyword and vector retrieval and a reranker.
5. Validate the cloud provider with a real key.
6. Add streaming, and split the two large modules.

---

## 12. Questions I'd ask the client, and the assumption I made instead

1. How many people will use it, and how sensitive is the content? (A2, A7)
2. What does a good answer look like: a quote, a summary, or both? A cited summary plus the exact passage.
3. Is silence better than a guess? I assumed yes (A4).
4. What do the essays feed into? I assumed human-edited drafts (A5).
5. Where does it have to run? I assumed laptops, with no internet needed after setup (A3).
6. Is any source allowed beyond this archive? I assumed no (A1).
