# Kickoff Prompt - spec07 voicebot call console redesign

Read `AGENTS.md`, `PLANS.md`, and the governing spec:

```text
docs/specs/spec07-voicebot-call-console.md
```

Implement the spec end to end: redesign the per-call console page around
the chat-bubble conversation and pipeline-pulse strip, extend the turns
API with the additive pulse/summary fields, and remove the retired
`/parity` and `/comparison` surface. Keep the dashboard read-only
(DEC-008, DEC-009), keep the no-build-step Jinja2 + vanilla JS + CSS
architecture, and do not touch the other dashboard pages beyond the nav
link.

Keep `PLANS.md` updated after meaningful work, preserve user changes,
keep secrets and runtime data out of git, run the relevant checks
(dashboard unit tests, `ruff check`, `make verify` on the Asterisk VM),
prove the live-call acceptance criteria with evidence under
`runtime/spec07-live-evidence/`, and commit all agent-made changes with
English Conventional Commits.
