# Spec spec05 - Realistic Multi-Turn Test Corpus

> Governed by `docs/runbooks/spec-rules.md`. A spec is a stable contract, not a
> changelog. Daily progress belongs in `PLANS.md`.

- **Status:** Draft
- **Owner:** operator
- **Created:** 2026-07-08

## Goal

An operator runs the LiveKit vs Pipecat paired comparison suite against a
scripted test corpus of realistic, complete-sentence, multi-turn
conversations instead of seven disconnected single-utterance calls, so the
dashboard's Paired Quality, Latency, Reliability, and Cost panels
(`docs/specs/spec04-livekit-pipecat-fair-comparison.md`) reflect genuine
multi-turn conversational behavior - context retention across turns, topic
changes mid-call - rather than one-shot Q&A. Generated test audio is
verified not to truncate mid-sentence before it is ever played into a call.

## Problem Statement

`vms/asterisk/services/test-caller/utterances.tsv` currently defines seven
independent utterances; `run-suite.sh` dials once per utterance, plays one
WAV, and hangs up. No scripted call ever exercises more than one turn, so
the paired comparison built by spec04 has never observed either lane's
behavior across a multi-turn conversation (does the agent keep context
from the previous turn, does it handle a topic change mid-call, does
interruption/echo handling degrade over a longer call).

Separately, while gathering the first real (non-replayed) live VM evidence
for spec04 this session, the operator flagged that generated WAV audio
appears to start each sentence correctly but cut off before the end -
suspected truncation in the ElevenLabs synthesis or the raw-PCM-to-WAV
`ffmpeg` conversion step in `gen-utterances.sh`. An STT-based scoring
pipeline (spec04's Paired Quality panel) built on silently-truncated audio
would produce scores that look plausible but are not measuring what they
claim to measure.

This spec also surfaces a related dashboard defect that will otherwise
regress once multi-turn calls exist: `reliability_summary()` in
`vms/asterisk/services/dashboard/app/data.py` defaults
`expected_turns_per_call` to `1`, an assumption `run-suite.sh`'s current
one-call-per-utterance design happens to satisfy today. A 4-turn
conversation call would be misreported under that default (flagged as
"extra turns" or under-turned) unless the assumption is corrected
alongside the corpus change.

## Scope

1. Replace `utterances.tsv` with `conversations.tsv`
   (`vms/asterisk/services/test-caller/`), columns: `conversation_id`,
   `turn_index`, `utterance_id`, `text`. Two hand-authored conversations,
   each a natural, complete Turkish sentence per turn (no isolated
   fragments), facts grounded in
   `vms/asterisk/services/common/docs/magaza/*.md`:
   - `magaza-sorular` (4 turns): store hours (Sunday, "on bir" / "11") ->
     banyo havlusu price ("üç yüz doksan" / "390") -> çift kişilik
     nevresim price ("sekiz yüz doksan" / "890") -> thanks/closing.
   - `kargo-iade-sorular` (4 turns): İzmir shipping time ("bir iş günü" /
     "1 iş günü") -> return window ("on dört gün" / "14 gün") ->
     exchange-shipping-payer ("müşteri") -> thanks/closing.
2. Update `gen-utterances.sh` to read `conversations.tsv` instead of
   `utterances.tsv`, still emitting one WAV per turn under
   `audio/<utterance_id>.wav`. Switch the ElevenLabs model from
   `eleven_flash_v2_5` to `eleven_multilingual_v2` for higher-fidelity
   synthesis. Add a truncation guard: run `ffmpeg silencedetect` (or
   equivalent) against each generated WAV to confirm genuine trailing
   silence rather than a mid-word cutoff; regenerate once automatically on
   failure, and hard-fail with a clear error if the second attempt also
   fails a given utterance.
3. Restructure `run-suite.sh` from "dial once per WAV" to "dial once per
   `conversation_id`, play each turn's WAV in sequence without hanging up
   between turns, hang up only after the last turn's settle window."
4. Update `expected-answers.json` to match the new corpus content and
   per-turn `utterance_id`s. Schema and scoring mechanism are unchanged
   (STT text match, tool-required, source-doc hit, required/forbidden
   facts, echo/extra-turn indicator) - only the content changes.
5. Fix `reliability_summary()`'s `expected_turns_per_call` handling
   (`vms/asterisk/services/dashboard/app/data.py`) so a 4-turn conversation
   call is correctly counted as reaching its expected turns, not
   misreported against the old single-turn default.
6. Remove the old `utterances.tsv` and its per-utterance WAVs
   (`01-greeting.wav` through `07-thanks-hangup.wav`) once the new corpus
   replaces them. `00-silence.wav` (the `ausrc` primer used before each
   dial) stays.
7. Re-run the LiveKit vs Pipecat paired comparison suite against the new
   corpus (shared `VOICEBOT_RUN_ID`, both lanes) and recapture dashboard
   evidence for spec04's live-evidence acceptance criterion, now exercising
   multi-turn calls end to end.

## Non-Goals

- No change to call topology (still Asterisk -> baresip caller -> lane
  extension); no SBC or routing changes.
- No new expected-answer scoring dimensions beyond what spec04 already
  defined - this spec changes what is being scored (multi-turn calls), not
  how scoring works.
- No change to LiveKit/Pipecat agent conversational logic (system prompt,
  tool schema, model config) - only the calling/test-corpus side changes.
- No general-purpose N-turn conversation authoring framework - exactly the
  two scripted conversations in Scope item 1. Additional scenarios are a
  Follow-Up, not blocking.
- No retry or self-healing logic beyond the single automatic
  regenerate-once guard in `gen-utterances.sh`. Persistent truncation after
  two attempts is a hard failure the operator must inspect, not something
  the script silently papers over.

## Architecture Contract

- `vms/asterisk/services/test-caller/` remains the sole owner of the
  scripted test corpus and its playback driver.
- The dashboard continues to only read `/var/lib/voicebot/*.jsonl` and the
  read-only expected-answer fixture, per spec04's Architecture Contract;
  this spec does not change that boundary.
- `conversations.tsv` and its generated `audio/*.wav` files are versioned,
  read-only fixtures tracked in git, exactly as `utterances.tsv` and its
  WAVs were - not runtime data.
- The `VOICEBOT_RUN_ID` pairing mechanism introduced by spec04 is unchanged:
  one shared run id across both lanes' invocations of the restructured
  suite.

## Config Contract

- No new env keys. `ELEVENLABS_MODEL_ID`'s effective default changes
  (`eleven_flash_v2_5` -> `eleven_multilingual_v2`) but remains overridable
  the same way it is today.
- `.env.example` is unaffected: no new keys, no new secrets.

## API Contract

- No dashboard endpoint or response-shape changes. `GET
  /api/comparison/reliability` keeps its existing contract; only the
  internal `expected_turns_per_call` value used to compute its counts
  changes.

## Observability Contract

- Unchanged from spec04: same JSONL sinks
  (`/var/lib/voicebot/{events,usage,turns}.jsonl`), same source-side
  redaction path, same `runtime/`-under-git-ignore evidence convention.

## Acceptance Criteria

- `shellcheck` passes on changed shell scripts (`gen-utterances.sh`,
  `run-suite.sh`).
- `ruff check` passes on changed Python
  (`vms/asterisk/services/dashboard/app/data.py`).
- A dashboard unit test proves a 4-turn conversation call is correctly
  counted as reaching its expected turns under the corrected
  `expected_turns_per_call` handling (not misreported as under- or
  over-turned).
- Live evidence: a real paired run (LiveKit ext 1099, Pipecat ext 1098,
  shared `VOICEBOT_RUN_ID`) using the new `conversations.tsv` corpus, with
  every generated turn WAV verified non-truncated (silencedetect check
  passing for all 8 turn WAVs), captured and linked from `PLANS.md`. The
  dashboard's Paired Quality panel shows both lanes scored across multiple
  turns of at least one full conversation; Reliability's comparable-outcomes
  counts correctly reflect 4-turn calls.
- No secrets, customer data, or runtime artifacts are tracked by git.

## Follow-Ups

- Additional conversation scenarios (e.g. product comparison, complaint
  handling) beyond the two defined here. Propose a matching `TODO.md` entry
  for operator approval.
- General N-turn conversation authoring tooling if the corpus keeps growing
  beyond a handful of hand-authored scripts.

## References

- Predecessor and governing context: `docs/specs/spec04-livekit-pipecat-fair-comparison.md`.
  This spec supersedes spec04's "existing scripted utterances" assumption
  for the test corpus and fixes the `expected_turns_per_call` mismatch that
  assumption's replacement surfaces.
- Store facts corpus: `vms/asterisk/services/common/docs/magaza/*.md`.
