# PLANS.md - asterisk-lab live execution state

> Governed by `docs/runbooks/plan-rules.md`. Keep around 100 to 250 lines.
> Update after every meaningful step. Link artifacts; never paste long output.
> Always carry a state.
> When the governing spec is complete, archive this file under `docs/archive/plan/`.
> The next spec starts with a fresh root `PLANS.md` from `docs/templates/PLANS.md`.

**Status:** Pending - spec03 (voicebot dashboard redesign) is drafted and
ready for implementation. spec01 and spec02 are both Done and archived; all
three VMs (Asterisk, SBC, monitoring) are on the same deploy revision
(`aaa08c5f1d68`) with `make verify`/`verify-sbc`/`verify-monitoring` all
green.
**Governing spec:** `docs/specs/spec03-voicebot-dashboard-redesign.md` (Draft)
**Last updated:** 2026-07-07

## Active milestones

- [ ] Implement spec03: Overview KPI tiles (cost, VM uptime/downtime, active
  calls), merged Calls transcript-status badges, animated call-detail flow,
  cost trend + drill-down, Zabbix host-uptime item, and the
  call/recording correlation field in both lane agents.

## Blockers

- none

## Canonical evidence

- `docs/specs/spec01-adopt-agent-harness.md` and
  `docs/specs/spec02-voicebot-observability-dashboard.md` are both Done.
- `docs/memory/decisions.md` DEC-001..DEC-008 covers governance, the deploy
  boundary, and the read-vs-write default-path gotcha found while verifying
  spec02 live.

## Recent updates

- 2026-07-07 - Drafted spec03 (voicebot dashboard redesign) after a
  brainstorming session with the operator: Overview KPI tiles, merged
  live/batch transcript status on the Calls page, an animated call-detail
  flow, a cost trend + drill-down view, a new Zabbix host-uptime item, and
  the Asterisk channel/uniqueid correlation field on both lane agents'
  `call`-stage trace event. Paired kickoff prompt at
  `docs/prompts/spec03-voicebot-dashboard-redesign.md`.
- 2026-07-07 - Closed spec01: deployed the current `/opt/asterisk-lab/current`
  payload to the SBC and monitoring VMs (`make deploy-sbc`,
  `make deploy-monitoring`); `vms/sbc/verify.sh` (11/11) and
  `vms/monitoring/verify.sh` (20/20) both passed. All three VMs now match
  revision `aaa08c5f1d68`. Archived the prior `PLANS.md` to
  `docs/archive/plan/2026-07-07-spec01-deploy-sbc-monitoring.md` and marked
  spec01 Done.
- 2026-07-07 - Closed spec02 (voicebot observability dashboard): deployed
  and verified live on the Asterisk VM (12/12 `verify.sh` checks; all four
  panels proven against 33 real calls already on disk). Archived to
  `docs/archive/plan/2026-07-07-spec02-voicebot-observability-dashboard.md`.

## Archive pointers

- `docs/archive/plan/2026-07-07-spec01-deploy-sbc-monitoring.md`
- `docs/archive/plan/2026-07-07-spec02-voicebot-observability-dashboard.md`
