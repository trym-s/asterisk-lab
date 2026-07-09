# PLANS.md - asterisk-lab live execution state

> Governed by `docs/runbooks/plan-rules.md`. Keep around 100 to 250 lines.
> Update after every meaningful step. Link artifacts; never paste long output.
> Always carry a state.
> When the governing spec is complete, archive this file under `docs/archive/plan/`.
> The next spec starts with a fresh root `PLANS.md` from `docs/templates/PLANS.md`.

**Status:** Live paired run proved the corpus/suite/dashboard rework
correct, then surfaced and fixed a real bug in `run-suite.sh` itself
(baresip's silent RTP gap between turns was tripping LiveKit SIP's
media-inactivity watchdog). Re-verified live after the fix: LiveKit went
from disconnecting after turn 1 on every call to completing one
conversation fully (4/4) and the other to 3/4. spec04's live-evidence
criterion still cannot close - see Blockers for the residual gap.
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
      (shared `VOICEBOT_RUN_ID`) and capture dashboard evidence
      (`runtime/spec05-live-evidence/*.json`, git-ignored). First pass
      (`run_id=...-20260708`): Pipecat completed both 4-turn conversations
      cleanly (2/2 on every `comparable_outcomes` check); LiveKit
      disconnected after turn 1 on both calls - root-caused (see Blockers
      history) and fixed in `run-suite.sh` (commit `134cc2f`). Second pass
      after the fix (`run_id=...-20260708-v2`, now the only data kept on
      the VM): LiveKit reached 4/4 turns on one conversation, 3/4 on the
      other - no more media-timeout disconnects, but still does NOT close
      spec04's criterion - see Blockers for the residual gap.

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

- **RESOLVED - root cause was `run-suite.sh`, not the LiveKit agent:**
  the first live pass had both LiveKit calls end with
  `participant_disconnected` right after turn 1. `lk-sip`'s own container
  logs pinned it precisely: `media_port.go: "triggering media timeout"`,
  `sinceLast: 15.000869487s`, `"SIP call ended", "reason": "media-timeout"`.
  baresip's `aufile` ausrc stops emitting RTP entirely at EOF instead of
  looping, so the caller leg went fully silent for the whole `SETTLE`
  window between turns; LiveKit's SIP gateway (`lk-sip` v1.6.0) has a
  hardcoded ~15s RTP-inactivity watchdog that kills a call it thinks is
  dead - unrelated to conversation content. Pipecat's transport
  (AudioSocket, a local Asterisk<->container TCP stream) has no such
  SIP-layer watchdog, which is why it sailed through the identical corpus
  and suite while LiveKit died every time. Fixed in `run-suite.sh`
  (commit `134cc2f`): re-arm the silence primer every second through the
  settle window so RTP never actually goes dead.
- **Residual, milder gap (open):** after the fix, one LiveKit conversation
  completed all 4 turns cleanly; the other reached only 3/4 - not a
  media-timeout this time (`lk-sip` log shows `"reason": "hangup"`, i.e.
  our own script's deliberate end-of-conversation hangup fired before turn
  4 was captured). Cause: `run-suite.sh`'s per-turn wait is a fixed
  `dur + SETTLE` timer, not an "agent finished speaking" signal; turn-level
  trace timestamps for that call show the agent's own STT-to-TTS round
  trip and speech length repeatedly running close to or past the 15s
  settle budget (compounded by an STT mishearing on turn 2 - the towel
  question's opening word came through garbled, sending the tool lookup
  down the wrong path), so cumulative drift across 4 turns
  ate into the last turn's window. This is a suite-timing tuning question
  (bump `SETTLE`, or make the wait adaptive) rather than a fresh bug;
  deferred to the operator rather than fixed unilaterally this session.
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
  - Current content is the post-fix pass (`run_id=...-20260708-v2`,
    default/no-`run_id` view since that's now the only data on the VM):
    `comparable_outcomes.pipecat` 2/2 on every check;
    `comparable_outcomes.livekit` 2/2 on `call_completed`,
    `no_missing_stage`, `no_error_event`, `no_stale_call`,
    `no_empty_final_transcript`, `no_duplicate_extra_turn`, but 1/2 on
    `expected_turns_reached` (see Blockers' residual-gap entry). Paired
    Quality panel matches both lanes' captured turns against
    `expected-answers.json` with `match_score: 1.0` where transcribed
    correctly.
  - The pre-fix pass (`run_id=...-20260708`, LiveKit 0/2 on every
    `expected_turns_reached`/`no_missing_stage`/`no_empty_final_transcript`
    check, both calls killed by `lk-sip`'s media-timeout) is preserved only
    in the VM-side backup and this file's history, not in the JSON
    evidence directory (overwritten by the second capture).

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
- 2026-07-08 - After the `run-suite.sh` fix and re-run under a new
  `run_id=...-20260708-v2`, pruned again (operator-confirmed) down to only
  v2's 4 calls, backing up the prior (both-runs) state to
  `/var/lib/voicebot/backup-20260708-v1-run/` on the VM first. Superseded
  the broken pre-fix run rather than keeping both, since it was fully
  reproduced by the fixed suite.

## Recent updates

- 2026-07-09 - Added `vms-up` (alias `vms_up`) and `vms-down` (alias `vms_down`) targets to the `Makefile` to start/stop all three VMs (Asterisk, SBC, Monitoring) robustly, checking current VM running states first for idempotency.
- 2026-07-08 - Root-caused the LiveKit disconnect from the entry above:
  read `lk-sip`'s own container logs for the exact call window and found
  `media_port.go: "triggering media timeout"` / `"reason": "media-timeout"`
  - LiveKit's SIP gateway has a hardcoded ~15s RTP-inactivity watchdog, and
    baresip's `aufile` ausrc goes fully silent (no RTP at all) once a WAV
    finishes rather than looping, so any `SETTLE >= 15s` gap between turns
    reliably killed the call. This reframed it from "a LiveKit agent bug,
    out of scope for spec05" to "a `run-suite.sh` gap, squarely spec05's
    territory". Fixed (commit `134cc2f`): re-arm the silence primer every
    second through the settle window. Re-ran live: LiveKit went from
    dying after turn 1 on 2/2 calls to completing 4/4 turns on one
    conversation and 3/4 on the other (a milder, separate timing issue -
    see Blockers). Pruned the VM's logs again to the fixed run only
    (operator-confirmed, backed up first - see VM-side data hygiene).
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
