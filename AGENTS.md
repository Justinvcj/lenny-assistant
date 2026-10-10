# AGENTS.md

Read SPEC.md first, then docs/architecture.md and docs/security.md. SPEC.md is the source of truth.

Rules for every session:
- Do only the task you are given. Do not start other tasks.
- If SPEC.md and reality conflict, stop and report. Do not silently change the design.
- Never enable built-in agent tools in the backend runtime. Never add allow-scripts or allow-same-origin to the artifact iframe.
- Do not commit data/, .env, notes/, or any key.
- Do not claim something works unless it was run. Mark untested things UNTESTED.
- I (the user) commit. End each task with: files changed, verify commands, known gaps.
