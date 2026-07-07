# PLANS.md - asterisk-lab live execution state

> Governed by `docs/runbooks/plan-rules.md`. Keep around 100 to 250 lines.
> Update after every meaningful step. Link artifacts; never paste long output.
> Always carry a state.
> When the governing spec is complete, archive this file under `docs/archive/plan/`.
> The next spec starts with a fresh root `PLANS.md` from `docs/templates/PLANS.md`.

**Status:** In progress - local implementation for spec03 is in place and
locally verified. Live VM deploy/verification and real or replayed call
evidence are still pending before the spec can close.
**Governing spec:** `docs/specs/spec03-voicebot-dashboard-redesign.md` (Draft)
**Last updated:** 2026-07-07

## Active milestones

- [ ] Implement spec03: Overview KPI tiles (cost, VM uptime/downtime, active
  calls, registered extensions), merged Calls transcript-status badges and
  extension roster, animated call-detail flow with STT-output / LLM-response /
  TTS-input labels, cost trend + drill-down, Zabbix host-uptime item, and the
  call/recording correlation field in both lane agents.

## Blockers

- none

## Canonical evidence

- `docs/specs/spec01-adopt-agent-harness.md` and
  `docs/specs/spec02-voicebot-observability-dashboard.md` are both Done.
- `docs/memory/decisions.md` DEC-001..DEC-008 covers governance, the deploy
  boundary, and the read-vs-write default-path gotcha found while verifying
  spec02 live.
- Local spec03 implementation evidence:
  `runtime/spec03-dashboard-redesign/dashboard-tests.log`,
  `runtime/spec03-dashboard-redesign/common-tests.log`,
  `runtime/spec03-dashboard-redesign/ruff.log`,
  `runtime/spec03-dashboard-redesign/shellcheck.log`,
  `runtime/spec03-dashboard-redesign/py-compile.log`, and
  `runtime/spec03-dashboard-redesign/route-smoke.log`.

## Recent updates

- 2026-07-07 - Implemented the first spec03 code pass locally: industrial
  console dashboard UI, Overview KPIs, `/calls` and `/calls/{call_id}`,
  extension roster, live-call state, transcript badges, STT-output /
  LLM-response / TTS-input turn flow, cost time series + drill-down,
  Zabbix uptime client, LiveKit/Pipecat correlation payloads, LiveKit
  terminal event hooks, LiveKit PJSIP correlation headers, monitoring
  host-uptime items, and expanded dashboard verify checks. Local tests,
  ruff, shellcheck, py_compile, and uvicorn route smoke are green; live
  deploy/VM evidence remains.
- 2026-07-07 - Began implementation pass for spec03. Expanded the spec to
  cover the operator's added dashboard questions: how many and which SIP
  extensions are registered, whether a just-started call is visible
  immediately, and the exact STT-output / TTS-input text in the call-detail
  flow.
- 2026-07-07 - Drafted spec03 (voicebot dashboard redesign) after a
  brainstorming session with the operator: Overview KPI tiles, merged
  live/batch transcript status on the Calls page, an animated call-detail
  flow, a cost trend + drill-down view, a new Zabbix host-uptime item, and
  the Asterisk channel/uniqueid correlation field on both lane agents'
  `call`-stage trace event. Paired kickoff prompt at
  `docs/prompts/spec03-voicebot-dashboard-redesign.md`.
- 2026-07-07 - Closed spec01: deployed the current `/opt/asterisk-lab/current`
  payload to the SBC and monitoring VMs (`make deploy-sbc`,
  `make deploy-monitoring`); `vms/sbc/verify.sh` (11/11) and
  `vms/monitoring/verify.sh` (20/20) both passed. All three VMs now match
  revision `aaa08c5f1d68`. Archived the prior `PLANS.md` to
  `docs/archive/plan/2026-07-07-spec01-deploy-sbc-monitoring.md` and marked
  spec01 Done.
- 2026-07-07 - Closed spec02 (voicebot observability dashboard): deployed
  and verified live on the Asterisk VM (12/12 `verify.sh` checks; all four
  panels proven against 33 real calls already on disk). Archived to
  `docs/archive/plan/2026-07-07-spec02-voicebot-observability-dashboard.md`.

## Archive pointers

- `docs/archive/plan/2026-07-07-spec01-deploy-sbc-monitoring.md`
- `docs/archive/plan/2026-07-07-spec02-voicebot-observability-dashboard.md`
