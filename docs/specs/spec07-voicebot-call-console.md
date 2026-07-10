# Spec spec07 - Voicebot Call Console Redesign

> Governed by `docs/runbooks/spec-rules.md`. A spec is a stable contract, not a
> changelog. Daily progress belongs in `PLANS.md`.

- **Status:** Draft
- **Owner:** operator
- **Created:** 2026-07-10
- **Builds on:** `docs/specs/spec02-voicebot-observability-dashboard.md` and
  `docs/specs/spec03-voicebot-dashboard-redesign.md` (the dashboard itself),
  `docs/specs/spec06-soniox-pipecat-consolidation.md` (single Pipecat lane,
  streaming STT/TTS, semantic endpointing)
- **Retires:** the dashboard's LiveKit-era comparison surface (`/parity`,
  `/comparison`), which spec06 left in graceful-degradation mode

## Goal

An operator opens `/calls/{call_id}` while a call is running and watches a
voice-to-voice console: the conversation flows as chat bubbles (caller left,
bot right) with per-stage latency badges under each bubble, while a
pipeline-pulse strip shows which stage (STT / LLM / TOOL / TTS) is active
right now, how long it has been active, and what its last event was. When
the call ends, the same page reads as the finished conversation with a call
summary in place of the pulse. The dead lane-comparison views are gone. This
is a dev tool, not a product, but it must look deliberate and communicate
meaning at a glance.

## Problem Statement

spec06 removed the LiveKit lane, so the dashboard's `/parity` and
`/comparison` views (fairness gate, paired quality scoring, per-lane
latency/reliability/cost, `LANES = ("livekit", "pipecat")` in
`app/data.py`) compare one live lane against a retired one; they carry
maintenance weight and mislead newcomers. Meanwhile the per-call view
(`app/templates/call_detail.html`) renders each turn as a flat numbered
step card list. It answers "what happened" after the fact but does not read
as a conversation, gives no sense of what the pipeline is doing at this
moment, and hides barge-in and echo-filter events inside generic step
markup. With a streaming pipeline whose whole point is sub-second turn
latency, the console should make liveness visible.

## Scope

1. Redesign the call console page (`/calls/{call_id}`,
   `app/templates/call_detail.html` plus its inline script and the related
   `dashboard.css` rules) around two elements:
   - a chat-bubble conversation: caller bubbles left, bot bubbles right,
     latency badges under each bubble (caller: stt ms; bot: llm, tool when
     present, tts ms), tool calls attached to the owning bot turn;
   - a pipeline-pulse strip pinned on the page: four stages
     (STT / LLM / TOOL / TTS), each showing idle/active state, a live
     elapsed timer while active, and a short label of its last event
     (for example "final transcript", "streaming", "first audio").
2. Surface barge-in (`audio.barge_in.stop_bot_audio`) and echo-filter
   (`stt.echo_filtered`) events on a compact event strip of their own,
   visually tied to the moment they happened in the conversation.
3. Finished calls use the same view: full conversation rendered statically,
   and the pulse strip replaced by a call summary (duration, turn count,
   average and p95 per-stage latency). No replay mechanics.
4. Extend the `/api/calls/{call_id}/turns` response with
   backward-compatible fields the pulse needs (for example
   `call.active_stage`, last event label, active-stage start timestamp),
   derived read-only from `events.jsonl` in `app/data.py`. No new endpoint.
5. Poll the call console at 1 s (env-overridable) instead of the shared 5 s
   default; other pages keep their current interval.
6. Remove the comparison surface: `/parity` and `/comparison` routes and
   their `/api/comparison/*` and parity endpoints in `app/main.py`, the
   `parity.html` and `comparison.html` templates, the `/comparison` nav
   link in `base.html`, and the comparison-only helpers in `app/data.py`
   (lane parity, fairness, paired quality, per-lane latency, reliability,
   per-lane cost) that no remaining view uses. Update or remove their
   tests in `tests/test_data.py`.

## Non-Goals

- No WebSocket or server-push transport; polling stays the mechanism.
- No frontend framework, bundler, or build step; no new JS libraries.
- No replay scrubber or audio-synchronized playback of recordings.
- No second lane and no LiveKit UI; re-adoption requires a new decision
  per DEC-010.
- No new trace event types and no writer-side changes; the console reads
  the existing `voicebot-events-v1` schema only.
- No changes to the overview, calls list, cost, or transcriber pages
  beyond removing the comparison nav link.
- No theme switch: the console keeps the dashboard's current light Tabler
  theme.

## Architecture Contract

- The dashboard remains a read-only consumer of
  `/var/lib/voicebot/events.jsonl`, `/var/lib/voicebot/usage.jsonl`, and
  `/var/spool/asterisk/monitor/` (DEC-008 path resolution, DEC-009 UUID
  normalization unchanged). It never writes to those sinks and never calls
  a model provider.
- Stack stays FastAPI + Jinja2 server-rendered templates + vanilla JS
  polling + Chart.js where already used. All motion is CSS
  transitions/animations driven by the polling loop; no build step, so
  `install.sh` file-copy plus service restart remains the full deploy.
- Served unchanged by `voicebot-dashboard.service` (uvicorn,
  127.0.0.1:8099 default, systemd sandboxing with read-only paths).
- All pulse/active-stage derivation lives server-side in `app/data.py`
  next to the existing turn/step grouping and `derive_stage_latency`;
  the frontend renders fields, it does not infer pipeline state.

## Config Contract

- New env name (documented in `.env.example` with a non-secret default):
  a call-console poll interval, default 1 second; the existing dashboard
  refresh setting keeps governing the other pages at 5 seconds.
- No other config, template, or service-unit changes.

## API Contract

- `/api/calls/{call_id}/turns` keeps every existing field; new fields are
  additive so any existing consumer keeps working. Additions carry the
  pulse state for in-progress calls (active stage, its start timestamp,
  last event label per stage) and the summary aggregates for ended calls
  (duration, turn count, per-stage average and p95 latency), all derived
  from events already on disk.
- `/api/comparison/*` and the parity endpoint are removed and return 404.
  They were operator-facing dev views, not customer contracts; no
  deprecation window is needed.

## Observability Contract

- Read-only feature: no new events, no schema changes, no redaction
  changes. The console consumes existing stages
  (`call, audio, stt, llm, tool, tts, error`) and existing event names;
  measured `duration_ms` values stay preferred over timestamp deltas, and
  the existing `latency_basis` truthfulness rule extends to the pulse
  strip (an approximated value must not be presented as measured).
- Visual language: one consistent accent color per stage used everywhere
  a stage appears (badge, pulse strip, event strip); motion carries
  meaning (state change, new content) and is never decorative. Palette
  and animation specifics are left to implementation.
- Live evidence for acceptance lands under ignored
  `runtime/spec07-live-evidence/`.

## Acceptance Criteria

- The call console renders a live call as the chat-bubble conversation
  with per-bubble latency badges, and the pulse strip tracks the active
  stage with a live timer, verified against a real call
  (baresip -> SBC -> 1098) watched end to end; barge-in and echo-filter
  events appear on the event strip when triggered.
- A finished call renders the full conversation plus the call summary
  (duration, turn count, per-stage average and p95 latency) on the same
  page.
- `/parity` and `/comparison` are gone: routes return 404, templates and
  comparison-only `app/data.py` helpers are deleted, the nav link is
  removed, and `rg -i comparison vms/asterisk/services/dashboard` returns
  no live code references.
- Dashboard unit tests pass with comparison tests updated or removed and
  new coverage for the pulse/summary derivation; `ruff check` passes on
  `vms/asterisk/services/`; `make verify` passes on the Asterisk VM.
- No secrets or runtime artifacts tracked by git; `PLANS.md` reflects
  final state; all changes committed.
