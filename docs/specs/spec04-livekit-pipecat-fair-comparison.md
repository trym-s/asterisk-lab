# Spec spec04 - LiveKit vs Pipecat Fair Comparison

> Governed by `docs/runbooks/spec-rules.md`. A spec is a stable contract, not a
> changelog. Daily progress belongs in `PLANS.md`.

- **Status:** Draft
- **Owner:** operator
- **Created:** 2026-07-07

## Goal

An operator opens the voicebot dashboard and sees a LiveKit vs Pipecat
comparison built as a gated benchmark report, not a usage leaderboard: a
Fairness Gate showing whether the two lanes were actually run under
comparable conditions, a Paired Quality panel scoring both lanes against the
same scripted utterance corpus, a Latency Decision panel with per-stage
percentiles and sample counts, a Reliability panel that separates comparable
neutral outcomes from lane-specific diagnostics, and Cost kept as normalized
context rather than the headline number. No lane-selection "winner" number
renders until the run passes explicit fairness preconditions; until then the
dashboard shows an "as-deployed stack comparison" labeled observational.

## Problem Statement

`docs/debates/livekit-pipecat-fair-comparison/transcript.md` (Codex/Claude
debate, closed `discussion_done` 2026-07-07) established that the current
`/parity` view (`vms/asterisk/services/dashboard/app/data.py:497`,
`templates/parity.html:11`) is not decision-worthy: it averages
timestamp-delta latency and estimated cost per lane with no pairing by
scripted utterance, no sample count, and no signal about whether the two
runs were actually comparable. Both lanes share model/prompt/tool/corpus
selection via `voicebot_profile.py` and emit matching `profile.loaded`
hashes, but they diverge in ways the current dashboard hides:

- **Media path**: LiveKit runs Asterisk -> SIP GW -> SFU -> agent with a
  trunk that can negotiate opus/g722/ulaw; Pipecat runs Asterisk AudioSocket
  TCP -> agent at a fixed 8 kHz slin16.
- **Interruption/echo instrumentation**: Pipecat explicitly emits
  `echo_filtered` and `barge_in.stop_bot_audio` trace events; LiveKit
  delegates interruption handling to its VoicePipelineAgent internals and
  emits no equivalent discrete event. A naive Reliability panel built
  directly from `events.jsonl` would read as "LiveKit: 0 echo events" and
  misrepresent an instrumentation gap as a reliability advantage - on
  exactly the axis (behavior under identical conditions) the operator cares
  about most.
- **Usage-evidence strength**: LiveKit records plugin metrics/tokens when
  available; Pipecat currently estimates LLM tokens and logs cumulative
  AudioSocket STT seconds. These are not equally strong evidence and must
  not be presented as equivalent.
- **Latency evidence**: both agents mostly lack real per-stage `duration_ms`
  (only the `tool` stage has it today); the dashboard derives latency from
  timestamp deltas, which is an approximation, not a measurement.

The operator's stated priority is explicit: this comparison is not about
which lane costs or uses more, it is about response-quality and ms-latency
performance under truly identical conditions.

## Scope

1. **Fairness Gate / Config Diff panel.** New dashboard view showing, per
   comparison run, a pass/warn/not-comparable status for each of: model
   profile + prompt hash + tool schema hash + corpus hash + repo revision
   (from existing `profile.loaded` events), audio codec/sample rate/media
   path, VAD/endpointing config, interruption/echo instrumentation parity,
   framework/dependency version, run/utterance pairing id, and
   usage-evidence parity (measured vs estimated). No headline "winner"
   number renders anywhere in the dashboard unless framework-isolated mode
   passes the media and instrumentation gates for that run; otherwise only
   an "as-deployed stack comparison" renders, explicitly labeled
   observational, with every divergent row visible.
2. **Paired Quality panel.** Grouped by `run_id` + `utterance_id`, LiveKit
   and Pipecat shown side by side for the same test-caller script. Scored
   against a new human-authored expected-answer corpus (expected intent,
   tool-required yes/no, expected source doc(s), required/forbidden key
   facts) covering the existing scripted utterances in
   `vms/asterisk/services/test-caller/`. Deterministic/rubric signals only:
   STT CER/WER against the scripted utterance, tool-called-when-required,
   `lookup_docs` source hit, required facts present / forbidden facts
   absent, extra-turn/echo/self-talk indicator. No LLM-judge scoring runs
   inside the dashboard (see Non-Goals); items outside deterministic
   scoring are shown as "needs review."
3. **Latency Decision panel.** Per stage (user-audio end -> STT final ->
   LLM request -> first/complete response -> TTS request -> first audio ->
   full turn), show p50 always, p95 only above a minimum sample floor
   (default N >= 20, configurable), N shown next to every stat, and each
   value labeled `measured`, `approx`, or `mixed` using the existing
   duration_ms-vs-timestamp-delta rule from `derive_stage_latency()`.
4. **Reliability panel, two rows.** (a) Comparable neutral outcomes usable
   in a lane-selection score: call completed, expected turns reached, no
   missing STT/LLM/TTS stage, no error event, no stale call, no empty final
   transcript, no duplicate/extra turn - built from existing `events.jsonl`
   fields available to both lanes today. (b) Lane-specific diagnostics
   (`echo_filtered` count, `barge_in.stop_bot_audio` count, and any other
   event only one lane currently emits) displayed but explicitly excluded
   from any score, labeled per-lane instrumentation, until both lanes emit
   equivalent events (see Follow-Ups).
5. **Cost panel, kept as normalized context.** Cost per successful correct
   turn and per complete scripted corpus run, not the primary decision
   axis. Rows sourced from measured usage (LiveKit plugin metrics/tokens)
   and estimated usage (Pipecat estimated tokens/STT seconds) stay visibly
   separate; they are never blended into one number.
6. **Run pairing metadata.** A `run_id` (and, where useful,
   `utterance_id`) becomes a first-class grouping key across the Paired
   Quality and Latency panels so both lanes' results for the same scripted
   corpus execution can be compared side by side rather than averaged
   independently per lane.

## Non-Goals

- No in-dashboard LLM-judge scoring. The dashboard must not call a model
  provider (AGENTS.md SS6, DEC-008); this is a hard architectural
  constraint independent of the fairness argument. A future LLM-judge score
  is an offline benchmark artifact only: a separate runner with a pinned
  judge model, pinned prompt, `judge_profile` hash, temperature, and rubric
  version, writing a readable artifact the dashboard may later display with
  "judge-assisted" provenance beside the deterministic rubric score. Wiring
  that runner is a follow-up, not part of this spec.
- No forced audio/codec parity between the two lanes in this spec. Making
  LiveKit's SFU path and Pipecat's AudioSocket path negotiate the same
  codec/sample rate is real work given their divergent media paths (SFU vs
  AudioSocket); this spec surfaces the divergence honestly via the Fairness
  Gate ("framework-isolated: not yet enforced") rather than closing it.
  Forcing parity is a follow-up.
- No real per-stage `duration_ms` instrumentation added by this spec beyond
  what already exists (`tool` stage only). Latency stays ts-delta-approximated
  elsewhere, labeled `approx`, carried over as a follow-up from `spec02`.
- No new LiveKit-side interruption/echo event instrumentation in this spec.
  The Reliability panel ships with the two-row split (comparable vs
  lane-specific) so the gap is labeled rather than hidden; adding matching
  LiveKit events is a follow-up.
- No WebSocket, SSE, or server push. All updates remain HTTP polling, same
  as `spec02`/`spec03`.
- No new authentication surface beyond what `spec02` already ships.
- No dashboard write path. The dashboard still never mutates
  `/var/lib/voicebot/*.jsonl` or `/var/spool/asterisk/monitor/`, and never
  calls a model provider (AGENTS.md SS6).
- No frontend build chain. Server-rendered Jinja2 plus vendored static
  assets (Tabler CSS/JS, Chart.js) remains the stack.

## Architecture Contract

- The dashboard remains a FastAPI + Jinja2 app deployed as
  `voicebot-dashboard.service` on the Asterisk VM, same deployment shape as
  `spec02`/`spec03`.
- All new panels are read-only aggregations over existing
  `/var/lib/voicebot/{events,usage,turns}.jsonl` inputs, reusing
  `vms/asterisk/services/common/` (`trace_events`, `usage`,
  `usage_summary`). No new outbound dependency beyond what `spec03` already
  added (Zabbix API for uptime; not used by this spec's panels).
- The new human-authored expected-answer corpus is a new, versioned,
  read-only fixture (not runtime data) living alongside
  `vms/asterisk/services/test-caller/`, keyed by the same `utterance_id`
  used in `utterances.tsv`. The dashboard reads it read-only; it is not
  runtime evidence and is tracked in git like any other fixture.
- `run_id` becomes a value the dashboard can group by. If it does not
  already exist as a stable field on relevant trace events, this spec adds
  it as a new field on the existing `call`/`profile.loaded` events (not a
  new event, not a schema version bump), following the same
  additive-field pattern spec03 used for the recording-correlation id.
- Data flow direction is preserved: JSONL files and the new expected-answer
  fixture flow one way into the dashboard's read/aggregate/render pipeline;
  nothing flows back toward the lanes or Asterisk.

## Config Contract

- New env keys, names and non-secret defaults only in `.env.example`,
  consumed from `/etc/asterisk-lab/env` on the Asterisk VM:
  `VOICEBOT_DASHBOARD_LATENCY_MIN_N` (minimum sample floor before p95
  renders, default `20`), `VOICEBOT_DASHBOARD_EXPECTED_CORPUS_PATH`
  (path to the new expected-answer fixture, defaulting to a path under
  `vms/asterisk/services/test-caller/`).
- No new secrets introduced by this spec.
- `make deploy` continues to never transport `.env`/`.env.*` (DEC-004,
  DEC-007).

## API Contract

- New read-only JSON endpoints:
  - `GET /api/comparison/fairness?run_id=` - Fairness Gate status rows for
    a given comparison run (or latest, if `run_id` omitted).
  - `GET /api/comparison/quality?run_id=` - Paired Quality rows keyed by
    `utterance_id`, both lanes side by side, with rubric scores.
  - `GET /api/comparison/latency?run_id=` - per-stage latency stats (p50,
    p95 gated by sample floor, N, source label) per lane.
  - `GET /api/comparison/reliability?run_id=` - the two-row Reliability
    payload (comparable neutral outcomes; lane-specific diagnostics).
  - `GET /api/comparison/cost?run_id=` - normalized cost-per-successful-turn
    and cost-per-corpus-run per lane, measured vs estimated rows separated.
- New page route: `/comparison` (or equivalent), replacing `/parity` as the
  primary LiveKit-vs-Pipecat view. `/parity` may redirect to `/comparison`
  or stay as a legacy alias; final naming is an implementation detail, not
  a contract change beyond "the flat unpaired `/parity` table is no longer
  the primary comparison surface."
- All endpoints stay read-only and side-effect free, consistent with
  `spec02`/`spec03`.

## Observability Contract

- The dashboard continues to rely on source-side redaction
  (`trace_events.redact`); it never reverses it and introduces no new
  secret-bearing log output.
- No new local persistence beyond the existing JSONL files and the new
  read-only expected-answer fixture; comparison figures are computed
  per-request, not cached to a second store.
- The service continues to log to journald under
  `voicebot-dashboard.service`.
- Acceptance evidence (screenshots, captured page HTML, `curl` of
  `/api/comparison/*` endpoints) is stored under ignored `runtime/` and
  linked from `PLANS.md`, never pasted inline.

## Acceptance Criteria

- `ruff check` passes on the changed/added Python under
  `vms/asterisk/services/dashboard/` and any changed lane agent code
  (`livekit/agent/`, `pipecat/agent/`) if the `run_id` field is added
  there.
- The declarative verify target for the dashboard is extended to cover the
  new `/api/comparison/*` endpoints and confirms each renders a valid
  response.
- Live runtime behavior is proven with a real or replayed paired run across
  both lanes using the same scripted corpus: the Fairness Gate shows the
  real pass/warn/not-comparable status per row (including "not yet
  enforced" for audio/codec parity, per Non-Goals); the Paired Quality
  panel shows at least one utterance scored on both lanes; the Latency
  panel shows N alongside p50 for at least one stage and correctly
  suppresses p95 below the sample floor; the Reliability panel shows the
  comparable-outcomes row populated for both lanes and the lane-specific
  diagnostics row correctly labeled (not blended into a shared score); the
  Cost panel shows measured (LiveKit) and estimated (Pipecat) rows kept
  visibly separate. Evidence is linked from `PLANS.md`.
- No secrets, customer data, or runtime artifacts are tracked by git.
  `.env.example` carries only key names and non-secret defaults.

## Follow-Ups

- Force or record audio codec/sample-rate parity between LiveKit's SFU
  path and Pipecat's AudioSocket path so "framework-isolated" mode can
  actually be enforced rather than shown as "not yet enforced." Its own
  spec: it touches `vms/asterisk/etc/asterisk/pjsip.conf.tmpl` trunk codec
  negotiation and the Pipecat AudioSocket fixed-rate assumption.
  Propose a matching `TODO.md` entry for operator approval.
- Add equivalent interruption/echo/barge-in trace instrumentation on the
  LiveKit lane so the Reliability panel's lane-specific diagnostics row can
  be promoted into the comparable-outcomes row. Propose a matching
  `TODO.md` entry for operator approval.
- Real per-stage `duration_ms` instrumentation for the STT/LLM/TTS
  request/response boundary in both agents (carried over from `spec02` and
  `spec03`, still its own spec).
- Offline LLM-judge benchmark runner (pinned judge model/prompt/rubric,
  writing a separate artifact) for quality dimensions the deterministic
  rubric cannot cover, displayed by the dashboard with "judge-assisted"
  provenance once it exists. Propose a matching `TODO.md` entry for
  operator approval.

## References

- Debate transcript (raw, ignored by git):
  `docs/debates/livekit-pipecat-fair-comparison/transcript.md` (converged
  `discussion_done`, 2026-07-07).
