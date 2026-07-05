# Validation Model

Contracts under `domains/*/contracts/` define done. Each contract must include:

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
