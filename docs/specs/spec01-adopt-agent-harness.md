# Spec spec01 - Adopt the agent-workflow-template harness

> Governed by `docs/runbooks/spec-rules.md`. A spec is a stable contract, not a
> changelog. Daily progress belongs in `PLANS.md`.

- **Status:** Active
- **Owner:** operator (initial execution by Claude Code during
  `/harness-init`)
- **Created:** 2026-07-06

## Goal

Bring the existing asterisk-lab repository under the agent-workflow-template
governance model, so that every future agent session starts from a single set
of rules (`AGENTS.md`), a single live state file (`PLANS.md`), and a shared
memory surface (`docs/memory/`).

## Problem Statement

The repository already had:

- a working `AGENTS.md` pointing at domain contracts;
- a mature domain spec, runbook, and VAL-* acceptance contract tree;
- project-level `.claude/skills/` and `.claude/agents/` roles;
- a `.mcp.json` with zenith configured and out-of-repo skill stores.

The agent-workflow-template drop added the AWT root scaffolding
(`PLANS.md`, `TODO.md`, `DEBATE.md`, `docs/`, harness `AGENTS.md.template`,
etc.) alongside the existing content. Without a deliberate adoption, the
repo would have two overlapping rulebooks, an empty `docs/specs/`, and
placeholder markers scattered across the harness files. This spec is the
adoption itself.

## Scope

1. Merge `AGENTS.md.template` into a single project-specific `AGENTS.md`
   with the AWT 10-section layout, preserving every existing rule.
2. Fill `docs/architecture/app-architecture.md` with the real three-VM
   plus voicebot layout.
3. Seed `docs/memory/decisions.md` with DEC-* entries covering
   governance, the dual spec surface, transcriber pins and hardening,
   the deploy `.env` exclusion, the direction-aware SBC INVITE branch,
   and the external skill store.
4. Reconcile the spec surface under `docs/specs/` and document it in
   `docs/runbooks/spec-rules.md`.
5. Wire the git identity, ASCII, and spec-boundary pre-commit hook
   (`.githooks/pre-commit`) with the real project name, and add the
   allowlist for user-facing root files (`README.md`, `PROCESS.md`,
   `NOTES.md`).
6. Delete `INIT.md`, all `.template` files, and the empty `awt/`
   directory.
7. Commit the initialization as `chore(harness): initialize
   agent-workflow-template`.

## Non-Goals

- Migrating or renumbering the existing domain contract tree. Contracts
  keep their current numbers and layout where preserved.
- Rewriting the four existing `.claude/agents/*.md` roles.
- Moving `.agents/skills` and `.codex/skills` from symlinks into in-repo
  copies. DEC-006 documents the current setup.
- Any application-code changes (`asterisk/`, `sbc/`, `monitoring/`,
  `services/`, `scripts/`, `infra/`, `install.sh`, `Makefile`).

## Architecture Contract

- `docs/specs/` holds the governing spec surface for
  harness or programme initiatives; each pairs with a kickoff prompt
  under `docs/prompts/`.
- Runtime layouts and boundaries are documented in
  `docs/architecture/app-architecture.md`. No new component or boundary
  is introduced by this spec.

## Config Contract

- No changes to `.env.example`.
- `.gitignore` gains the AWT harness blocks (`.env.*`, `!.env.example`,
  `runtime/`, `logs/`, `.codex/*` allowlist, `docs/debates/*/transcript.md`)
  without dropping the project-specific ignores.
- `.codex/config.toml` mirrors the zenith server from `.mcp.json` and
  sets `[features] memories = false` to comply with the AGENTS.md hard
  rule that agent memory is repo-tracked only.

## API Contract

Not applicable. This spec is a governance and documentation initiative.

## Observability Contract

- All initialization steps are recorded in `PLANS.md` (Active milestones
  and Recent updates).
- The initialization commit references this spec by filename.

## Acceptance Criteria

- `AGENTS.md` sections 1-10 are populated with real project content;
  no template placeholders (the project-slug, project-purpose,
  architecture-principles, or harness-init HTML-comment markers used by
  the agent-workflow-template) remain outside the three harness-init
  skill trees and `docs/templates/`.
- `PLANS.md` carries a real `Last updated` date and Governing spec
  pointer.
- `docs/memory/decisions.md` contains DEC-001..DEC-006.
- `docs/architecture/app-architecture.md` describes the real three-VM
  plus voicebot layout.
- `docs/runbooks/spec-rules.md` documents the consolidated single spec surface.
- No `*.template` files remain anywhere in the repository.
- `INIT.md` and the empty `awt/` directory no longer exist.
- The pre-commit hook accepts a commit with `git config user.name
  "Claude" && git config user.email "claude@asterisk-lab.local"`.
- `git status` is clean after the initialization commit.

## Follow-Ups

- Backfill more DEC-* entries from git history and `NOTES.md` (LiveKit
  wideband trial and Pipecat AudioSocket lane rationale) into
  `docs/memory/`.
- Decide whether to move the shared skill store in-repo (DEC-006) or
  keep the zenith symlinks; record the outcome as a follow-up DEC.
- Populate `TODO.md` with any operator-owned open items surfaced during
  the adoption.
