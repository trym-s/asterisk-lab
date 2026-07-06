# Kickoff Prompt - spec01 adopt-agent-harness

Read `AGENTS.md`, `PLANS.md`, and the governing spec:

```text
docs/specs/spec01-adopt-agent-harness.md
```

Complete the harness adoption end to end. Do not touch application code
under `asterisk/`, `sbc/`, `monitoring/`, `services/`, `scripts/`,
`infra/`, `install.sh`, or `Makefile`. Do not migrate or renumber the
existing `specs/` domain contract tree.

Concretely:

1. Verify AGENTS.md sections 1-10 reflect the real project; add any
   missing project-specific rule surfaced during the review.
2. Verify `docs/memory/decisions.md` DEC-001..DEC-006; add follow-up
   DEC-* entries only when the operator confirms a new decision.
3. Verify `docs/architecture/app-architecture.md` still matches the
   deployed layout; update it if any component or boundary changed.
4. Verify the pre-commit hook works: try a no-op commit with a Claude
   or Codex identity; expect the hook to accept it. Try a commit that
   would introduce a non-ASCII character in a harness file (outside
   the allowlist); expect the hook to reject it.
5. Verify the spec-boundary check: try a commit that adds `spec01` to
   an application-source path; expect the hook to reject it.
6. Update `PLANS.md` after each meaningful step; mark milestones done
   only when their evidence is in place.
7. Preserve user changes. Keep secrets and runtime data out of git.
8. Run `make verify`, `make verify-sbc`, and `make verify-monitoring`
   on the target VMs if any change lands that could affect them; the
   initialization commit itself does not need runtime evidence because
   it does not touch application code.
9. Commit all agent-made changes as
   `chore(harness): initialize agent-workflow-template`
   in a single commit (no application-code mixing).
