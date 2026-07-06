# Spec Rules

`docs/specs/` is the single spec surface in this repository (see DEC-002).

## `docs/specs/` - governing specs

- Large, risky, multi-step, operationally significant, or
  contract-defining work gets a spec under `docs/specs/`.
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
