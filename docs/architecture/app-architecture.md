# Application Architecture

The lab is a three-VM Debian 13 / Ubuntu 26.04 stack plus optional voicebot
lanes that co-locate on the Asterisk VM. A host machine drives the lab
through baresip (softphone) and Makefile targets. Every runtime config is
rendered from a template in this repository; nothing edited directly on a
VM is authoritative.

## Components

- **Host machine.** Runs baresip against the SBC (or Asterisk directly),
  runs `virsh` / `virt-install` under libvirt to provision VMs, and holds
  the operator-facing Makefile. Host bootstrap lives in
  `infra/libvirt/setup-host.sh`; cloud-init VM creation in
  `infra/libvirt/create-cloudinit-vm.sh`. Deploy targets rsync role payloads
  (shaped by `infra/deploy/*.filter`) to `/opt/asterisk-lab/current` on the VMs.
- **Asterisk VM (`VM` in the Makefile).** Runs Asterisk 22 LTS built from
  source by the root `install.sh`. Templates under
  `vms/asterisk/etc/asterisk/*.tmpl` render to
  `/etc/asterisk/{pjsip.conf, pjsip.d/<ext>.conf, extensions.conf, rtp.conf}`.
  A local-Whisper transcriber (`transcriber.service`, installed by
  `infra/scripts/setup-transcriber.sh`, code under `/opt/transcriber/`) watches
  `/var/spool/asterisk/monitor/` and writes `<recording>.txt` next to each
  `<recording>.wav`. Voicebot lanes (LiveKit stack, Pipecat stack) run on
  this VM under Docker; their installers live under
  `vms/asterisk/services/livekit/` and `vms/asterisk/services/pipecat/`.
- **Voicebot observability dashboard (Asterisk VM, spec02).** A read-only
  FastAPI + Tabler service under `vms/asterisk/services/dashboard/` that
  reads `/var/lib/voicebot/{events,usage,turns}.jsonl` and
  `/var/spool/asterisk/monitor/` and renders four polling pages (parity,
  cost/usage, turn transcript, batch transcriber status) plus a JSON
  `/api/*` surface. It is not a container: `install.sh` provisions a `uv`-
  managed venv at `/opt/voicebot-dashboard/venv` (kept outside the
  rsync'd `/opt/asterisk-lab/current` payload so it survives redeploys,
  mirroring the transcriber) and a `voicebot-dashboard.service` systemd
  unit. Binds `127.0.0.1:8099` by default; reached over an SSH tunnel. It
  never writes to the sinks it reads and never calls a model provider. See
  `docs/specs/spec02-voicebot-observability-dashboard.md` and DEC-008 for
  a read-path gotcha in `vms/asterisk/services/common`'s default-path helpers.
- **SBC VM (`SBC_VM`).** Runs OpenSIPS 3.6 LTS with rtpengine as a
  stateless SIP proxy and RTP relay. `vms/sbc/install.sh` renders
  `vms/sbc/etc/opensips/opensips.cfg.tmpl` and
  `vms/sbc/etc/rtpengine/rtpengine.conf.tmpl` into
  `/etc/opensips/opensips.cfg` and `/etc/rtpengine/rtpengine.conf`. Both
  daemons log to syslog (`local0` for opensips, `local1` for rtpengine)
  and to their systemd journals.
- **Monitoring VM (`MONITORING_VM`).** Runs Zabbix 7.0 LTS + PostgreSQL,
  Apache serving the Zabbix web UI, and Grafana with the Zabbix
  datasource plugin. Provisioned by `vms/monitoring/install.sh` (which
  calls `vms/monitoring/provision-observability.py`). Domain-side metric
  collectors live under `vms/monitoring/usr/local/bin/`; Grafana
  dashboards and datasource provisioning live under
  `vms/monitoring/etc/grafana/provisioning/`.
- **Zabbix agent (all monitored VMs).** `vms/monitoring/setup-zabbix-agent.sh`
  installs zabbix-agent2 on each node with a rendered
  `zabbix-agent-lab.conf` pointing at `MONITORING_IP`; verified by
  `vms/monitoring/verify-agent.sh`.
- **Test-caller and utterance suite.** `vms/asterisk/services/test-caller/`
  synthesizes a fixed WAV corpus via ElevenLabs and drives repeated baresip
  calls for voicebot benchmarking. `vms/asterisk/services/common/` holds the
  shared model/cost/usage/trace bookkeeping used by both voicebot lanes and
  read by the dashboard.

## Boundaries

- Template files under `vms/asterisk/`, `vms/sbc/`, and `vms/monitoring/`
  are sources; their rendered outputs on the VMs are not. Re-running the
  matching installer overwrites the rendered file.
- The observability dashboard reads `/var/lib/voicebot/*.jsonl` and
  `/var/spool/asterisk/monitor/` read-only; it never writes to them and
  never mutates any rendered config.
- Secrets are per-VM. VM secrets live in `/etc/asterisk-lab/env`. `.env` is
  never rsynced by any `make deploy` target and never checked into git; only
  `.env.example` is tracked. Local host workflows may still use ignored
  repo-local `.env` files.
- `/opt/asterisk-lab/current` on each VM is disposable deploy payload, not a
  git repository or acceptance source.
- The SBC is a stateless proxy, not a topology-hiding B2BUA. Signaling
  and media both pass through it, but session state does not live there.
- Voicebot lanes are comparison surfaces on the Asterisk VM. Each lane
  isolates its containers under Docker; they never edit each other's
  state, and both consume shared credentials (`OPENAI_API_KEY`,
  `ELEVENLABS_API_KEY`) from the Asterisk VM lab env.
- Real IPs are DHCP-allocated by the libvirt default network. Read them
  from `virsh net-dhcp-leases default` after boot; no config file may
  hardcode a last-seen IP.

## Interactions

- **SIP signaling and RTP media** flow: baresip on host ->
  `${SBC_IP}:5060` (UDP) -> OpenSIPS + rtpengine -> `${ASTERISK_IP}:5060`
  -> Asterisk PJSIP. On the return leg (`Dial(PJSIP/<ext>)` B2BUA
  outbound), Asterisk originates an INVITE that must NOT be looped back
  by the SBC; the initial-INVITE branch in
  `vms/sbc/etc/opensips/opensips.cfg.tmpl` is direction-aware (see
  decisions.md DEC-005).
- **Path/Record-Route handling.** OpenSIPS inserts `Record-Route` and
  `Path` headers using `${SBC_IP}`. PJSIP AORs include `support_path=yes`
  so Asterisk stores the SBC-inserted `Path:` header and can address
  registered endpoints correctly on B2BUA legs.
- **Recording and transcription.** Dialplan pattern `_10XX` starts
  `MixMonitor` before dialing. Files land under
  `/var/spool/asterisk/monitor/`; the transcriber watcher picks each WAV
  up, runs local Whisper, and writes the sibling `.txt`. Model and
  language come from `WHISPER_MODEL` (default `base`) and
  `WHISPER_LANGUAGE` (default `tr`) env vars in the systemd unit;
  override via a `transcriber.service.d/*.conf` drop-in.
- **Monitoring pull.** Zabbix server pulls metrics from `zabbix-agent2`
  on each monitored VM. Grafana queries Zabbix via the datasource and
  dashboards provisioned under `vms/monitoring/etc/grafana/provisioning/`.
- **Voicebot flow.** LiveKit lane: SIP GW <-> LiveKit SFU <-> agent
  worker; Pipecat lane: Asterisk ARI ExternalMedia (slin16) <-> Pipecat
  agent. Both agents call OpenAI (Whisper STT, gpt-4o-mini LLM, tts-1
  TTS) so the cost comparison is fair. Trace events land in
  `/var/lib/voicebot/events.jsonl` (schema `voicebot-events-v1`) and
  usage/cost in `/var/lib/voicebot/usage.jsonl`;
  `vms/asterisk/services/common/usage_summary.py` aggregates the latter and
  the observability dashboard reads both to render per-turn latency and
  cost without touching the lanes.
- **Operator control.** All install/verify/deploy/logs operations are
  wrapped by the root `Makefile`. Each VM has its own trio
  (`install / verify / deploy / logs` for Asterisk;
  `install-sbc / verify-sbc / deploy-sbc / logs-sbc`;
  `install-monitoring / verify-monitoring / deploy-monitoring /
  logs-monitoring`), plus per-lane voicebot targets and
  `install/verify/deploy/logs-voicebot-dashboard` for the dashboard.

## Non-Goals

- This lab is not a production HA deployment. There is no failover,
  clustering, or geo-redundancy.
- The SBC does not do topology-hiding B2BUA today; it is a stateless
  proxy that inserts Record-Route/Path headers and delegates media to
  rtpengine.
- Voicebot lanes are stable only when parity is proven with fresh runtime
  evidence. Adding a new voicebot backend requires explicit validation.
