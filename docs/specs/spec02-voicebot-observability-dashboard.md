# Spec spec02 - Voicebot Observability Dashboard

> Governed by `docs/runbooks/spec-rules.md`. A spec is a stable contract, not a
> changelog. Daily progress belongs in `PLANS.md`.

- **Status:** Done
- **Owner:** operator
- **Created:** 2026-07-07
- **Completed:** 2026-07-07

## Goal

An operator opens a web page served from the Asterisk VM and sees, per call and
per turn, the STT/LLM/TTS input and output text, the approximate latency (ms) of
each stage, the estimated cost, and a LiveKit-vs-Pipecat side-by-side
comparison. The page refreshes on a short interval so an active call can be
followed while it happens.

## Problem Statement

The voicebot lanes already emit structured telemetry as JSONL under
`/var/lib/voicebot/` on the Asterisk VM (`events.jsonl`, schema
`voicebot-events-v1`; `usage.jsonl`; `turns.jsonl`), but there is no way to see
it. Zabbix and Grafana cover only the infra and telephony plane
(SIP/RTP/rtpengine/channels) and never touch the STT/LLM/TTS/turn/cost plane.
The data is reachable today only through CLI tools (`usage_summary.py`,
`tail_turns.py`) and raw files. As a result the two lanes cannot be compared, and
a single turn's pipeline cannot be inspected, at a glance. This repository treats
LiveKit and Pipecat as comparison surfaces whose parity must be proven with fresh
runtime evidence, so a visual per-turn view of that evidence is missing
infrastructure.

## Scope

1. A new read-only web service under `vms/asterisk/services/dashboard/`
   (FastAPI app + Jinja2 templates + vendored Tabler and chart static assets,
   Bootstrap 5, no Node or build chain).
2. A data layer that reads the local JSONL sinks by reusing
   `vms/asterisk/services/common/`: `trace_events.read_events` /
   `validate_event` for `events.jsonl`; the `usage_summary.PRICE` table and
   `parse_since` for cost; `turns.jsonl` parsing for transcripts.
3. Latency derivation: group `events.jsonl` rows by `(lane, call_id, turn_id)`,
   order by `ts`, and compute inter-stage deltas as approximate stt/llm/tts
   milliseconds. When a row carries a real `duration_ms` (already true for the
   `tool` stage, and forward-compatible with a later instrumentation spec),
   prefer it over the derived value. Derived values are labeled approximate in
   the UI.
4. Four panels, each a rendered page backed by a JSON endpoint: lane parity
   comparison, cost and usage, turn transcript viewer, and batch transcriber
   status (scan `/var/spool/asterisk/monitor/*.wav` against the sibling `.txt`
   and report whether the `transcriber` unit is active).
5. In-page polling / auto-refresh at a configurable interval; no server push.
6. An idempotent installer, a systemd unit, Makefile targets, and a declarative
   verify smoke check, following the repository deploy conventions.
7. Config Contract additions: the new env keys in `.env.example` (shape only)
   consumed from `/etc/asterisk-lab/env` on the VM.

## Non-Goals

- No WebSocket, SSE, or real-time server push. Live updates are polling only.
  True streaming is a later spec.
- No changes to the LiveKit or Pipecat agents and no real per-stage latency
  instrumentation. That is a separate, parity-critical spec; this dashboard
  consumes whatever `events.jsonl` already contains.
- No duplication of the Zabbix / Grafana infra and telephony metrics.
- No write path. The dashboard never mutates the JSONL sinks and never calls a
  model provider.
- No heavy authentication in v1. The service binds loopback and is reached over
  an SSH tunnel; an optional basic-auth env toggle is the only auth surface.

## Architecture Contract

- The service runs on the Asterisk VM beside the voicebot lanes and reads
  `/var/lib/voicebot/{events,usage,turns}.jsonl` and
  `/var/spool/asterisk/monitor/` read-only. It reuses
  `vms/asterisk/services/common/` made importable on `PYTHONPATH`, mirroring how
  the lanes bind-mount that directory read-only at `/opt/voicebot-common`.
- The deployment shape follows the transcriber precedent: a Python virtualenv
  plus a systemd unit running uvicorn (for example `/opt/voicebot-dashboard/venv`
  and a `voicebot-dashboard.service`), not a container, because it is a thin
  local-file reader. Rendered runtime files are installer outputs, not sources;
  the repository templates and app code are the source of truth.
- The service binds `127.0.0.1` on a dedicated port by default, matching the
  loopback convention used by the LiveKit stack and VNC, and is reached from the
  host over an SSH tunnel. An env override allows a LAN bind when the operator
  opts in.
- Data flow is one direction: JSONL and spool files on disk -> reader/aggregator
  -> JSON endpoint -> Jinja2 page. Nothing flows back toward the lanes.

## Config Contract

- New env keys carry names and non-secret defaults only in `.env.example`, and
  are consumed from `/etc/asterisk-lab/env` on the VM:
  `VOICEBOT_DASHBOARD_BIND` (default `127.0.0.1`), `VOICEBOT_DASHBOARD_PORT`
  (default `8099`; `8090`, `5062`, `7880`, and `4444` are already taken on the
  Asterisk VM), and `VOICEBOT_DASHBOARD_REFRESH_S` (default `5`). The existing
  `VOICEBOT_EVENTS_LOG` and `VOICEBOT_USAGE_LOG` overrides are reused for the
  input paths.
- `make deploy` never transports `.env` or `.env.*` (DEC-004, DEC-007); VM
  secrets live in `/etc/asterisk-lab/env`.
- Pricing stays single-sourced in `usage_summary.PRICE`. The dashboard imports
  that table; it does not fork or re-declare prices.

## API Contract

- Rendered pages (final names decided during execution): `/` (overview),
  `/parity`, `/cost`, `/transcript`, `/transcriber`.
- A read-only JSON surface backs the pages, for example: `GET /api/calls`,
  `GET /api/turns?call_id=<id>`, `GET /api/parity`, `GET /api/cost?since=1h`,
  `GET /api/transcriber`. Each returns the aggregate its page renders.
- The API is read-only and side-effect free. Secrets are already stripped at the
  source by `trace_events.redact`; the dashboard performs no unredaction.

## Observability Contract

- The dashboard is itself an observability surface and must not log secrets. It
  relies on the source-side redaction already applied when `events.jsonl` is
  written; it never reverses it.
- The service logs to journald under its unit
  (`journalctl -u voicebot-dashboard`).
- Acceptance evidence (screenshots, captured page HTML, `curl` of the `/api/*`
  endpoints) is stored under ignored `runtime/` and linked from `PLANS.md`, never
  pasted inline.

## Acceptance Criteria

- `ruff check` passes on the new Python under `vms/asterisk/services/dashboard/`
  and `shellcheck` passes on the new installer.
- A declarative verify target passes on the Asterisk VM: the service is active,
  the port returns HTTP 200, each `/api/*` endpoint returns valid JSON against a
  sample or live `events.jsonl`, and the parity, cost, transcript, and
  transcriber panels render.
- Live runtime behavior is proven with a real or replayed call that produces
  `events.jsonl`: the four panels show the STT/LLM/TTS text, the derived (and any
  real) latency in ms, the estimated cost, and both lanes. Evidence is linked
  from `PLANS.md`.
- No secrets, customer data, or runtime artifacts are tracked by git.
  `.env.example` carries only key names and non-secret defaults.

## Follow-Ups

- Real per-stage `duration_ms` instrumentation in both agents (its own spec). The
  dashboard is built to prefer a real `duration_ms` when present, so no dashboard
  rework is required when that lands.
- Live streaming (its own spec): WebSocket or SSE push, an active-call view, and
  a barge-in timeline. Propose a matching `TODO.md` entry for operator approval;
  do not add it unilaterally.
