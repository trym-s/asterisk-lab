# PLANS.md - asterisk-lab live execution state

> Governed by `docs/runbooks/plan-rules.md`. Keep around 100 to 250 lines.
> Update after every meaningful step. Link artifacts; never paste long output.
> Always carry a state.
> When the governing spec is complete, archive this file under `docs/archive/plan/`.
> The next spec starts with a fresh root `PLANS.md` from `docs/templates/PLANS.md`.

**Status:** Active - spec02 done and archived; only the carried-over spec01
deploy item remains open, tracked here until it lands.
**Governing spec:** `docs/specs/spec01-adopt-agent-harness.md`
**Last updated:** 2026-07-07

## Active milestones

- [ ] Deploy the `/opt/asterisk-lab/current` payload layout to the SBC and
      monitoring VMs and run their verify targets (`make verify-sbc`,
      `make verify-monitoring`). The Asterisk VM already runs this layout
      (confirmed live while deploying spec02's dashboard).

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
