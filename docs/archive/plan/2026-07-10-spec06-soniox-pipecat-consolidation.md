# PLANS.md - asterisk-lab live execution state

> Governed by `docs/runbooks/plan-rules.md`. Keep around 100 to 250 lines.
> Update after every meaningful step. Link artifacts; never paste long output.
> Always carry a state.
> When the governing spec is complete, archive this file under `docs/archive/plan/`.
> The next spec starts with a fresh root `PLANS.md` from `docs/templates/PLANS.md`.

**Status:** spec06 implemented and proven live. LiveKit lane removed
(repo + VM); Pipecat runs Soniox streaming STT/TTS at 16 kHz with semantic
endpointing owning turn-end and VAD owning barge-in only. A live corpus
suite completed both 4-turn Turkish conversations end to end (Soniox STT
transcripts correct, lookup_docs firing, first bot audio ~1.2-2.4 s after
the caller stops vs 10+ s on the old batch pipeline). All gates green.
**Governing spec:** `docs/specs/spec06-soniox-pipecat-consolidation.md`
**Predecessor:** `docs/specs/spec05-realistic-multiturn-test-corpus.md`
(Draft; corpus/suite/dashboard rework proven live. Its two residual open
items transfer here: the fixed-timer settle budget in `run-suite.sh` is
revisited in spec06 scope item 7, and the corpus-WAV `.gitignore` vs
Architecture Contract mismatch remains an operator decision.)
**Last updated:** 2026-07-10

## Active milestones

- [x] Governance: spec06 + kickoff prompt created, `PLANS.md` archived and
      reset, spec04 header marked superseded, DEC-010 recorded.
- [x] Phase 1 - LiveKit lane removed: `services/livekit/` tree, pjsip
      trunk, ext 1099 + header/outbound contexts, Makefile targets, env
      names, `run-suite.sh` LiveKit path + RTP keepalive hack. Dashboard
      degrades to single lane (25/25 tests). VM containers + images gone.
      (commit `848f0f8`)
- [x] Phase 2 - 16 kHz audio path: ext 1098 on chan_audiosocket Dial form
      with c(slin16); sample-rate-parameterized `audiosocket.py`. Resampler
      deleted. (commit `ee25df2`; KIND-byte 0x12 framing fixed in `4b84f61`)
- [x] Phase 3 - Soniox streaming pipeline: SonioxSTTService (stt-rt-v5,
      Turkish hints, domain context, endpoint detection) + OpenAI LLM with
      lookup_docs + SonioxTTSService (16 kHz native). Soniox endpoint owns
      turn-end (EndpointLLMTrigger), VAD owns barge-in; profile gains
      provider fields; Soniox pricing rows; measured per-stage duration_ms.
      (commit `74afe7d`)
- [x] Phase 4 - Deployed and verified live: 3 Turkish TTS voice samples
      captured for operator choice; corpus suite completed both 4-turn
      conversations (8 STT, 6 tool lookups, echo drops 0); measured LLM
      p50 1441 ms, TTS first-audio 1.2-2.4 s. `make verify` 11/11, ruff,
      shellcheck, common + dashboard tests all green. Evidence under
      `runtime/spec06-live-evidence/`.

## Blockers

- none

## Follow-ups (deferred, non-blocking)

- Operator to pick the Turkish TTS voice from the three samples in
  `runtime/spec06-live-evidence/tts-samples/` (default is `Adrian`; change
  via `VOICEBOT_TTS_VOICE`). Soniox voices are multilingual, not
  Turkish-specific.
- STT endpoint-latency metric reads `unknown` under the replayed-WAV
  suite (no fresh VAD-stop per turn); it is honest now rather than wrong.
  Real barge-in / endpoint feel needs a human-driven call to tune
  `VOICEBOT_STT_ENDPOINT_SENSITIVITY`.
- Soniox TTS char->USD rate in `usage_summary.py` is an estimate
  (~$13/1M chars); reconcile against a real invoice.
- Old per-utterance WAVs under `test-caller/audio/` (carried from spec05)
  remain gitignored runtime artifacts.

## Canonical evidence

- `runtime/spec06-live-evidence/` (git-ignored): `dashboard-snapshot.jsonl`
  (overview/calls/latency/reliability/fairness/cost), `agent-dialogue.log`
  (both conversations' transcripts), `tts-samples/*.wav` (Adrian/Maya/Daniel
  Turkish samples). Suite run logs under
  `vms/asterisk/services/test-caller/runs/20260710-17*/`.
- Historical: `runtime/spec04-comparison-verify/`,
  `runtime/spec05-live-evidence/` (see archived plan).

## Recent updates

- 2026-07-10 - Implemented spec06 end to end across four commits
  (`848f0f8` remove LiveKit, `ee25df2` 16 kHz path, `74afe7d` Soniox
  pipeline, `4b84f61` + latency fix). First live run surfaced two bugs
  fixed same session: AudioSocket slin16 uses KIND byte 0x12 not 0x10
  (our 16 kHz frames were read as 8 kHz), and streaming STT interim
  frames (TextFrame subclass) were logged as bot speech and poisoned the
  echo filter into dropping every real user turn. After the fixes both
  4-turn conversations complete cleanly. Restored host baresip config
  (temporarily enabled G722/aufile for the wideband test).
- 2026-07-10 - spec06 created from the operator conversation: remove the
  LiveKit lane (down on the VM since 2026-07-08; WebRTC stack is pure ops
  burden in a SIP-only lab), adopt the Soniox voice-agent reference
  architecture inside the Pipecat agent (streaming STT/TTS, semantic
  endpointing owns turn-end, VAD owns barge-in), 16 kHz end to end.
  Key facts verified beforehand: pipecat-ai 1.4.0 already installed with
  native Soniox services (stt-rt-v5 default, TR supported, 16 kHz TTS
  output valid); Asterisk 22 chan_audiosocket supports slin16 via the
  Dial form. Archived the spec05 plan state to
  `docs/archive/plan/2026-07-10-spec05-realistic-multiturn-test-corpus.md`.

## Archive pointers

- `docs/archive/plan/2026-07-07-spec01-deploy-sbc-monitoring.md`
- `docs/archive/plan/2026-07-07-spec02-voicebot-observability-dashboard.md`
- `docs/archive/plan/2026-07-07-spec03-voicebot-dashboard-redesign.md`
- `docs/archive/plan/2026-07-10-spec05-realistic-multiturn-test-corpus.md`
