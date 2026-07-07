# PLANS.md - asterisk-lab live execution state

> Governed by `docs/runbooks/plan-rules.md`. Keep around 100 to 250 lines.
> Update after every meaningful step. Link artifacts; never paste long output.
> Always carry a state.
> When the governing spec is complete, archive this file under `docs/archive/plan/`.
> The next spec starts with a fresh root `PLANS.md` from `docs/templates/PLANS.md`.

**Status:** Active - spec02 voicebot observability dashboard authored; implementation pending.
**Governing spec:** `docs/specs/spec02-voicebot-observability-dashboard.md`
**Last updated:** 2026-07-07

## Active milestones

- [x] Author `docs/specs/spec02-voicebot-observability-dashboard.md` (9 sections,
      decision-complete) and its paired kickoff prompt under `docs/prompts/`.
- [ ] Scaffold the read-only FastAPI service under
      `vms/asterisk/services/dashboard/` (app + Jinja2 + vendored Tabler/chart assets).
- [ ] Build the data layer reusing `vms/asterisk/services/common/`
      (`trace_events.read_events`, `usage_summary.PRICE`/`parse_since`, `turns.jsonl`).
- [ ] Implement latency derivation from `ts` deltas per `(lane, call_id, turn_id)`,
      preferring a real `duration_ms` when present.
- [ ] Ship the four panels: parity, cost/usage, transcript, batch transcriber.
- [ ] Add installer + systemd unit + Makefile targets + declarative verify smoke check.
- [ ] Prove live behavior with a real or replayed call; link evidence under `runtime/`.

## Blockers

- none

## Carried over from spec01 (still Active)

- [ ] Deploy the new `/opt/asterisk-lab/current` payload layout to all live VMs
      and run verify targets. Tracked against `docs/specs/spec01-adopt-agent-harness.md`,
      which remains Active until this lands. Not superseded by spec02.

## Canonical evidence

- `docs/specs/spec02-voicebot-observability-dashboard.md` defines the dashboard
  contract; `docs/prompts/spec02-voicebot-observability-dashboard.md` is its kickoff.
- Telemetry sources already exist on the Asterisk VM:
  `/var/lib/voicebot/{events,usage,turns}.jsonl`
  (`events.jsonl` schema `voicebot-events-v1`).
- `docs/memory/decisions.md` DEC-001..DEC-007 documents governance and the
  `/opt/asterisk-lab/current` + `/etc/asterisk-lab/env` deploy boundary.

## Recent updates

- 2026-07-07 - Authored spec02 (voicebot observability dashboard, v1): FastAPI +
  Tabler on the Asterisk VM, reads local JSONL, derived per-stage latency,
  polling refresh, four panels. Real per-stage instrumentation and live streaming
  were split out as separate follow-up specs. Repointed the governing spec to
  spec02 and carried spec01's open deploy milestone forward.
- 2026-07-06 - Started deploy layout migration: role payloads now target
  `/opt/asterisk-lab/current`, VM env loads from `/etc/asterisk-lab/env`,
  and `deploy/rsync/*.filter` keeps docs/harness/secrets out of VM payloads.
- 2026-07-06 - Added simplified VM management (virsh) targets (`vms`, `ips`,
  `up`, `down`, `up-sbc`, `down-sbc`, `up-mon`, `down-mon`) to the `Makefile`.
- 2026-07-06 - Harness initialized from agent-workflow-template; `docs/specs/`
  established as the single spec surface (DEC-002).

## Archive pointers

- none
