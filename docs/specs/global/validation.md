# Validation Model

Contracts under `docs/specs/domains/*/contracts/` define done. Each contract must include:

```text
Surface
Needs
Behavior
Evidence
```

Use `Fail`, `Oracle`, or `Scope` when needed to prevent ambiguity.

## Evidence Rules

- CLI behavior requires command, stdout/stderr summary, exit code, cwd, and env
  assumptions.
- SIP behavior requires relevant `asterisk -rx`, `sngrep`, service log, or
  packet observation evidence.
- Docker voicebot behavior requires compose/container status, logs, and call
  evidence from the dialed extension.
- Voicebot trace behavior requires fresh `/var/lib/voicebot/events.jsonl` rows
  grouped by lane, call ID, and turn ID, plus linked usage rows when cost or
  usage is in scope.
- Voicebot audio integrity requires test-caller timing manifests plus
  receive-side audio evidence such as Asterisk recordings, framework audio
  byte/duration counters, or both, as named by the contract.
- Voicebot observer behavior requires real HTTP/browser evidence, API response
  bodies, and source artifact rows that explain the rendered values.
- Voicebot benchmark/report behavior requires same-revision lane evidence,
  generated Markdown/JSON reports, and explicit pass/fail/inconclusive verdicts.
- Monitoring behavior requires `verify.sh`, `zabbix_get`, API, or dashboard
  reachability evidence as named by the contract.
- Source inspection alone cannot pass a real runtime contract unless the
  contract explicitly names source review as the oracle.

## Blocking Conditions

- Missing `.env` on a target VM blocks deployment validation.
- Shut off VMs block runtime validation.
- Dynamic DHCP drift blocks SBC/monitoring validation until `.env` is updated.
- Missing API keys block voicebot validation.
- Missing required evidence means blocked or failed, not passed.
