# PLANS.md - asterisk-lab live execution state

> Governed by `docs/runbooks/plan-rules.md`. Keep around 100 to 250 lines.
> Update after every meaningful step. Link artifacts; never paste long output.
> Always carry a state.
> When the governing spec is complete, archive this file under `docs/archive/plan/`.
> The next spec starts with a fresh root `PLANS.md` from `docs/templates/PLANS.md`.

**Status:** Done - spec02 implemented, deployed, and verified live on the
Asterisk VM against real call data. Archived.
**Governing spec:** `docs/specs/spec02-voicebot-observability-dashboard.md`
**Last updated:** 2026-07-07

## Active milestones

- [x] Author `docs/specs/spec02-voicebot-observability-dashboard.md` (9 sections,
      decision-complete) and its paired kickoff prompt under `docs/prompts/`.
- [x] Scaffold the read-only FastAPI service under
      `vms/asterisk/services/dashboard/` (app + Jinja2 + vendored Tabler/Chart.js,
      no Node/build chain).
- [x] Build the data layer reusing `vms/asterisk/services/common/`
      (`trace_events.read_events`/`validate_event`, `usage_summary.PRICE`/`parse_since`).
- [x] Implement latency derivation from `ts` deltas per `(lane, call_id, turn_id)`,
      preferring a real `duration_ms` when present (unit-tested in `tests/test_data.py`).
- [x] Ship the four panels: parity, cost/usage, transcript, batch transcriber
      (plus an overview/calls list page).
- [x] Add installer (uv-managed venv, not requirements.txt) + systemd unit +
      Makefile targets (`install/verify/deploy/logs-voicebot-dashboard`) +
      declarative `verify.sh` smoke check.
- [x] Prove live behavior on the Asterisk VM. The VM came up mid-session;
      deployed via `make deploy-voicebot-dashboard`, `verify.sh` passed 12/12
      against the real service, and all four panels rendered real STT/LLM/TTS
      text, latency, and cost from 33 pre-existing calls (both lanes) already
      on disk in `/var/lib/voicebot/events.jsonl`. Evidence captured under
      ignored `runtime/spec02-dashboard-verify/` (verify.log, api-*.json).

## Fixes found during live verification

- `config.py` originally called `trace_events.default_events_path()` /
  `usage.LOG_PATH`, whose fallback logic checks *write* access to
  `/var/lib/voicebot` (correct for the writer agents, wrong for a read-only
  consumer running as `asterisk`, which can read but not write that
  root-owned dir). This silently served an empty per-user path instead of
  the real log, and `/api/calls` returned `[]` against 1043 real events.
  Fixed by resolving read paths independently in `config.py`; recorded as
  DEC-008 in `docs/memory/decisions.md`.
- The dashboard's first deploy leaked a local dev `.venv` (32 MB) and a
  `.ruff_cache` into the VM payload because `infra/deploy/*.filter` excluded
  `__pycache__`/`.rendered`/`.claude` but not `.venv`/`.ruff_cache`/
  `.pytest_cache` (only `.gitignore` excluded those, which rsync does not
  read). Fixed in all three filters (asterisk/sbc/monitoring); a redeploy
  confirmed `--delete` removed the stray directories.

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
- `vms/asterisk/services/dashboard/` is the implemented dashboard service;
  `tests/test_data.py` covers latency derivation, call/turn grouping, cost
  summary, and transcriber status. `install.sh`/`verify.sh` are shellcheck-clean.

## Recent updates

- 2026-07-07 - Implemented spec02: FastAPI + Tabler dashboard under
  `vms/asterisk/services/dashboard/` (overview/parity/cost/transcript/transcriber
  pages, `/api/*` JSON backing them), reusing `trace_events`/`usage_summary`
  from `services/common/`. Latency derivation groups `events.jsonl` by
  `(lane, call_id, turn_id)`, orders by `ts`, and prefers a real `duration_ms`
  over the derived delta. Dependency management uses `uv` (pyproject.toml +
  uv.lock), not requirements.txt. Installer mirrors the transcriber precedent
  (venv + systemd unit, not a container) with an optional basic-auth env
  toggle. Verified locally against synthetic JSONL fixtures (ruff clean,
  shellcheck clean, 6/6 unit tests, all pages and API endpoints return
  correct shapes); live-VM proof is the one open item (see Blockers).
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
