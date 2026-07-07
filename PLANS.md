# PLANS.md - asterisk-lab live execution state

> Governed by `docs/runbooks/plan-rules.md`. Keep around 100 to 250 lines.
> Update after every meaningful step. Link artifacts; never paste long output.
> Always carry a state.
> When the governing spec is complete, archive this file under `docs/archive/plan/`.
> The next spec starts with a fresh root `PLANS.md` from `docs/templates/PLANS.md`.

**Status:** In progress - implementation done, live VM evidence pending
**Governing spec:** `docs/specs/spec04-livekit-pipecat-fair-comparison.md`
**Last updated:** 2026-07-07

## Active milestones

- [x] Fairness Gate / Config Diff panel and API endpoint
      (`GET /api/comparison/fairness`, `data.fairness_gate`).
- [x] Paired Quality panel, expected-answer fixture, and API endpoint
      (`vms/asterisk/services/test-caller/expected-answers.json`,
      `GET /api/comparison/quality`, `data.paired_quality`, STT-text-to
      -utterance matching since agents don't stamp `utterance_id`).
- [x] Latency Decision panel (p50/p95 with sample floor) and API endpoint
      (`GET /api/comparison/latency`, `data.latency_decision`,
      `VOICEBOT_DASHBOARD_LATENCY_MIN_N`).
- [x] Reliability panel (comparable outcomes vs lane-specific diagnostics)
      and API endpoint (`GET /api/comparison/reliability`,
      `data.reliability_summary`; `expected_turns_per_call` defaults to 1,
      matching run-suite.sh's one-call-per-utterance design).
- [x] Cost panel (normalized, measured vs estimated) and API endpoint
      (`GET /api/comparison/cost`, `data.cost_normalized`).
- [x] `run_id` grouping key added to `call.started`/`profile.loaded` in
      both lane agents via `VOICEBOT_RUN_ID` env
      (`trace_events.current_run_id()`); additive field, omitted when unset.
- [x] New `/comparison` page (`comparison.html`) replaces `/parity` as the
      primary nav link; `/parity` kept as an unlinked legacy alias.
- [x] `verify.sh` extended with checks for all 5 new endpoints + the page;
      `.env.example` carries `VOICEBOT_RUN_ID`,
      `VOICEBOT_DASHBOARD_LATENCY_MIN_N`,
      `VOICEBOT_DASHBOARD_EXPECTED_CORPUS_PATH` (names/defaults only).
- [x] Unit tests for all new `data.py` functions (21/21 dashboard tests,
      6/6 common tests pass) plus `ruff check` clean on all changed Python.
- [x] Live evidence captured for a *replayed* paired run (synthetic
      fixture, both lanes, shared `run_id`, local uvicorn instance) - see
      Canonical evidence. Real end-to-end evidence from an actual VM
      `run-suite.sh` pair (LiveKit ext 1099 + Pipecat ext 1098 against the
      same corpus, `VOICEBOT_RUN_ID` set identically) is still pending -
      this session had no VM access.

## Blockers

- None for the implementation. Still open: a real (not replayed) paired
  run captured on the Asterisk VM to close the spec's live-evidence
  acceptance criterion end-to-end, plus `make verify-voicebot-dashboard`
  run on the deployed service.

## Canonical evidence

- `runtime/spec04-comparison-verify/` (git-ignored): synthetic paired-run
  fixture (`events.jsonl`, `usage.jsonl`, shared `run_id`), plus captured
  responses from all 5 new endpoints (`fairness.json`, `quality.json`,
  `latency.json`, `reliability.json`, `cost.json`) and rendered
  `comparison_page.html` / `parity_page.html`, from a local
  `uvicorn main:app` run against that fixture. Confirms: fairness rows
  render `pass`/`warn`/`not_enforced` (never a forced pass on media/VAD/
  framework-version rows, `framework_isolated: false`); paired quality
  scores utterance `03-havlu-fiyat` correctly on both lanes side by side;
  latency shows `N` with p95 suppressed below the 20-sample floor;
  reliability's comparable-outcomes counts are populated for both lanes
  while `echo_filtered` stays isolated to pipecat's lane-specific row;
  cost keeps livekit (`measured`) and pipecat (`mixed` - estimated LLM +
  measured STT) rows separate.

## Recent updates

- 2026-07-07 - Implemented spec04 end to end: Fairness Gate, Paired
  Quality, Latency Decision, Reliability (two-row split), and Cost panels
  on the dashboard; `run_id` grouping key; expected-answer fixture; 5 new
  `/api/comparison/*` endpoints; `/comparison` page. Verified with unit
  tests, `ruff check`, and a replayed-fixture live run (see Canonical
  evidence above). Real VM evidence and `make verify-voicebot-dashboard`
  against the deployed service are the remaining gap before closing the
  spec.
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
