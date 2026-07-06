# Testing

## Checks

```bash
# Per-VM smoke checks (declarative; exit non-zero on first failing check)
make verify                # Asterisk VM: asterisk version, pjsip endpoints,
                           # dialplan 600, monitor dir owner, transcriber
                           # service, whisper model cache, etc.
make verify-sbc            # SBC VM: opensips + rtpengine service status,
                           # config sanity, socket binding
make verify-monitoring     # Monitoring VM: zabbix-server, postgresql,
                           # apache2, grafana-server
make verify-zabbix-agent   # Any monitored node: zabbix-agent2 status

# CI-scope linters (also runnable locally)
shellcheck install.sh scripts/*.sh sbc/*.sh monitoring/*.sh services/*/install.sh
ruff check scripts/ services/
```

The GitHub Actions workflow under `.github/workflows/` runs shellcheck
and ruff on push and PR. VM-scoped verify targets are not run in CI
because they need a live Debian VM.

## Rules

- Run the relevant `verify` target on the affected VM before declaring
  work done. Report failures honestly; never weaken a check to make it
  pass.
- Voicebot changes must also satisfy the parity check in
  `VAL-VOICEBOT-PARITY-001.md`.
- Live runtime evidence (recordings, transcripts, trace logs) goes under
  ignored `runtime/` on the host or `/var/spool/`, `/var/lib/voicebot/`
  on the VMs, and is only linked (never pasted) from `PLANS.md`.
- Shellcheck SC1091 on `. .env` or `. /etc/os-release` is expected;
  suppress it with `# shellcheck source=/dev/null` on the line above
  each source. Do not disable SC1091 repo-wide.
