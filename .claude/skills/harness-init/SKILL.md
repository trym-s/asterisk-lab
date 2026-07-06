---
name: harness-init
description: Initialize the agent-workflow-template harness in this repository. Use immediately after the template files were cloned or copied into a new (greenfield) or existing (brownfield) project. Replaces placeholders, fills AGENTS.md from an operator interview or a codebase scan, seeds the docs system, creates the first spec, and commits the initialized harness.
---

# Harness Init

Turn the freshly copied agent-workflow-template files into a project-specific
harness. Run this once, from the repository root, right after the template
files were copied into the project (see `INIT.md` for the copy commands; the
copy never overwrites existing files, git history, or remote configuration).
Everything is done by you, the agent - there is no init script.

## Read First

- `INIT.md` (the copy/clone instructions this skill completes)
- `AGENTS.md` (the template version with placeholders; if the project already
  had its own `AGENTS.md`, the copy step left the template version next to it
  as `AGENTS.md.template` - the same applies to every root file that already
  existed: its template source is at `<name>.template`)
- `docs/runbooks/plan-rules.md` and `docs/runbooks/spec-rules.md`

## Arguments

Any text passed after the skill invocation (for example
`/harness-init migrate the existing docs and prompts into the new structure`)
is the operator's directive. Treat it as the first mission for Step 1/Step 4
and shape `spec01` around it. With no arguments, ask for or derive the first
mission as described below.

## Step 0 - Detect Mode

- **Greenfield**: the repository contains only the template files (plus at
  most `.git`, an auto-generated README/LICENSE/.gitignore, or empty skeleton
  dirs). You will interview the operator.
- **Brownfield**: real application code already exists. You will scan the
  codebase and derive facts from it; ask the operator only what the code cannot
  tell you.

## Step 1 - Collect Project Facts

Greenfield - ask the operator (in their language), at minimum:

1. Project name (short slug) and one-paragraph purpose.
2. Language/stack and rough component layout.
3. Deploy model (systemd, docker compose, bare scripts, none yet).
4. Does the project touch live/production systems? Which safety rules apply?
5. The first concrete mission (this becomes spec01).
6. Any MCP servers this project needs (add them to both `.mcp.json` and
   `.codex/config.toml`).

Brownfield - derive from the repository instead:

1. Name from the directory or package metadata; purpose from README/code.
2. Real directory layout for the ownership table.
3. Build/test/lint commands from the build files (pyproject, package.json,
   Makefile, go.mod, ...).
4. Deploy assets present (systemd units, compose files, CI configs).
5. Existing docs worth linking or migrating into `docs/`.
6. Existing agent/workflow files (an own `AGENTS.md`, a legacy plan file, an
   existing spec system) - these need merge or migration, not replacement.

Confirm your summary of the collected facts with the operator before writing.

## Step 2 - Replace Placeholders

Replace in all template files, including any `<name>.template` copies
(grep to find them all):

- `PROJECT_NAME` -> the project slug (files: `AGENTS.md`, `CLAUDE.md`,
  `PLANS.md`, `README.md`, `.env.example`, `.githooks/pre-commit`,
  `docs/templates/PLANS.md`).
- `PROJECT_PURPOSE` -> the one-paragraph purpose (`AGENTS.md`, `README.md`).
- `PROJECT_ARCHITECTURE_PRINCIPLES` -> 3-8 durable principles (`AGENTS.md`).
- `YYYY-MM-DD` in root `PLANS.md` -> today's date (leave the copies inside
  `docs/templates/` as placeholders).
- Every `<!-- harness-init: ... -->` comment -> real content, then delete the
  comment.

## Step 3 - Fit The Harness To The Project

- `AGENTS.md` Directory Ownership: make the table match the real (or planned)
  layout; remove rows that do not apply, add project-specific paths.
- `AGENTS.md` Environment And Safety: keep only the rules that apply; for
  projects with live/production hosts keep the production safety defaults.
- `AGENTS.md` Done Criteria: add the project's concrete check commands.
- Merge every `<name>.template` file into its existing counterpart, then
  delete the `.template` copy. An existing `AGENTS.md` is the most important
  case: restructure it to this template's section layout (Purpose, Read Order,
  Directory Ownership, Agent and Skill Model, Working Rules, Architecture
  Principles, Environment And Safety, Done Criteria, Commit Conventions, Spec
  and Plan Workflow) while preserving every project-specific rule it already
  contains. For an existing README add a "Start Here" section; for an existing
  `.env.example` extend it. Nested files matter too: merge
  `.githooks/pre-commit.template` so the existing hook gains the identity,
  ASCII, and spec-boundary checks, and merge `.codex/config.toml.template` /
  `.codex/README.md.template` into the existing Codex config. Show the
  operator every merge before applying it.
- If the provider skill trees (`.claude/skills/`, `.codex/skills/`,
  `.agents/skills/`) already contained files before the copy, treat differing
  template skills as an upgrade decision: list the differences and let the
  operator choose per skill; then re-sync the three trees.
- The live plan file is always named `PLANS.md` - this name is canonical.
  If the project has a legacy plan file under another name (for example
  `PLAN.md`), migrate its active content into `PLANS.md`, archive the legacy
  file under `docs/archive/plan/` with a dated name, remove it from the root,
  and update any references to it (with operator approval).
- `.gitignore`: adapt the tooling ignore blocks to the project's stack (the
  template ships Python-flavored entries; replace them with the stack's
  equivalents). Always keep the harness blocks: `.env` + `!.env.example`,
  `runtime/`, `logs/`, the `.codex/*` allowlist, and debate transcripts.
- Per-directory README convention: give each key top-level directory (`src/`,
  `tests/`, `configs/`, `deploy/`, `scripts/`, and the `docs/` subdirs already
  covered) a short `README.md` stating its purpose and constraints. Create
  missing ones; extend existing ones only with operator approval.
- `.env.example`: replace the example block with the project's real variable
  shape (secrets as `replace-me`, non-secret defaults real).
- `.mcp.json` and `.codex/config.toml`: add the domain MCP servers the operator
  named; keep both files in sync (same servers, provider-appropriate settings).
- `.codex/config.toml`: review the shipped defaults (`model`, `sandbox_mode`,
  `model_reasoning_effort`) with the operator; they are starting points, not
  requirements.
- `docs/architecture/app-architecture.md`: brownfield - rewrite the shipped
  skeleton to describe the system as found; greenfield - fill it from the
  planned component layout the operator described (components, boundaries,
  interactions), to be expanded during the first spec.
- Brownfield only: seed `docs/memory/` with proven facts you discovered
  (as `DEC-NNN` entries only when they are real decisions).
- Optional (operator choice): add domain subagent roles as
  `.claude/agents/<role>.md` + `.codex/agents/<role>.toml` pairs, following
  `docs/templates/subagent-role-template.md`. Skip by default.

## Step 4 - First Spec

Create the first spec from `docs/templates/spec-template.md`:

- Greenfield: `docs/specs/spec01-<first-mission>.md` for the operator's first
  mission, plus the paired kickoff prompt under `docs/prompts/`.
- Brownfield: either the operator's first mission, or - if none was given -
  `spec01-adopt-agent-harness.md` covering: document current architecture,
  wire up the check commands, and backfill `docs/memory/` from git history.
- Brownfield with an existing spec system: if `docs/specs/` (or equivalent)
  already exists with a different numbering scheme, do not renumber existing
  specs. Either continue the existing scheme or switch new specs to
  `specNN-topic.md` going forward; record the choice as a `DEC-NNN` entry and
  reflect it in `docs/runbooks/spec-rules.md`.
- Point `PLANS.md` at the governing spec and set Status accordingly.

## Step 5 - Wire Git And Commit

```bash
git init                       # only if not already a repository
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
# set YOUR identity per AGENTS.md Commit Conventions:
git config user.name "Claude" && git config user.email "claude@<project>.local"
#   or, when running as Codex:
git config user.name "Codex" && git config user.email "codex@<project>.local"
```

The pre-commit hook enforces the ASCII character conventions (no em dashes,
emoji, or non-ASCII arrows) on harness paths only: root `.md` files, `docs/`,
`.claude/`, `.codex/`, `.agents/`, and `.githooks/`. Application source and
user-facing content are not checked, so non-English product text keeps its
proper native characters. Harness paths that legitimately need non-ASCII
content go into `.githooks/ascii-allowlist`, one path prefix per line.

Delete `INIT.md` (its job is done once the harness is initialized), then
commit the initialized harness as
`chore(harness): initialize agent-workflow-template` (brownfield: never mix
harness files and application changes in one commit).

## Step 6 - Verify

All of these must hold before you report done:

- `grep -rn "PROJECT_NAME\|PROJECT_PURPOSE\|PROJECT_ARCHITECTURE\|harness-init:" --include="*.md" --include="*.example" --include="pre-commit" .`
  returns nothing outside `.claude/skills/harness-init/`, `.codex/skills/harness-init/`,
  `.agents/skills/harness-init/`, and `docs/templates/`.
- The three skill trees (`.agents/skills/`, `.claude/skills/`,
  `.codex/skills/`) are byte-identical.
- `PLANS.md` carries a real status and today's date, and no legacy plan file
  (for example `PLAN.md`) remains at the root.
- No `*.template` files remain anywhere in the repository.
- `INIT.md` no longer exists.
- `git status` is clean.

Report to the operator: mode used, facts assumed, files customized, the first
spec created, and any open questions.

## Boundaries

- Do not touch existing application code in brownfield mode.
- Do not overwrite existing project files (README, .gitignore, .env.example)
  without showing the operator a merge proposal first.
- Do not invent architecture principles or safety rules; derive them from the
  operator or the code.
