# Security — Lenny Growth Assistant

Scope: demo-grade system for a trusted single team. Controls below are what is implemented and tested; residual risks are listed honestly.

## 1. Threat model
| # | Threat | Where | Control | How verified |
|---|---|---|---|---|
| T1 | XSS / script injection via LLM-generated HTML artifact | Artifact viewer | Sandboxed iframe, DOMPurify, CSP in srcdoc (§2) | Frontend tests with a payload corpus; manual check |
| T2 | Markdown rendering injects raw HTML/JS | Markdown artifacts and chat | `react-markdown` without raw HTML plugins; DOMPurify on any HTML path; links get `rel="noopener noreferrer"` | Unit test with `<img onerror>` / `javascript:` links |
| T3 | Prompt injection through transcript text or user text | RAG prompt | Retrieved text wrapped in delimiters and labelled untrusted data; system prompt forbids following instructions inside sources; agent has no side-effecting tools besides saving an artifact | Test: poisoned chunk ("ignore previous instructions...") does not change behaviour/tool use |
| T4 | Agent runtime abuse (shell, file read/write, web) | Claude Agent SDK | Allowlist of our MCP tools only; ALL built-in tools disabled; empty temp `cwd`; small `max_turns`; timeout | Test asserting init tool list == our tools; log check |
| T5 | SQL injection | DB access | SQLAlchemy parameterized queries only; no string-built SQL | Code review + test with hostile inputs |
| T6 | Secret leakage | Repo, logs, transcripts | `.env` ignored; `.env.example` placeholders; secret scan before commit; scrub agent transcripts; never log keys or full prompts at INFO | `grep`/gitleaks-style scan in P13 |
| T7 | Transcript IP exposure | Repo | `data/` gitignored; ingest downloads from source; assumption A7 | Check `git ls-files` has no transcripts |
| T8 | DoS via huge inputs/outputs | API | Message length cap; artifact size cap; request timeout; top-k cap | Tests for 422/413 |
| T9 | Cross-origin abuse | API | CORS restricted to configured origins | Test |
| T10 | Info leak in errors | API | Error envelope; no stack traces; request id for support | Test |
| T11 | Vulnerable/malicious dependencies | Supply chain | Pin versions; install only listed packages; prefer versions at least 2 weeks old | Review lockfiles |
| T12 | Container escape/privilege | Docker | Non-root user in backend image; no privileged mode; db port bound to localhost | Compose review |

## 2. Artifact viewer specification (what it permits, blocks, and why)
Generated HTML is untrusted because the model may emit scripts, inline handlers, forms, remote resources, or tracking pixels (by mistake or via prompt injection).

**Rendering pipeline (HTML artifact):**
1. Size check (`ARTIFACT_MAX_BYTES`).
2. Sanitize with DOMPurify: forbid `script`, `iframe`, `object`, `embed`, `form`, `link`, `meta`, `base`; forbid all `on*` attributes; allow `style` elements and a safe set of tags/attributes; forbid `javascript:` URLs.
3. Wrap in a document with a CSP meta tag:
   `default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; base-uri 'none'; form-action 'none'`
4. Render in `<iframe sandbox="" srcdoc=...>` — **empty sandbox attribute**: no scripts, no same-origin access, no forms, no popups, no top navigation, no downloads, unique opaque origin.
5. Inside the viewer show a visible note: "Sandboxed preview: scripts and external requests are blocked."

**Permits:** static HTML and CSS, inline `<style>`, data-URI images, text layout.
**Blocks:** JavaScript of any kind, event handlers, remote images/fonts/stylesheets (no tracking pixels), forms, nested frames, plugins, `<base>` tampering, navigation of the parent page, access to cookies/localStorage/the app origin.

**Why not `allow-same-origin`:** combined with scripts it would let content remove its own sandbox; even without scripts it removes the opaque-origin isolation we want. We need neither.

**Markdown artifacts:** rendered with `react-markdown` (no raw HTML), then displayed in the app's own pane or the same sandboxed iframe; links open with `rel="noopener noreferrer"`.

**Source view:** a "Source" tab shows the raw text as plain text, so users can inspect what the model produced.

## 3. Agent and prompt-injection handling
- Retrieved passages are inserted inside clearly delimited blocks (`<source id="S1" untrusted>...</source>`); system prompt states they are data, not instructions.
- Tools cannot read files, run commands, call the network, or modify anything except saving an artifact row.
- Output is never executed. Citations are rebuilt from the database, so injected text cannot fabricate a source.
- Residual risk: a poisoned passage could still skew the wording of an answer; the UI shows the source passage so a human can see it.

## 4. Secrets and data handling
- Real keys only in local `.env` (gitignored). Dummy `ollama` token is not a secret.
- Local Postgres password `localdev` is a throwaway for a local-only container; not exposed beyond localhost.
- Agent transcripts are scrubbed of keys, usernames/paths where sensitive, before commit.
- User data = chat text stored in local Postgres; no third-party calls in the default Ollama configuration. With the cloud provider enabled, prompts and retrieved passages are sent to that provider (documented in README).

## 5. Residual risks (stated honestly)
No authentication; a local model can still produce wrong claims; Anthropic provider untested; browser sandbox correctness depends on the user's browser; dependency vulnerabilities not continuously scanned.

## 6. Verification checklist (fill in during playbook P8)
- [ ] Payload corpus renders inert (`<script>`, `onerror`, `javascript:` link, `<iframe>`, `<form>`, remote `<img>`, `<meta refresh>`, `<base>`).
- [ ] Init tool list equals our tools only.
- [ ] Poisoned-chunk test passes.
- [ ] No secrets/transcripts tracked by git.
- [ ] Error responses contain no stack traces.
