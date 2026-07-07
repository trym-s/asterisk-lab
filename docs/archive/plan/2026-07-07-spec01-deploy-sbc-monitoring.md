# PLANS.md - asterisk-lab live execution state

> Governed by `docs/runbooks/plan-rules.md`. Keep around 100 to 250 lines.
> Update after every meaningful step. Link artifacts; never paste long output.
> Always carry a state.
> When the governing spec is complete, archive this file under `docs/archive/plan/`.
> The next spec starts with a fresh root `PLANS.md` from `docs/templates/PLANS.md`.

**Status:** Done - spec01 fully closed; SBC and monitoring VMs now run the
current `/opt/asterisk-lab/current` payload at the same revision as Asterisk.
**Governing spec:** `docs/specs/spec01-adopt-agent-harness.md`
**Last updated:** 2026-07-07

## Active milestones

- [x] Deploy the `/opt/asterisk-lab/current` payload layout to the SBC and
      monitoring VMs and run their verify targets. `make deploy-sbc` and
      `make deploy-monitoring` ran clean; `vms/sbc/verify.sh` passed 11/11 on
      the SBC VM and `vms/monitoring/verify.sh` passed 20/20 on the
      monitoring VM. All three VMs (Asterisk, SBC, monitoring) now report
      `.deploy-revision` = `aaa08c5f1d68`. Evidence under ignored
      `runtime/spec01-deploy-sbc-monitoring/` (verify-sbc.log,
      verify-monitoring.log, verify-zabbix-agent-asterisk.log,
      deploy-revisions.txt).

## Blockers

- none

## Canonical evidence

- `docs/specs/spec01-adopt-agent-harness.md` defines the harness/layout
  contract this item closes out.
- `docs/memory/decisions.md` DEC-004/DEC-007 document the `/opt/asterisk-lab/current`
  + `/etc/asterisk-lab/env` deploy boundary; DEC-008 documents a read-path
  gotcha discovered while verifying spec02 live.

## Recent updates

- 2026-07-07 - Closed out spec02 (voicebot observability dashboard): deployed
  and verified live on the Asterisk VM (12/12 `verify.sh` checks; all four
  panels proven against 33 real calls already on disk). Archived the prior
  `PLANS.md` to `docs/archive/plan/2026-07-07-spec02-voicebot-observability-dashboard.md`
  and marked the spec Done. Carried spec01's remaining SBC/monitoring deploy
  item forward as the only open work.

## Archive pointers

- `docs/archive/plan/2026-07-07-spec02-voicebot-observability-dashboard.md`
