# PLANS.md - asterisk-lab live execution state

> Governed by `docs/runbooks/plan-rules.md`. Keep around 100 to 250 lines.
> Update after every meaningful step. Link artifacts; never paste long output.
> Always carry a state.
> When the governing spec is complete, archive this file under `docs/archive/plan/`.
> The next spec starts with a fresh root `PLANS.md` from `docs/templates/PLANS.md`.

**Status:** spec07 drafted, awaiting kickoff. The spec redesigns the
per-call dashboard page into a voice-to-voice console (chat-bubble
conversation + pipeline-pulse strip) and removes the retired LiveKit-era
comparison surface. No implementation started.
**Governing spec:** `docs/specs/spec07-voicebot-call-console.md`
**Kickoff prompt:** `docs/prompts/spec07-voicebot-call-console.md`
**Last updated:** 2026-07-10

## Active milestones

- [ ] Call console page redesign: chat-bubble conversation with per-bubble
      latency badges, pipeline-pulse strip (stage state, live timer, last
      event label), barge-in/echo-filter event strip.
- [ ] Finished-call mode: same view with a call summary (duration, turn
      count, per-stage avg/p95 latency) replacing the pulse strip.
- [ ] Additive pulse/summary fields on `/api/calls/{call_id}/turns`,
      derived server-side in `app/data.py`; 1 s console polling
      (env-overridable).
- [ ] Remove `/parity` and `/comparison`: routes, API endpoints, templates,
      nav link, comparison-only `app/data.py` helpers, and their tests.
- [ ] Gates and live evidence: dashboard tests, ruff, `make verify`, real
      call watched end to end, evidence under
      `runtime/spec07-live-evidence/`.

## Blockers

- none

## Canonical evidence

- none

## Recent updates

- 2026-07-10 - Drafted spec07 (voicebot call console redesign) with the
  operator: chat-bubble layout, pulse detail level, no-replay finished-call
  mode, light Tabler theme, additive turns-API fields, 1 s console polling
  all confirmed interactively. Comparison surface removal is in scope;
  implementation deferred to the spec07 kickoff.
- 2026-07-10 - Closed spec06: LiveKit lane removed, Pipecat lane moved to
  Soniox streaming STT/TTS at 16 kHz with semantic endpointing owning
  turn-end and VAD limited to barge-in. Proven live: both 4-turn Turkish
  corpus conversations completed cleanly, first bot audio ~1.2-2.4 s after
  caller stop (vs 10+ s on the old batch pipeline). All gates green
  (`make verify` 11/11, ruff, shellcheck, 25 dashboard + 6 common tests).
  Two bugs found and fixed during the live run: AudioSocket slin16 KIND
  byte (0x12, not 0x10) and streaming-STT interim frames poisoning the
  echo filter. Archived to
  `docs/archive/plan/2026-07-10-spec06-soniox-pipecat-consolidation.md`.
  Deferred, non-blocking follow-ups (not tracked as TODO - no operator
  approval sought yet): pick the Turkish TTS voice from the three
  captured samples (default stays `Adrian`); tune
  `VOICEBOT_STT_ENDPOINT_SENSITIVITY` against a real human call; reconcile
  the Soniox TTS per-char cost estimate against a real invoice.

## Archive pointers

- `docs/archive/plan/2026-07-07-spec01-deploy-sbc-monitoring.md`
- `docs/archive/plan/2026-07-07-spec02-voicebot-observability-dashboard.md`
- `docs/archive/plan/2026-07-07-spec03-voicebot-dashboard-redesign.md`
- `docs/archive/plan/2026-07-10-spec05-realistic-multiturn-test-corpus.md`
- `docs/archive/plan/2026-07-10-spec06-soniox-pipecat-consolidation.md`
