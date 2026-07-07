# Spec spec03 - Voicebot Dashboard Redesign

> Governed by `docs/runbooks/spec-rules.md`. A spec is a stable contract, not a
> changelog. Daily progress belongs in `PLANS.md`.

- **Status:** Done
- **Owner:** operator
- **Created:** 2026-07-07

## Goal

An operator opens the dashboard and sees an Overview with click-through KPI
tiles (cost over a selectable time range, VM up/down status per VM, calls
currently in progress, and registered SIP extensions), a Calls list where
each call shows both its live-STT-captured status and its
batch-transcription status, a call-detail page that animates the
STT-output -> LLM-response -> TTS-input pipeline per turn with per-stage
latency and lane, and a cost view with a trend chart plus drill-down instead
of one flat table. The service stays read-only, polling-refreshed, and
deployed the same way as today: a systemd-managed FastAPI app on the
Asterisk VM.

## Problem Statement

`spec02` shipped four flat panels (parity, cost, transcript, transcriber)
and a KPI-less overview list. There is no way to see infra health, cost
trends, or an in-progress call's flow at a glance, and the tables read as
raw data dumps rather than an operator tool. The dashboard also does not
answer the immediate operator questions during a field test: "how many and
which extensions are registered?", "I just placed a call - has the system
seen it start?", and "what text came out of STT and what exact text went
into TTS?". Two separate notions of
"transcribed" exist and are never shown together: live per-turn STT capture
(from `events.jsonl`) and batch Whisper transcription of the raw call
recording (`.wav`/`.txt` pairing under `/var/spool/asterisk/monitor/`) - the
latter has no linkage to a voicebot `call_id` today, so it cannot currently
be surfaced per call. VM/host uptime is invisible in this dashboard; only
per-service `active`/`inactive` booleans exist in Zabbix, with no
host-level up/down tracking wired up anywhere in the lab.

## Scope

1. **Overview redesign.** KPI tiles for: cost over a selectable time range
   (reusing `cost_summary`/`parse_since` from `services/common/usage_summary.py`),
   VM uptime/downtime per VM (Asterisk, SBC, monitoring - see item 4), and a
   count of calls currently in progress. It also shows a registered SIP
   extensions tile: total configured extensions, currently reachable
   extensions, and the concrete extension numbers/statuses returned by
   Asterisk PJSIP. Each tile links through to its corresponding detail page
   or a pre-filtered view (e.g. the cost tile links to the Cost page with the
   same time range selected; the active-calls tile links to the Calls page
   filtered to in-progress; the extensions tile opens the Calls page's
   extension roster band).
2. **Calls page** (evolves today's Overview call list). One row per call as
   today, plus two independent status badges per row:
   - live STT capture presence, derived from whether any turn for that call
     has a `stt/final_transcript` event (existing data, no new instrumentation);
   - batch-transcription presence, derived from the new call/recording
     correlation in item 5.
   The page includes an extension roster band above the calls table, showing
   exactly which configured extensions are registered/reachable now and which
   are unavailable. It also supports an in-progress filter so a just-started
   call is visible within the dashboard refresh interval.
   The standalone Transcriber page narrows to service health only (unit
   active/inactive, pending-recording count); the per-file `.wav`/`.txt`
   table it shows today is dropped from that page, since the same
   information now surfaces per call on the Calls page.
3. **Call-detail page** (evolves today's `/transcript?call_id=`, reachable at
   a per-call route, e.g. `/calls/{call_id}`). Renders each turn as an
   animated, step-by-step sequence: STT output text arrives, then LLM
   response text, then the exact TTS input text that is sent for synthesis.
   Each step is tagged with its per-stage latency (labeled "measured" or
   "approx", same derivation rule as today - a real `duration_ms` when
   present, otherwise the ts-delta between stage events), the lane (LiveKit or
   Pipecat) badge, and whether the call is still live. Built from the
   existing `turn_summary()` / `derive_stage_latency()` helpers in
   `dashboard/app/data.py`. Animation is CSS-transition/keyframe driven by
   the existing HTTP polling loop - a step reveals when its data first
   appears in a poll response. A call still in progress is visually marked as
   live (new turns appending as polls return them); a finished call renders
   the same view statically.
4. **VM uptime/downtime KPI.** Attach a Zabbix host-level availability item
   (the standard Zabbix agent template's `agent.ping`/`system.uptime`, or an
   equivalent lab item) to the Asterisk, SBC, and monitoring VM hosts already
   registered by `vms/monitoring/provision-observability.py`. The dashboard
   adds a small read-only Zabbix API client (new module under
   `dashboard/app/`) that queries uptime history/percentage for the selected
   KPI time range. This is additive to Zabbix's existing per-service
   `lab.systemd.active[*]` items; it does not replace or duplicate the
   existing Grafana panels.
5. **Call/recording correlation.** Add the Asterisk channel/uniqueid as a new
   field on the existing `call`-stage trace event emitted by both
   `vms/asterisk/services/livekit/agent.py` and
   `vms/asterisk/services/pipecat/agent.py` (both already import the shared
   `trace_events.py` schema and write to the same `events.jsonl`; this is a
   new field on an existing event, not a new event/stage). The dashboard
   parses the equivalent id out of `/var/spool/asterisk/monitor/*.wav`
   filenames (Asterisk MixMonitor naming) and joins it to a `call_id` to
   determine batch-transcription status per call.
6. **Cost view redesign.** Add a cost-over-time chart (bucketed, e.g.
   hourly/daily depending on the selected range) built from `usage.jsonl`,
   plus a drill-down breakdown that starts at a lane-level summary and
   expands into stage/model/provider detail on demand - replacing today's
   single flat table grouped by `(lane, provider, stage, model, op,
   unit_type)` all at once.
7. **Visual modernization.** Across all pages, replace bare data-dump tables
   with stat tiles, charts, and drill-down tables used selectively. Apply
   consistent color rules: a status palette for uptime/service-active state,
   a fixed categorical hue order for the two lanes (LiveKit vs. Pipecat,
   used consistently across Parity, Overview, and Call-detail), and a single
   sequential hue for cost magnitude. Stay within the existing vendored
   Tabler CSS/JS and Chart.js assets - no new charting library.

## Non-Goals

- No WebSocket, SSE, or server push. All live updates remain HTTP polling
  only, same as `spec02`'s non-goal - the animated call-detail flow reveals
  steps as polls return new data, it does not stream.
- No true measured `duration_ms` instrumentation for the stt/llm/tts request/
  response boundary. Latency stays ts-delta-approximated except where a real
  `duration_ms` already exists (currently only the `tool` stage). Real
  per-stage timers remain a deferred follow-up, as in `spec02`.
- No new authentication surface beyond what `spec02` already ships (optional
  basic-auth env toggle).
- No dashboard write path. The dashboard still never mutates
  `/var/lib/voicebot/*.jsonl`, `/var/spool/asterisk/monitor/`, or calls a
  model provider.
- No rebuild or duplication of Zabbix/Grafana's existing service-level
  panels and dashboards. Only the new host-uptime item and the dashboard's
  read of it are in scope; Grafana's existing per-service panels are
  untouched.
- No frontend build chain. Server-rendered Jinja2 plus vendored static
  assets remains the stack; no Node, no bundler, no JS framework.

## Architecture Contract

- The dashboard remains a FastAPI + Jinja2 app deployed as
  `voicebot-dashboard.service` on the Asterisk VM, following the same
  virtualenv + systemd-unit deployment shape as `spec02` (no container).
- Existing read paths are unchanged: `/var/lib/voicebot/{events,usage,turns}.jsonl`
  and `/var/spool/asterisk/monitor/` are read-only inputs, reusing
  `vms/asterisk/services/common/` (`trace_events`, `usage`, `usage_summary`)
  made importable on `PYTHONPATH` as today.
- New outbound dependency: a read-only HTTP call from the Asterisk VM to the
  monitoring VM's Zabbix API for host-uptime data. This is the first time the
  dashboard reaches across VMs; it must degrade gracefully (uptime tile shows
  "unavailable" rather than failing the whole Overview page) if the
  monitoring VM or its API is unreachable.
- New local read-only observation: the dashboard may execute
  `asterisk -rx "pjsip show endpoints"` on the Asterisk VM to summarize
  configured and registered SIP extensions. This is read-only operator
  state, not a config source; rendered files and templates remain the source
  of truth for endpoint configuration.
- New field on the existing `call`-stage trace event in both lane agents:
  the Asterisk channel/uniqueid, populated from data already available to
  each agent's Asterisk integration. No new event, no new stage, no schema
  version bump - `events.jsonl` readers that ignore unknown payload fields
  continue to work unchanged.
- Data flow direction is preserved: JSONL/spool files and the new Zabbix API
  response flow one way into the dashboard's read/aggregate/render pipeline;
  nothing flows back toward the lanes, Asterisk, or Zabbix.

## Config Contract

- New env keys, names and non-secret defaults only in `.env.example`,
  consumed from `/etc/asterisk-lab/env` on the Asterisk VM:
  `VOICEBOT_DASHBOARD_ZABBIX_API_URL` (points at the monitoring VM's Zabbix
  API), `VOICEBOT_DASHBOARD_ZABBIX_API_TOKEN` (secret; name only in
  `.env.example`, real value lives only in `/etc/asterisk-lab/env`),
  `VOICEBOT_DASHBOARD_DEFAULT_RANGE` (default KPI time range, e.g. `1h`), and
  `VOICEBOT_DASHBOARD_COST_BUCKET` (default bucket size for the cost trend
  chart, e.g. `1h`). The extension roster uses
  `VOICEBOT_DASHBOARD_ASTERISK_CLI` only as an optional local-dev override;
  the default is `asterisk`.
- `make deploy` continues to never transport `.env`/`.env.*` (DEC-004,
  DEC-007); all secrets stay in `/etc/asterisk-lab/env` per VM.
- Pricing stays single-sourced in `usage_summary.PRICE`; this spec does not
  add a second pricing table.
- The Zabbix host-uptime item's provisioning (template attachment or new
  item definition) is added idempotently to
  `vms/monitoring/provision-observability.py`, following the existing
  pattern for `ASTERISK_ITEMS`/`SBC_ITEMS`.

## API Contract

- New or changed read-only JSON endpoints:
  - `GET /api/uptime?since=` - per-VM uptime percentage/history for the
    given range, sourced from the new Zabbix host item.
  - `GET /api/extensions` - configured PJSIP softphone extensions, including
    registered/reachable count and the concrete extension numbers/statuses.
  - `GET /api/overview?since=` - combined Overview payload for cost, uptime,
    active calls, and extension registration KPI tiles.
  - `GET /api/cost/timeseries?since=&bucket=` - bucketed cost totals backing
    the new trend chart.
  - `GET /api/calls` - extended with `live_transcript`, `batch_transcript`,
    and `in_progress` boolean fields per call, using the new correlation from
    Scope item 5. A started call with no `call.ended` event appears as
    in-progress immediately; legacy rows without an end event are treated as
    stale once their last event is older than a short grace window.
  - A call-detail JSON endpoint backing the new per-call route (e.g.
    `GET /api/calls/{call_id}/turns`, replacing the current
    `GET /api/turns?call_id=`).
- New page routes: `/calls` (replaces the Overview's inline list as the
  primary calls view), `/calls/{call_id}` (replaces `/transcript?call_id=`),
  `/cost` (redesigned in place). `/parity` and `/transcriber` keep their
  routes with revised content per Scope items 2 and 7.
- All endpoints stay read-only and side-effect free. Secrets are already
  stripped at the source by `trace_events.redact`; the Zabbix client
  performs no unredaction and never logs its API token.

## Observability Contract

- The dashboard continues to rely on source-side redaction; it never
  reverses it and introduces no new secret-bearing log output.
- The Zabbix API token is treated as a secret: never logged, never returned
  in any `/api/*` response, present in `.env.example` as a key name only.
- No new local persistence of Zabbix data. Uptime figures are computed
  per-request from the Zabbix API and not cached to disk, avoiding a second
  history store alongside Zabbix's own.
- The service continues to log to journald under `voicebot-dashboard.service`.
- Acceptance evidence (screenshots, captured page HTML, `curl` of `/api/*`
  endpoints) is stored under ignored `runtime/` and linked from `PLANS.md`,
  never pasted inline.

## Acceptance Criteria

- `ruff check` passes on the changed/added Python under
  `vms/asterisk/services/dashboard/`, `vms/asterisk/services/livekit/`, and
  `vms/asterisk/services/pipecat/`; `shellcheck` passes on any changed
  installer/provisioning shell code.
- The declarative verify target for the dashboard is extended to cover the
  new/changed endpoints (`/api/overview`, `/api/uptime`, `/api/extensions`,
  `/api/cost/timeseries`, the extended `/api/calls`, the new call-detail
  endpoint) and confirms each renders a valid response.
- Live runtime behavior is proven with a real or replayed call: the
  call-detail page shows the animated STT-output -> LLM-response ->
  TTS-input sequence with per-stage latency and lane for that call; a
  just-started call appears as in-progress on Overview/Calls within the
  polling interval; the Overview's VM-uptime tile shows real data for all
  three VMs; the extensions tile shows the registered count and concrete
  extension numbers; at least one call shows both transcript status badges
  correctly (one true, one false, or both true) after the new correlation
  field is populated; the Cost page's trend chart renders more than one
  bucket over a real time range. Evidence is linked from `PLANS.md`.
- No secrets, customer data, or runtime artifacts are tracked by git.
  `.env.example` carries only key names and non-secret defaults.

## Follow-Ups

- Real per-stage `duration_ms` instrumentation for the stt/llm/tts request/
  response boundary in both agents (carried over from `spec02`, still its
  own spec).
- Live streaming (its own spec): WebSocket or SSE push, a fully live
  active-call view, and a barge-in timeline (carried over from `spec02`).
  Propose a matching `TODO.md` entry for operator approval; do not add it
  unilaterally.
