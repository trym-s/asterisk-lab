# PLANS.md - asterisk-lab live execution state

> Governed by `docs/runbooks/plan-rules.md`. Keep around 100 to 250 lines.
> Update after every meaningful step. Link artifacts; never paste long output.
> Always carry a state.
> When the governing spec is complete, archive this file under `docs/archive/plan/`.
> The next spec starts with a fresh root `PLANS.md` from `docs/templates/PLANS.md`.

**Status:** Done - spec03 implemented, deployed, and verified live across the
Asterisk, SBC, and monitoring VMs. Archived.
**Governing spec:** `docs/specs/spec03-voicebot-dashboard-redesign.md` (Done)
**Last updated:** 2026-07-07

## Active milestones

- [x] Implement spec03: Overview KPI tiles (cost, VM uptime/downtime, active
  calls, registered extensions), merged Calls transcript-status badges and
  extension roster, animated call-detail flow with STT-output / LLM-response /
  TTS-input labels, cost trend + drill-down, Zabbix host-uptime item, and the
  call/recording correlation field in both lane agents.

## Fixes found during live verification

- The dashboard initially missed Pipecat recording correlation because
  MixMonitor filenames carry the Asterisk `${UNIQUEID}` and the dashboard
  derived a hyphenated AudioSocket UUID, while Pipecat emits the same UUID
  compact as `call_id` / `uuid`. `/api/transcriber` could show the derived
  UUID, but `/api/calls` stayed at `correlation_status=missing`. Fixed by
  normalizing compact and hyphenated UUID lookup keys in the dashboard
  recording index and adding a regression test. Recorded as DEC-009.

## Canonical evidence

- Local implementation evidence:
  `runtime/spec03-dashboard-redesign/dashboard-tests.log`,
  `runtime/spec03-dashboard-redesign/common-tests.log`,
  `runtime/spec03-dashboard-redesign/ruff.log`,
  `runtime/spec03-dashboard-redesign/shellcheck.log`,
  `runtime/spec03-dashboard-redesign/py-compile.log`, and
  `runtime/spec03-dashboard-redesign/route-smoke.log`.
- Live VM smoke checks:
  `runtime/spec03-dashboard-redesign/live/verify-asterisk.log` (11/11),
  `runtime/spec03-dashboard-redesign/live/verify-sbc.log` (11/11),
  `runtime/spec03-dashboard-redesign/live/verify-monitoring.log` (20/20),
  `runtime/spec03-dashboard-redesign/live/verify-dashboard-after-uuid-fix.log`
  (19/19), plus monitored-node Zabbix agent checks under
  `runtime/spec03-dashboard-redesign/live/verify-zabbix-agent-*.log`.
- Live dashboard data evidence:
  `runtime/spec03-dashboard-redesign/live/evidence-summary.txt`,
  `runtime/spec03-dashboard-redesign/live/api-extensions-after-uuid-fix.json`,
  `runtime/spec03-dashboard-redesign/live/api-uptime-1h-after-uuid-fix.json`,
  `runtime/spec03-dashboard-redesign/live/api-overview-1h-after-uuid-fix.json`,
  `runtime/spec03-dashboard-redesign/live/api-cost-timeseries-24h-after-uuid-fix.json`,
  and `runtime/spec03-dashboard-redesign/live/api-calls-after-uuid-fix.json`.
- Fresh call evidence:
  `runtime/spec03-dashboard-redesign/live/drive-pipecat-active-calls.log`,
  `runtime/spec03-dashboard-redesign/live/api-calls-during-pipecat-active-1.json`,
  and
  `runtime/spec03-dashboard-redesign/live/api-overview-during-pipecat-active-1.json`
  show a just-started Pipecat call with `in_progress=true` in both Calls and
  Overview.
- Call-detail evidence:
  `runtime/spec03-dashboard-redesign/live/api-call-detail-20bad8d5-after-uuid-fix.json`
  and
  `runtime/spec03-dashboard-redesign/live/page-call-detail-20bad8d5-after-uuid-fix.html`
  show the STT-output / LLM-response / TTS-input sequence, approximate
  latencies, lane, and the matched recording file for call
  `20bad8d5f3625e45469ee6b9ab196bce`.

## Acceptance summary

- `/api/extensions` reported both configured extensions registered:
  `1001` and `1002`, both `Avail`.
- `/api/uptime?since=1h` reported Asterisk, SBC, and monitoring all `up`
  with `100.0` uptime percentage and Zabbix samples present.
- A fresh Pipecat call appeared as in-progress during polling on both
  Overview and Calls.
- The representative call detail showed Turkish STT output, LLM response,
  and exact TTS input text with approximate per-stage latency.
- `/api/calls` showed matched recordings after the UUID normalization fix;
  at least one matched call had `live_transcript=true` and
  `batch_transcript=false`, proving both transcript badges independently.
- `/api/cost/timeseries?since=24h&bucket=1h` returned four hourly buckets.
- Dashboard verify passed 19/19 on the live Asterisk VM after the final fix.

## Recent updates

- 2026-07-07 - Implemented the spec03 dashboard redesign: industrial console
  UI, Overview KPIs, `/calls` and `/calls/{call_id}`, extension roster,
  active-call state, transcript badges, STT-output / LLM-response /
  TTS-input turn flow, cost time series + drill-down, Zabbix uptime client,
  LiveKit/Pipecat correlation payloads, LiveKit terminal event hooks,
  LiveKit PJSIP correlation headers, monitoring host-uptime items, and
  expanded dashboard verify checks.
- 2026-07-07 - Deployed monitoring, Asterisk, dashboard, LiveKit, and
  Pipecat payloads to the live VMs. Verified Asterisk, SBC, monitoring,
  dashboard, and monitored-node Zabbix agents.
- 2026-07-07 - Drove a fresh host baresip -> SBC -> Asterisk -> Pipecat call
  through extension `1098` and captured in-progress dashboard polls showing
  the new call immediately visible.
- 2026-07-07 - Fixed compact-vs-hyphenated AudioSocket UUID correlation,
  redeployed the dashboard, and confirmed `/api/calls` now matches
  MixMonitor recordings for Pipecat rows.

## Archive pointers

- `docs/archive/plan/2026-07-07-spec01-deploy-sbc-monitoring.md`
- `docs/archive/plan/2026-07-07-spec02-voicebot-observability-dashboard.md`
