# Global Conventions

## Source Files

- Edit `asterisk/*.tmpl`, never rendered `/etc/asterisk/*`.
- Edit `sbc/*.tmpl`, never rendered `/etc/opensips/*` or `/etc/rtpengine/*`.
- Edit `monitoring/*.tmpl` and `monitoring/*.sh`, never rendered monitoring
  service files expecting them to survive re-install.

## Commands

- Use Makefile targets as the operator interface when available.
- Keep install scripts idempotent.
- Keep verify scripts declarative and direct; avoid short-circuit pipelines that
  break under `set -o pipefail`.

## Documentation

- Put current behavior in domain specs.
- Put acceptance criteria in contracts.
- Put procedure in runbooks.
- Put rationale in decisions.
- Do not duplicate acceptance criteria into README or PROCESS.

## Agent Discipline

- Before a code change, identify affected domain contracts.
- If a behavior changes, update the matching spec and contract in the same
  change set.
- If validation evidence changes, update `global/validation.md` or the domain
  runbook instead of burying the lesson in a one-off note.
