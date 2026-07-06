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
  `infra/libvirt/create-cloudinit-vm.sh`.
- **Asterisk VM (`VM` in the Makefile).** Runs Asterisk 22 LTS built from
  source by `install.sh`. Templates under `asterisk/*.tmpl` render to
  `/etc/asterisk/{pjsip.conf, pjsip.d/<ext>.conf, extensions.conf, rtp.conf}`.
  A local-Whisper transcriber (`transcriber.service`, installed by
  `scripts/setup-transcriber.sh`, code under `/opt/transcriber/`) watches
  `/var/spool/asterisk/monitor/` and writes `<recording>.txt` next to each
  `<recording>.wav`. Voicebot lanes (LiveKit stack, Pipecat stack) run on
  this VM under Docker; their installers live under `services/livekit/`
  and `services/pipecat/`.
- **SBC VM (`SBC_VM`).** Runs OpenSIPS 3.6 LTS with rtpengine as a
  stateless SIP proxy and RTP relay. `sbc/install.sh` renders
  `sbc/opensips.cfg.tmpl` and `sbc/rtpengine.conf.tmpl` into
  `/etc/opensips/opensips.cfg` and `/etc/rtpengine/rtpengine.conf`. Both
  daemons log to syslog (`local0` for opensips, `local1` for rtpengine)
  and to their systemd journals.
- **Monitoring VM (`MONITORING_VM`).** Runs Zabbix 7.0 LTS + PostgreSQL,
  Apache serving the Zabbix web UI, and Grafana with the Zabbix
  datasource plugin. Provisioned by `monitoring/install.sh`. Domain-side
  metric collectors are `monitoring/asterisk-metrics.py`,
  `monitoring/opensips-mi.py`, and `monitoring/rtpengine-metrics.sh`;
  Grafana dashboards live as JSON alongside them.
- **Zabbix agent (all monitored VMs).** `monitoring/setup-zabbix-agent.sh`
  installs zabbix-agent2 on each node with a rendered
  `zabbix-agent-lab.conf` pointing at `MONITORING_IP`.
- **Test-caller and utterance suite.** `services/test-caller/` synthesizes
  a fixed WAV corpus via ElevenLabs and drives repeated baresip calls for
  voicebot benchmarking. `services/common/` holds the shared
  model/cost/usage bookkeeping used by both voicebot lanes.

## Boundaries

- Template files under `asterisk/`, `sbc/`, and `monitoring/` are sources;
  their rendered outputs on the VMs are not. Re-running the matching
  installer overwrites the rendered file.
- Secrets are per-VM. `.env` is never rsynced by any `make deploy` target
  and never checked into git; only `.env.example` is tracked.
- The SBC is a stateless proxy, not a topology-hiding B2BUA. Signaling
  and media both pass through it, but session state does not live there.
- Voicebot lanes are comparison surfaces on the Asterisk VM. Each lane
  isolates its containers under Docker; they never edit each other's
  state, and both consume shared credentials (`OPENAI_API_KEY`,
  `ELEVENLABS_API_KEY`) from the Asterisk VM's `.env`.
- Real IPs are DHCP-allocated by the libvirt default network. Read them
  from `virsh net-dhcp-leases default` after boot; no config file may
  hardcode a last-seen IP.

## Interactions

- **SIP signaling and RTP media** flow: baresip on host ->
  `${SBC_IP}:5060` (UDP) -> OpenSIPS + rtpengine -> `${ASTERISK_IP}:5060`
  -> Asterisk PJSIP. On the return leg (`Dial(PJSIP/<ext>)` B2BUA
  outbound), Asterisk originates an INVITE that must NOT be looped back
  by the SBC; the initial-INVITE branch in `sbc/opensips.cfg.tmpl` is
  direction-aware (see decisions.md DEC-005).
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
  on each monitored VM. Grafana queries Zabbix via the datasource
  provisioned in `monitoring/grafana-datasource-zabbix.yaml`; dashboards
  provisioned via `monitoring/grafana-dashboard-provider.yaml`.
- **Voicebot flow.** LiveKit lane: SIP GW <-> LiveKit SFU <-> agent
  worker; Pipecat lane: Asterisk ARI ExternalMedia (slin16) <-> Pipecat
  agent. Both agents call OpenAI (Whisper STT, gpt-4o-mini LLM, tts-1
  TTS) so the cost comparison is fair. Turn/usage logging goes to
  `/var/lib/voicebot/usage.jsonl`; `services/common/usage_summary.py`
  aggregates it.
- **Operator control.** All install/verify/deploy/logs operations are
  wrapped by the root `Makefile`. Each VM has its own trio
  (`install / verify / deploy / logs` for Asterisk;
  `install-sbc / verify-sbc / deploy-sbc / logs-sbc`;
  `install-monitoring / verify-monitoring / deploy-monitoring /
  logs-monitoring`), plus per-lane voicebot targets.

## Non-Goals

- This lab is not a production HA deployment. There is no failover,
  clustering, or geo-redundancy.
- The SBC does not do topology-hiding B2BUA today; it is a stateless
  proxy that inserts Record-Route/Path headers and delegates media to
  rtpengine.
- Voicebot lanes are stable only when their VAL-VOICEBOT-* contracts
  hold. Adding a new voicebot backend requires new VAL-* contracts.
