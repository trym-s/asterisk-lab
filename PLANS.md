# PLANS.md - asterisk-lab live execution state

> Governed by `docs/runbooks/plan-rules.md`. Keep around 100 to 250 lines.
> Update after every meaningful step. Link artifacts; never paste long output.
> Always carry a state.
> When the governing spec is complete, archive this file under `docs/archive/plan/`.
> The next spec starts with a fresh root `PLANS.md` from `docs/templates/PLANS.md`.

**Status:** Live paired run against real VM extensions is done and proved
the corpus/suite/dashboard rework correct (Pipecat: clean 4/4-turn
conversations both times), but it also surfaced a real LiveKit-lane bug
(participant disconnects after turn 1, both conversations) that blocks
spec04's live-evidence closure. Not a spec05 defect - the corpus, WAV
generation, suite driver, and dashboard scoring all behaved correctly.
**Governing spec:** `docs/specs/spec05-realistic-multiturn-test-corpus.md`
**Predecessor:** `docs/specs/spec04-livekit-pipecat-fair-comparison.md`
(Draft; implementation done, but its live-evidence acceptance criterion
cannot close yet - see Blockers)
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
- [x] Re-run the paired LiveKit/Pipecat suite against the new corpus
      (shared `VOICEBOT_RUN_ID=livekit-pipecat-multiturn-20260708`) and
      capture dashboard evidence (`runtime/spec05-live-evidence/*.json`,
      git-ignored). Confirmed correct: Pipecat completed both 4-turn
      conversations cleanly with correct answers per `expected-answers.json`
      (`comparable_outcomes.pipecat` is 2/2 on every check). Does NOT close
      spec04's criterion - see Blockers.

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

- **LiveKit lane disconnects after turn 1** (blocks spec04 closure, not a
  spec05 defect): both live calls to ext 1099 ended with
  `participant_disconnected` right after the agent answered the first
  turn, well before the script played turns 2-4. Trace events confirm only
  `turn-0001` was ever transcribed; the SIP participant left the LiveKit
  room on its own. `livekit/agent/agent.py` reacts to `participant_disconnected`
  / `room disconnected` events (lines ~276-282) but does not cause them -
  the disconnect itself is upstream (Asterisk<->LiveKit SIP trunk or
  LiveKit SIP gateway). Needs its own investigation/spec; out of scope for
  spec05 (Non-Goals explicitly excludes agent conversational-logic changes).
  Pipecat, driven by the identical corpus and suite, completed both
  4-turn conversations without issue - proving the corpus/suite rework
  itself is not the cause.
- Spec05's Architecture Contract states `conversations.tsv` and its
  generated `audio/*.wav` are "versioned, read-only fixtures tracked in
  git, exactly as `utterances.tsv` and its WAVs were" - but the repo's
  `.gitignore` has a blanket `*.wav` rule, and the old WAVs were in fact
  never tracked in git history either. This is a spec/reality mismatch
  the operator should resolve (either amend the spec's Architecture
  Contract, or add a `.gitignore` exception for `test-caller/audio/`) -
  not something resolved unilaterally here.

## Canonical evidence

- spec04's replayed-fixture evidence remains at
  `runtime/spec04-comparison-verify/` (git-ignored) - still valid for the
  panel-rendering behavior it covers.
- spec05's live evidence (git-ignored): `runtime/spec05-live-evidence/*.json`
  - `/api/comparison/{fairness,quality,latency,reliability,cost}` responses
    for `run_id=livekit-pipecat-multiturn-20260708`, captured 2026-07-08
    against real VM extensions 1099 (LiveKit) and 1098 (Pipecat), after the
    VM-side log cleanup below. Proves the corpus/generator/suite/
    reliability-scoring rework correct (Paired Quality panel matches both
    lanes' turn-1 answers against `expected-answers.json` with
    `match_score: 1.0`); also proves the LiveKit-lane disconnect bug above
    (real, not a scoring
    artifact - trace events show the SIP participant left the room after
    turn 1's response, both conversations).

## VM-side data hygiene

- 2026-07-08 - Pruned `/var/lib/voicebot/{events,usage}.jsonl` on the
  Asterisk VM down to only `run_id=livekit-pipecat-multiturn-20260708`
  (108/2018 event rows, 56/1447 usage rows kept), at operator request, so
  the dashboard's default no-`run_id` comparison view is no longer mixed
  with ~95 old calls (manual talk-tests, the old single-utterance corpus,
  and the earlier `spec04-live-20260708-102331` run). Originals backed up
  to `/var/lib/voicebot/backup-20260708/` on the VM before pruning.
  `turns.jsonl` was left untouched - grepped `main.py` and confirmed no
  `/api/comparison/*` endpoint reads `settings.turns_path`, so it cannot
  pollute the comparison panels. Verified both the scoped and default
  views post-prune return identical, clean results.

## Recent updates

- 2026-07-08 - Ran the live paired suite against real VM extensions
  (deploying the spec05 rework first: `make deploy`, `deploy-voicebot-livekit`,
  `deploy-voicebot-pipecat`, `deploy-voicebot-dashboard`; generated all 8
  turn WAVs via ElevenLabs with no truncation-guard retries needed;
  registered a host baresip as 1001/1002 through the SBC). LiveKit (1099)
  and Pipecat (1098) each dialed both conversations once with a shared
  `VOICEBOT_RUN_ID`. Result: Pipecat completed both 4-turn conversations
  correctly (verified against `expected-answers.json`); LiveKit
  disconnected after turn 1 both times (see Blockers) - a real lane bug,
  not a corpus/suite defect. While reviewing the reliability evidence,
  found and fixed (commit `501a2e7`) a related dashboard bug: both agents
  tag the greeting with `turn_id="greeting"`, which `list_calls` and
  `reliability_summary` were counting as a real turn - this inflated
  turn_count by one on every call, so it initially misreported Pipecat's
  clean 4-turn run as having a duplicate/extra turn and every call
  (both lanes) as missing stt/llm stages. Fixed by excluding the sentinel
  turn_id in both places, with unit tests; 25/25 dashboard tests pass.
  Evidence and the resulting blocker are recorded above.
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
