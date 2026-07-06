# Spec Rules

Two spec surfaces coexist in this repository (see DEC-002).

## `specs/` - authoritative domain contracts

- `specs/global/` holds mission, conventions, environment, validation,
  agent routing, and global VAL-* contracts.
- `specs/domains/<domain>/spec.md` holds the current supported behavior
  for a subsystem.
- `specs/domains/<domain>/contracts/VAL-*.md` files hold falsifiable
  acceptance criteria and required evidence surfaces.
- `specs/domains/<domain>/runbook.md` holds operator and agent procedure.
- `specs/domains/<domain>/decisions.md` holds durable rationale local to
  the domain.
- `specs/changes/NNNN-topic.md` holds change proposals and migrations;
  they are not current truth by themselves.
- Numbering under `specs/changes/` is sequential (four-digit,
  zero-padded); numbers are never reused.

## `docs/specs/` - cross-cutting harness or programme specs

- Large, risky, multi-step, operationally significant, or
  contract-defining work that spans domains or evolves the harness
  itself gets a spec under `docs/specs/`.
- Use the next unused `specNN-topic.md` filename (two-digit).
- Create a matching kickoff prompt under `docs/prompts/`.
- Spec numbers are never reused.
- Specs are stable contracts, not daily logs; daily progress belongs in
  `PLANS.md`.
- The `specNN` token may appear only in `docs/specs/`, `docs/prompts/`,
  root workflow files (`PLANS.md`, `AGENTS.md`), and links to those
  documents. The pre-commit hook enforces this boundary on application
  paths.
- Completed specs stay in the repo. Superseded specs point to their
  replacement.
