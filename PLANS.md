# PLANS.md - asterisk-lab live execution state

> Governed by `docs/runbooks/plan-rules.md`. Keep around 100 to 250 lines.
> Update after every meaningful step. Link artifacts; never paste long output.
> Always carry a state.
> When the governing spec is complete, archive this file under `docs/archive/plan/`.
> The next spec starts with a fresh root `PLANS.md` from `docs/templates/PLANS.md`.

**Status:** Pending - spec01 and spec02 are both Done and archived. No
governing spec is active; all three VMs (Asterisk, SBC, monitoring) are on
the same deploy revision (`aaa08c5f1d68`) with `make verify`/`verify-sbc`/
`verify-monitoring` all green.
**Governing spec:** none
**Last updated:** 2026-07-07

## Active milestones

- [ ] Define active work.

## Blockers

- none

## Canonical evidence

- `docs/specs/spec01-adopt-agent-harness.md` and
  `docs/specs/spec02-voicebot-observability-dashboard.md` are both Done.
- `docs/memory/decisions.md` DEC-001..DEC-008 covers governance, the deploy
  boundary, and the read-vs-write default-path gotcha found while verifying
  spec02 live.

## Recent updates

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
