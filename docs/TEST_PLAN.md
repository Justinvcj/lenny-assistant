# Test Plan & Verification Checklist — Lenny Growth Assistant

## 1. Automated Test Suites

### Backend Tests
```powershell
# Run from backend/ directory
..\.venv\Scripts\python.exe -m pytest tests -v
```
- **Coverage**:
  - `test_artifacts.py`: GET /artifacts/{id}, POST /artifacts, 413 artifact_too_large (>200KB), 422 invalid type, tool validation.
  - `test_ship30.py`: Validator unit tests (word count, hook, structure, takeaway, citations), outline planner, end-to-end pipeline with FakeLLMProvider.
  - `test_chat.py`: Intent routing, grounding refusal at score < 0.58, citation retry protocol, artifact persistence.
  - `test_health.py`: Live PostgreSQL and Ollama connectivity checks.
  - `test_sessions.py`: Session CRUD and validation.

### Frontend Tests (Vitest)
```powershell
# Run from frontend/ directory
npm test
npm run build
```
- **Coverage**:
  - `ArtifactPanel.test.tsx`: Malicious payload corpus (<script>, <img onerror>, javascript: links, <iframe>, <form>, <meta refresh>, <base>, remote <img>), strict CSP meta tag, empty sandbox="" tokens, size limits, Copy & Download buttons, safe markdown links, "Open artifact" button.
  - `App.test.tsx`: Full application workflow, session management, sending messages, refusal cards, error recovery.
  - `security_adversarial.test.tsx`: XSS prevention, markdown security, link sanitization.

---

## 2. Manual Browser Checklist: Artifact Panel & Sandbox (Phase 7)

Perform these steps in a real browser (Chrome / Edge / Firefox):

| # | Test Case | Action | Expected Result | Pass / Fail |
|---|---|---|---|---|
| **M1** | **Artifact Auto-Open** | Ask: *"Make a one-pager (HTML) about retention"* | Response arrives, assistant message shows *"Open artifact: Retention One-Pager"* button, and right-hand Artifact Panel opens automatically. | [ ] |
| **M2** | **Sandboxed Iframe Security** | Open Browser DevTools (F12) → Inspect Artifact preview element | `<iframe>` element has attribute `sandbox=""` strictly empty (NO `allow-scripts`, NO `allow-same-origin`). Mandatory security notice *"Sandboxed preview: scripts and external requests are blocked."* is visible above preview. | [ ] |
| **M3** | **Content-Security-Policy (CSP)** | Inspect `srcdoc` of the `<iframe>` in DevTools | `<meta http-equiv="Content-Security-Policy">` is present with `default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; base-uri 'none'; form-action 'none'`. | [ ] |
| **M4** | **Malicious Code Neutralization** | Ask assistant to generate HTML with `<script>alert('pwned')</script>` or `<img src=x onerror=alert(1)>` | Preview displays static text/structure. **No JavaScript executes**, no alert dialog appears, and event handlers are neutralized. | [ ] |
| **M5** | **Tracking Pixel / Remote Image Block** | Inspect network tab when viewing artifact with remote `<img>` tags | Remote images are either stripped or blocked by CSP (`img-src data:;`). Zero third-party network requests are made. | [ ] |
| **M6** | **Preview vs. Source Tab Switching** | Click **Source** tab in Artifact Panel header | Panel switches to plain-text view displaying raw HTML/Markdown source code inside a `<pre>` block. Click **Preview** switches back to rendered layout. | [ ] |
| **M7** | **Copy to Clipboard** | Click **Copy** button in Artifact Panel | Button briefly changes to *"Copied"* with green checkmark. Clipboard contains exact artifact content. | [ ] |
| **M8** | **Download File** | Click **Download** button in Artifact Panel | Browser prompts file download saving file as `<title-slug>.html` or `<title-slug>.md`. | [ ] |
| **M9** | **Assistant Message "Open Artifact" Button** | Close panel using (X), then click **Open artifact: [Title]** button on the assistant message | Panel smoothly re-opens displaying the selected artifact. | [ ] |
| **M10** | **Markdown Artifact Rendering** | Ask: *"Turn that into a Ship 30 essay"* | Essay artifact renders formatted headings, bullet lists, bold text via ReactMarkdown. Raw HTML is inert. Outbound links open in new tab with `target="_blank" rel="noopener noreferrer"`. | [ ] |
| **M11** | **Oversize Payload Defense** | Send or inspect an artifact exceeding 200,000 bytes | Visible alert banner *"Artifact size exceeds 200,000 bytes limit. Rendering blocked."* is displayed, preventing memory/browser DoS. | [ ] |
