# PLANS.md - asterisk-lab live execution state

> Governed by `docs/runbooks/plan-rules.md`. Keep around 100 to 250 lines.
> Update after every meaningful step. Link artifacts; never paste long output.
> Always carry a state.
> When the governing spec is complete, archive this file under `docs/archive/plan/`.
> The next spec starts with a fresh root `PLANS.md` from `docs/templates/PLANS.md`.

**Status:** In progress - corpus/generator/suite rework implemented and
committed; old per-utterance WAVs intentionally left in place (operator
deferred cleanup); live re-run against real VMs not started
**Governing spec:** `docs/specs/spec05-realistic-multiturn-test-corpus.md`
**Predecessor:** `docs/specs/spec04-livekit-pipecat-fair-comparison.md`
(Draft; implementation done, but its live-evidence acceptance criterion is
now closed by spec05, not independently - see spec05 References)
**Last updated:** 2026-07-08

## Active milestones

- [x] Replace `utterances.tsv` with `conversations.tsv`
      (`vms/asterisk/services/test-caller/`): two 4-turn Turkish
      conversations (`magaza-sorular`, `kargo-iade-sorular`), facts grounded
      in `vms/asterisk/services/common/docs/magaza/*.md`.
- [x] Update `gen-utterances.sh`: read `conversations.tsv`, switch
      `ELEVENLABS_MODEL_ID` default to `eleven_multilingual_v2`, add an
      `ffmpeg silencedetect` truncation guard with one automatic
      regenerate-once retry and a hard fail on persistent truncation.
- [x] Restructure `run-suite.sh`: dial once per `conversation_id`, play all
      turns in sequence without hanging up between them, hang up only after
      the last turn's settle window.
- [x] Update `expected-answers.json` for the new corpus content and per-turn
      `utterance_id`s (schema/scoring mechanism unchanged).
- [x] Fix `reliability_summary()`'s `expected_turns_per_call` handling
      (`vms/asterisk/services/dashboard/app/data.py`) so 4-turn calls are
      correctly counted, with a unit test proving it.
- [ ] Remove old `utterances.tsv` and its per-utterance WAVs
      (`01-greeting.wav` .. `07-thanks-hangup.wav`); keep `00-silence.wav`.
      `utterances.tsv` itself is removed (committed in `d1a8560`); the WAVs
      under `vms/asterisk/services/test-caller/audio/` are gitignored
      runtime artifacts and were deliberately left in place per operator
      choice on 2026-07-08 - delete manually or let `gen-utterances.sh`
      overwrite them on next run.
- [ ] Re-run the paired LiveKit/Pipecat suite against the new corpus
      (shared `VOICEBOT_RUN_ID`) and recapture dashboard evidence, closing
      spec04's live-evidence acceptance criterion.

## Prerequisite fixes (confirmed already committed in `f50485b`)

- [x] `_filter_run()` fix in `vms/asterisk/services/dashboard/app/data.py`:
      `run_id` is only stamped on `call.started`/`profile.loaded`, not on
      every event a call emits, so scoping goes through `call_id`
      membership rather than filtering rows directly on `row.get("run_id")`.
- [x] `VOICEBOT_RUN_ID` passthrough in both
      `vms/asterisk/services/livekit/docker-compose.yml` and
      `vms/asterisk/services/pipecat/docker-compose.yml` (was set by
      `run-suite.sh` but previously never reached the containers).

## Blockers

- None yet for spec05 itself. Live evidence (Acceptance Criteria) needs
  actual Asterisk VM access (LiveKit ext 1099, Pipecat ext 1098) once the
  corpus/generator/suite rework lands.

## Canonical evidence

- spec04's replayed-fixture evidence remains at
  `runtime/spec04-comparison-verify/` (git-ignored) - still valid for the
  panel-rendering behavior it covers, but does not satisfy spec04's or
  spec05's live-evidence criteria (real VM run, multi-turn corpus,
  silencedetect-verified audio). No spec05 evidence captured yet.

## Recent updates

- 2026-07-08 - Implemented and committed (`d1a8560`) the spec05
  corpus/generator/suite rework: `conversations.tsv`, the truncation-guarded
  `gen-utterances.sh`, the per-conversation `run-suite.sh`, the regrouped
  `expected-answers.json`, and `reliability_summary()`'s
  `expected_turns_for_corpus()` fix with unit tests (24/24 dashboard tests
  pass, ruff and shellcheck clean). Confirmed the two "prerequisite fixes"
  were already committed in `f50485b` (PLANS.md had gone stale on that
  point). Left the old per-utterance WAVs under `test-caller/audio/` in
  place at operator request (deferred cleanup, not a blocker). Still open:
  the live re-run against real VM extensions.
- 2026-07-08 - Created spec05 (realistic multi-turn test corpus) after the
  operator, while gathering spec04's first real (non-replayed) live VM
  evidence, found (a) generated WAV audio truncating mid-sentence and (b)
  the single-utterance-per-call corpus never exercising multi-turn
  behavior. Kickoff prompt at
  `docs/prompts/spec05-realistic-multiturn-test-corpus.md`. Reset root plan
  to govern spec05; carried forward two uncommitted bug fixes discovered
  during that live-evidence attempt (see Prerequisite fixes above) as the
  starting point.
- 2026-07-07 - Implemented spec04 end to end: Fairness Gate, Paired
  Quality, Latency Decision, Reliability (two-row split), and Cost panels
  on the dashboard; `run_id` grouping key; expected-answer fixture; 5 new
  `/api/comparison/*` endpoints; `/comparison` page. Verified with unit
  tests, `ruff check`, and a replayed-fixture live run. Real VM evidence
  turned out to require the spec05 corpus/generator rework first, so
  spec04 stays open (Draft) until spec05 closes its live-evidence
  criterion.
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
