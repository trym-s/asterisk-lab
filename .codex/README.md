# Codex Agent Entry Point

Use `../AGENTS.md` first, then `../specs/README.md`.

This directory is only a pointer for Codex-specific discoverability and
non-secret project configuration. It is not a source of truth. Do not place
independent acceptance criteria here.

Durable agent knowledge belongs in tracked `../docs/memory/*` files, not in
private memory stores under this directory. Keep API keys, credentials,
customer data, recordings, transcripts, and runtime evidence out of this
directory too.

Before editing:

1. Read `../specs/global/agent-routing.md`.
2. Read the affected domain spec under `../specs/domains/`.
3. Read the relevant `contracts/VAL-*.md`.
4. Update specs/contracts in the same change when behavior changes.
