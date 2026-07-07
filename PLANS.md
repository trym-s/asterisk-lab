# PLANS.md - asterisk-lab live execution state

> Governed by `docs/runbooks/plan-rules.md`. Keep around 100 to 250 lines.
> Update after every meaningful step. Link artifacts; never paste long output.
> Always carry a state.
> When the governing spec is complete, archive this file under `docs/archive/plan/`.
> The next spec starts with a fresh root `PLANS.md` from `docs/templates/PLANS.md`.

**Status:** Pending
**Governing spec:** `docs/specs/spec04-livekit-pipecat-fair-comparison.md`
**Last updated:** 2026-07-07

## Active milestones

- [ ] Fairness Gate / Config Diff panel and API endpoint.
- [ ] Paired Quality panel, expected-answer fixture, and API endpoint.
- [ ] Latency Decision panel (p50/p95 with sample floor) and API endpoint.
- [ ] Reliability panel (comparable outcomes vs lane-specific diagnostics)
      and API endpoint.
- [ ] Cost panel (normalized, measured vs estimated) and API endpoint.
- [ ] `run_id` grouping key added across relevant trace events.
- [ ] Live evidence captured for a real or replayed paired run.

## Blockers

- none

## Canonical evidence

- none

## Recent updates

- 2026-07-07 - Created spec04 (LiveKit vs Pipecat fair comparison) from the
  converged Codex/Claude debate in
  `docs/debates/livekit-pipecat-fair-comparison/transcript.md`
  (`discussion_done`), and its kickoff prompt at
  `docs/prompts/spec04-livekit-pipecat-fair-comparison.md`.
- 2026-07-07 - Closed spec03 (voicebot dashboard redesign): implemented,
  deployed, verified live across the Asterisk, SBC, and monitoring VMs,
  archived to
  `docs/archive/plan/2026-07-07-spec03-voicebot-dashboard-redesign.md`, and
  reset the root plan for the next work item.

## Archive pointers

- `docs/archive/plan/2026-07-07-spec01-deploy-sbc-monitoring.md`
- `docs/archive/plan/2026-07-07-spec02-voicebot-observability-dashboard.md`
- `docs/archive/plan/2026-07-07-spec03-voicebot-dashboard-redesign.md`
