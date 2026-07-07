# Kickoff Prompt - spec02 voicebot observability dashboard

Read `AGENTS.md`, `PLANS.md`, and the governing spec:

```text
docs/specs/spec02-voicebot-observability-dashboard.md
```

Implement the spec end to end. Build a read-only FastAPI plus Tabler dashboard
under `vms/asterisk/services/dashboard/` that runs on the Asterisk VM and reads
the local `/var/lib/voicebot/*.jsonl` sinks. Reuse `vms/asterisk/services/common/`
(`trace_events.read_events`, `usage_summary.PRICE` and `parse_since`, the
`turns.jsonl` parsing); derive per-stage latency from `ts` deltas and prefer a
real `duration_ms` when present; no agent changes and no WebSocket in this spec.
Ship an idempotent installer, a systemd unit, Makefile targets, and a declarative
verify smoke check.

Keep `PLANS.md` updated after meaningful work, preserve user changes, keep
secrets and runtime data out of git, run the relevant checks, and commit all
agent-made changes with an English Conventional Commit.
