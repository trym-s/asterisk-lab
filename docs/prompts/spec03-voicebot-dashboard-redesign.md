# Kickoff Prompt - spec03 voicebot dashboard redesign

Read `AGENTS.md`, `PLANS.md`, and the governing spec:

```text
docs/specs/spec03-voicebot-dashboard-redesign.md
```

Implement the spec end to end. Redesign the Overview into click-through KPI
tiles (cost with a time range, VM uptime/downtime, active calls now); merge
live-STT and batch-transcription status onto a Calls page; turn the call
detail view into an animated step-by-step STT/LLM/TTS flow with per-stage
latency and lane, driven by the existing HTTP polling (no WebSocket); add a
cost trend chart plus drill-down; add a Zabbix host-uptime item and a
read-only Zabbix API client for the uptime KPI; add the Asterisk
channel/uniqueid to the existing `call`-stage trace event in both the
LiveKit and Pipecat agents to correlate recordings with `call_id`. Keep the
no-build-chain FastAPI + Jinja2 + vendored Tabler/Chart.js stack. Extend the
declarative verify script for the new/changed endpoints.

Keep `PLANS.md` updated after meaningful work, preserve user changes, keep
secrets and runtime data out of git, run the relevant checks, and commit all
agent-made changes with an English Conventional Commit.
