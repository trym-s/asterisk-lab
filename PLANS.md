# PLANS.md - asterisk-lab live execution state

> Governed by `docs/runbooks/plan-rules.md`. Keep around 100 to 250 lines.
> Update after every meaningful step. Link artifacts; never paste long output.
> Always carry a state.
> When the governing spec is complete, archive this file under `docs/archive/plan/`.
> The next spec starts with a fresh root `PLANS.md` from `docs/templates/PLANS.md`.

**Status:** Active - specs decommission and directory update in progress.
**Governing spec:** `docs/specs/spec01-adopt-agent-harness.md`
**Last updated:** 2026-07-06

## Active milestones

- [x] Merge `AGENTS.md` template into project-specific 10-section AGENTS.md.
- [x] Replace project-slug placeholders in `CLAUDE.md` and `.githooks/pre-commit`.
- [x] Merge and prune all `<name>.template` files at the repo root and in `.codex/`.
- [x] Rewrite `docs/architecture/app-architecture.md` for the real three-VM
      plus voicebot layout.
- [x] Seed `docs/memory/decisions.md` with DEC-002...DEC-006 from existing
      operational knowledge (dual specs, transcriber pins, `.env` exclusion,
      SBC direction-aware INVITE, external skill store).
- [x] Fill `docs/runbooks/{local-development,testing,spec-rules}.md` with
      the real check commands and dual-spec discipline.
- [x] Create `docs/specs/spec01-adopt-agent-harness.md` and its kickoff prompt.
- [x] Land the initialization commit (`chore(harness): initialize
      agent-workflow-template`) after removing `INIT.md` and the empty
      `awt/` directory.
- [x] Migrate legacy `specs/` directory (domain specs, contracts, decisions, changes)
      under `docs/specs/` (into `docs/specs/domains/`, `docs/specs/global/`,
      and `docs/specs/changes/`). Consolidated into `docs/specs/` as the
      single spec surface. Updated DEC-002 entry.
- [x] Update references to `specs/` to `docs/specs/` across repository files.
- [x] Update Makefile default VM IP to point to the active Asterisk VM (192.168.122.247).
- [ ] Follow-up: extract more DEC-* entries from git history (LiveKit
      wideband trial, Pipecat AudioSocket lane, monitoring provisioning
      quirks). Tracked as scope inside spec01.

## Blockers

- none

## Canonical evidence

- `AGENTS.md` sections 1-10 reflect the real project after the merge.
- `docs/memory/decisions.md` DEC-001..DEC-006 documents the current
  governance and operational baselines.
- `docs/architecture/app-architecture.md` describes the current
  three-VM plus voicebot layout.
- `docs/specs/` is the single spec surface, with domain contracts migrated under `docs/specs/domains/` and `docs/specs/global/`.

## Recent updates

- 2026-07-06 - Added simplified VM management (virsh) targets (`vms`, `ips`, `up`, `down`, `up-sbc`, `down-sbc`, `up-mon`, `down-mon`) to the `Makefile`.
- 2026-07-06 - Migrated all domain specs, contracts, decisions, and runbooks under `docs/specs/` (placed into `docs/specs/domains/`, `docs/specs/global/`, and `docs/specs/changes/`). Fixed path references in domains README, conventions, agent-routing, and validation model. Updated Makefile default VM IP.
- 2026-07-06 - Harness initialized from agent-workflow-template. AGENTS.md
  rewritten to 10-section layout; `docs/specs/spec01` created for
  the adoption effort itself.
- 2026-07-06 - `specs/` directory decommissioned. All spec work consolidated
  under `docs/specs/`. DEC-002 updated. Stale references being cleaned up
  across AGENTS.md, PROCESS.md, README.md, PLANS.md, spec-rules.md,
  testing.md, Makefile, `.claude/README.md`, and `.codex/README.md`.

## Archive pointers

- none
