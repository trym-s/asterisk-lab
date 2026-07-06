---
name: spec-driven-execution
description: Use when starting, resetting, or continuing a large or product-level initiative that should be governed by a spec under docs/specs and executed through the root PLANS.md. Covers deciding whether a spec is needed, creating the spec and kickoff prompt, plan discipline, archive-on-close, memory promotion, and TODO reconciliation.
---

# Spec-Driven Execution

The master workflow for large work in this repository: contract first
(spec), then execution state (PLANS.md), then durable knowledge
(docs/memory). Follow it start to finish; do not skip the closure steps.

## Read First

- `AGENTS.md`
- `PLANS.md`
- `docs/runbooks/spec-rules.md` and `docs/runbooks/plan-rules.md`
- Relevant `docs/memory/*` files

## Workflow

1. Decide whether a spec is needed. A spec is required when the work is
   large, risky, multi-step, operationally significant, or changes a
   contract (behavior, schema, API, routing, deployment topology). Small
   tasks skip specs and are tracked through commits and `PLANS.md`.
2. Check for an existing governing spec under `docs/specs/` before creating
   one; continue it if the work belongs there.
3. Create the spec as `docs/specs/specNN-topic.md` from
   `docs/templates/spec-template.md`, using the next unused number. Make it
   decision-complete: goal, scope, non-goals, constraints, acceptance
   criteria, required evidence, risks.
4. Create the paired kickoff prompt as `docs/prompts/specNN-topic.md` from
   `docs/templates/spec-kickoff-prompt-template.md`. Keep it short; it must
   not duplicate the spec.
5. Reset or update the root `PLANS.md` from `docs/templates/PLANS.md`: point
   it at the governing spec, set Status, list the active milestones as
   checkboxes.
6. Execute. Update `PLANS.md` after every meaningful step; link evidence
   (under ignored `runtime/`), never paste long output. Commit continuously
   in Conventional Commit style.
7. Do not declare done until the spec's acceptance criteria and the
   `AGENTS.md` Done Criteria all hold.
8. Close: archive `PLANS.md` to `docs/archive/plan/YYYY-MM-DD-topic.md`,
   start a fresh `PLANS.md` from the template, and mark the spec's status.
9. Promote proven, reusable findings into `docs/memory/*`; record decisions
   as `DEC-NNN` entries (Decision / Reason / Impact).
10. Reconcile `TODO.md` with operator approval: propose closing satisfied
    topics and opening newly discovered deferred ones.
11. Re-read `AGENTS.md` and propose updates if this work changed a durable
    rule.

## Boundaries

- Do not turn the spec into a changelog; it is a stable contract.
- Do not let `PLANS.md` copy the whole spec; it links to it.
- Do not reuse or renumber spec numbers; superseded specs point to their
  replacement.
- Do not edit `TODO.md` without operator approval.
