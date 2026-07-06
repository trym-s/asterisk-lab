# Spec Index

This directory is the canonical source of truth for supported behavior,
operator workflows, validation contracts, and durable design decisions.

## Read Order For Agents

1. Read [mission.md](file:///home/vlhnac/local_dev/lab/docs/specs/global/mission.md) to understand the whole lab.
2. Read [agent-routing.md](file:///home/vlhnac/local_dev/lab/docs/specs/global/agent-routing.md) to select a domain.
3. Read the selected `docs/specs/domains/<domain>/spec.md`.
4. Read the matching `docs/specs/domains/<domain>/contracts/VAL-*.md` before changing behavior.
5. Read `docs/specs/domains/<domain>/runbook.md` before deploying or operating that domain.
6. Read `docs/specs/domains/<domain>/decisions.md` when a design choice looks surprising.

## Directory Model

```text
docs/specs/global/       Repo-wide mission, conventions, environment, validation, routing.
docs/specs/domains/      Current truth for each subsystem.
docs/specs/changes/      Change proposals and migrations. Not current truth by itself.
```

Global contracts live under `docs/specs/global/contracts/`. Domain contracts live under
`docs/specs/domains/<domain>/contracts/`.

## Source-Of-Truth Rules

- Domain `spec.md` files define current supported behavior.
- `contracts/VAL-*.md` files define falsifiable acceptance criteria.
- `runbook.md` files define operator and agent procedure.
- `decisions.md` files explain durable rationale.
- `README.md` is onboarding, not acceptance.
- `PROCESS.md` is a current-state index, not acceptance.
- `NOTES.md` is personal rationale, not acceptance.
- `.claude/skills/*` can provide procedure, but contracts still define done.

## Domain Map

```text
asterisk    PBX install, PJSIP endpoints, dialplan, recordings, transcriber.
sbc         OpenSIPS, rtpengine, SIP routing, Path/Record-Route, media relay.
monitoring  Zabbix, Grafana, zabbix-agent2, lab metrics.
voicebot    LiveKit, Pipecat, test-caller, usage/turn logs, benchmarks.
```
