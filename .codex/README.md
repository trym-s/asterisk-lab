# Codex Agent Entry Point

Use `../AGENTS.md` as the repo-wide operating rules.

This directory is only a pointer for Codex-specific discoverability and
non-secret project configuration. It is not a source of truth. Do not place
independent acceptance criteria here.

Durable agent knowledge belongs in tracked `../docs/memory/*` files, not in
private memory stores under this directory. Keep API keys, credentials,
customer data, recordings, transcripts, and runtime evidence out of this
directory too.

Before editing:

1. Read `../AGENTS.md`.
2. Read the governing spec under `../docs/specs/` if `PLANS.md` points to one.
3. Read the relevant `docs/memory/decisions.md` entries.
4. Update docs/specs when behavior changes.
