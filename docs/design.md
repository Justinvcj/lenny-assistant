# Design — Lenny Growth Assistant (UI/UX)

## 1. Principles
1. **Trust over polish.** Every claim shows where it came from; passages are one click away.
2. **Honest about waiting.** Local models take 10–30 s; show progress and elapsed time, never a frozen screen.
3. **Honest about refusing.** "I don't have that in the transcripts" is a designed state, not an error.
4. **Chat first, artifact beside it.** Reading and writing happen side by side, like Claude's artifacts.
5. **Safe by default.** Anything generated is previewed in a sandbox with a visible notice.

## 2. Layout
Desktop (≥1024px): three regions — left sidebar (sessions, new chat), center chat, right artifact panel (collapsible, opens when an artifact is created).
Tablet (640–1023px): sidebar becomes a drawer; chat and artifact panel toggle via tabs.
Mobile (<640px): single column; artifact opens as a full-screen sheet with a back button.
Header: app name, active model badge (e.g. "Ollama · qwen2.5:7b"), connection indicator (green/amber/red from `/health`).

## 3. Components
- **Session list:** title (first user message, truncated), relative time, active highlight, delete with confirm.
- **Message list:** user right, assistant left; assistant messages show answer text, citation chips `[S1] Guest — Episode title`, and an expandable "Sources" section with the exact passage.
- **Composer:** multiline input, Enter to send, Shift+Enter for newline, disabled while sending, character counter near the cap, quick-action chips: "Turn that into a Ship 30 essay", "Make a one-pager (HTML)".
- **Artifact panel:** title, tabs **Preview | Source**, copy and download buttons, sandbox notice, size warning.
- **Status banners:** Ollama down, DB down, degraded mode ("answered without the agent runtime").

## 4. Interaction states
| State | Behaviour |
|---|---|
| Empty (no sessions) | Welcome text, 3 example questions as clickable chips |
| Loading | Skeleton assistant bubble, stage text ("Searching transcripts…", "Writing answer…"), elapsed seconds, Cancel |
| Answer | Text + citation chips + sources |
| Refusal | Neutral card: "I don't have information about that in the transcripts." + tip to rephrase; no source chips |
| Error | Inline red message with plain-language cause and Retry; request id in small text |
| Degraded | Amber tag on the message |
| Essay ready | Message states word count; artifact opens in panel |

## 5. Accessibility
Semantic landmarks (nav, main, aside); all controls reachable by keyboard with visible focus; message list is an `aria-live="polite"` region; buttons have accessible names; color contrast ≥ 4.5:1; status never conveyed by color alone (icon + text); iframe has a descriptive `title`; respects `prefers-reduced-motion`.

## 6. Visual style
Neutral background, one accent color, system font stack, 16px base, comfortable line length (~70ch) for answers, monospace only for source view. Light theme required; dark theme optional.

## 7. Content rules
Answers lead with the direct answer, then support. Refusal wording is fixed and identical everywhere. Never show raw model errors; map to friendly text with a request id.

## 8. Information Architecture

### Screens & Viewports
The interface is structured as an adaptive single-page workspace (SPA) designed to minimize cognitive overhead and eliminate multi-page page transitions:

```
┌────────────────────────────────────────────────────────────────────────┐
│ Header: Logo | Model Badge (Ollama · qwen2.5:7b) | Health Dot (online) │
├───────────────┬──────────────────────────────────────┬─────────────────┤
│ Left Sidebar  │ Center Main Chat Viewport            │ Right Artifact  │
│ (280px)       │ (Flex-1, max-width ~860px)           │ Panel (420px)   │
│               │                                      │                 │
│ [+ New Chat]  │ [Empty Knowledge Base Banner]        │ [Tabs: Pre/Src] │
│               │                                      │ [Copy][Download]│
│ Session List  │ Message History:                     │ ┌─────────────┐ │
│ - Title       │ - User Bubble                        │ │ Sandboxed   │ │
│ - Timestamp   │ - Assistant Bubble                   │ │ Iframe /    │ │
│ - Delete [X]  │   * Grounded text                    │ │ Markdown    │ │
│               │   * Citations [S1][S2]               │ │ Viewer      │ │
│               │   * Verified Passages Accordion      │ └─────────────┘ │
│               │                                      │ [Sandbox Alert] │
│               │ [Loading Skeleton + Elapsed Timer]   │                 │
│               │ ───────────────────────────────────  │                 │
│               │ Docked Composer:                     │                 │
│               │ [Textarea (Auto-resize) | Send | 4k] │                 │
└───────────────┴──────────────────────────────────────┴─────────────────┘
```

### Region Responsibilities
1. **Header Region (`<header>`)**:
   - Persistent brand identity ("Lenny Growth Assistant").
   - Live Model Badge (`{provider} · {model}`) reflecting active backend configuration from `/config`.
   - Real-time Connection Dot (`online` [green], `degraded` [amber], `offline` [red]) polled via `/health`.
   - Mobile hamburger toggle for sidebar drawer.
2. **Left Navigation Region (`<nav aria-label="Chat history">`)**:
   - Action: `+ New Chat` primary button to reset viewport state.
   - History: Reverse-chronological session list (`/sessions`).
   - Active session highlight and confirmation-backed session deletion modal.
3. **Center Main Chat Region (`<main role="main">`)**:
   - Diagnostic Banners: Amber empty knowledge base banner (when `/health` reports `ingested: false`), red error banner with Request ID and retry CTA.
   - Message Stream: Semantic log (`role="log" aria-live="polite"`) rendering user queries, verified assistant responses with expandable citation chips, and neutral refusal cards.
   - In-Flight Feedback: Skeleton bubble showing real-time elapsed seconds and an immediate Cancel button (`AbortController`).
   - Docked Composer: Auto-expanding textarea, 4,000-character limit counter, Shift+Enter newline support, and quick-action chips.
4. **Right Artifact Region (`<aside role="complementary">`)**:
   - Side-by-side workspace for reading long-form generated outputs (Ship 30 essays, HTML one-pagers).
   - Mode switcher: `Preview` (sandboxed rendering) and `Source` (raw text).
   - Action controls: One-click clipboard copy with status feedback and formatted file download (`.html` or `.md`).
   - Safety: Sandboxed iframe (`sandbox=""`), size limit validation (200 KB), and React `ArtifactErrorBoundary`.

---

## 9. Design Decisions & Trade-Offs

| Decision | Selected Approach | Rejected Alternative | Rationale & Trade-Off |
|---|---|---|---|
| **1. Artifact Presentation** | **Side-by-side sliding panel** | Modal overlay popup | Modals obscure conversational context and prevent referencing previous messages while reviewing generated essays. Side-by-side layout mimics professional IDEs and Claude artifacts. |
| **2. Iframe Sandbox Policy** | **Strictly empty `sandbox=""`** | `sandbox="allow-scripts"` | Security invariant. Model-generated HTML must never execute JavaScript. An empty sandbox eliminates XSS, localStorage theft, and cross-origin access entirely. |
| **3. Intent Routing Engine** | **Deterministic regex/rule router** | LLM self-classification prompt | Zero token consumption and sub-millisecond classification (<1ms vs 3–8s). Prevents local 7B model hallucination when routing between QA, Essay, and Artifact modes. |
| **4. In-Flight Progress** | **Inline skeleton with elapsed timer & cancel** | Full-screen blocking modal spinner | Local inference on 7B models can take 15–30 seconds. A blocking modal induces user fatigue and prevents aborting stalled generations. |
| **5. Citation Architecture** | **Interactive accordion chips `[S#]` with exact quotes** | Footnotes or plain text links | Inline chips allow instant verification without leaving the conversational thread. Expanding a chip displays the verbatim speaker turn and episode metadata. |
| **6. Observability & Telemetry** | **Dedicated `/client-events` endpoint (type + reason only)** | Client console logging or transmitting full payload | Enables server-side observability for frontend rendering failures while strictly avoiding logging sensitive user content or prompt data. |
| **7. Error Handling Strategy** | **Graceful inline ErrorBanner with Request ID** | Raw generic toast or alert dialog | Toasts easily vanish without notice. Inline banners retain context, surface the correlated `X-Request-ID` for debugging, and provide a direct "Retry" button. |

---

## 10. Out of scope (UI)
Auth screens, multi-user presence, voice input, streaming token animation (stretch).
