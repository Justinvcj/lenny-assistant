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

## 8. Out of scope (UI)
Auth screens, multi-user presence, voice input, streaming token animation (stretch).
