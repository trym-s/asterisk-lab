# PLANS.md - asterisk-lab live execution state

> Governed by `docs/runbooks/plan-rules.md`. Keep around 100 to 250 lines.
> Update after every meaningful step. Link artifacts; never paste long output.
> Always carry a state.
> When the governing spec is complete, archive this file under `docs/archive/plan/`.
> The next spec starts with a fresh root `PLANS.md` from `docs/templates/PLANS.md`.

**Status:** spec06 started. Governance docs created (spec, kickoff prompt,
DEC-010); spec04 marked superseded. Implementation not yet started.
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
- [ ] Phase 1 - Remove the LiveKit lane: repo tree, pjsip trunk, ext 1099,
      Makefile targets, deploy filter, env names, `run-suite.sh` LiveKit
      path + RTP keepalive hack; dashboard single-lane degradation checked;
      VM containers and images removed.
- [ ] Phase 2 - 16 kHz audio path: ext 1098 on chan_audiosocket Dial form
      with slin16; sample-rate-parameterized `audiosocket.py` (640-byte
      frames); nearest-neighbour resampler deleted.
- [ ] Phase 3 - Soniox streaming pipeline: SonioxSTTService (stt-rt-v5,
      Turkish hints, domain context, endpoint detection) + OpenAI LLM with
      lookup_docs + SonioxTTSService (16 kHz, Turkish); Soniox "<end>"
      owns turn-end, VAD owns barge-in; DirectLLMContextTrigger removed;
      BotEchoFilter behind an env flag; profile/pricing/trace updates;
      SONIOX_API_KEY plumbing.
- [ ] Phase 4 - Deploy + live verification: TTS voice samples for operator
      voice choice; manual call evidence (latency, quality, barge-in, no
      cutoff); corpus suite run with dashboard evidence under
      `runtime/spec06-live-evidence/`; `make verify`, ruff, shellcheck,
      dashboard tests; all committed.

## Blockers

- `SONIOX_API_KEY` not yet provided by the operator (needed from Phase 3
  onward; Phases 1-2 are unblocked).
- Turkish TTS voice not yet chosen (listening test planned in Phase 4).

## Canonical evidence

- Planned: `runtime/spec06-live-evidence/` (git-ignored) for the live-call
  and corpus-suite captures required by the spec's acceptance criteria.
- Historical: `runtime/spec04-comparison-verify/`,
  `runtime/spec05-live-evidence/` (see archived plan).

## Recent updates

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
