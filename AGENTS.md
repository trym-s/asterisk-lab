# Agent Notes

## Spec-Driven Entry Point

1. `specs/README.md` for the spec map and source-of-truth rules.
2. `specs/global/agent-routing.md` to choose the relevant domain.
3. The matching `specs/domains/<domain>/spec.md`, `runbook.md`,
   `decisions.md`, and `contracts/VAL-*.md` files.

`README.md`, `PROCESS.md`, and `NOTES.md` are not acceptance sources. They may
explain onboarding, current state, or rationale, but the specs and contracts
define supported behavior and required evidence.

This repo is a reproducible three-VM lab for Debian 13 :
**Asterisk 22 LTS PBX**, an **OpenSIPS 3.6 LTS SBC** with rtpengine, and a
**monitoring VM** with Zabbix 7.0 LTS + PostgreSQL and Grafana.
Host softphone (baresip) talks to the SBC; the SBC relays signaling and
media to Asterisk. All VMs run on the same libvirt default NAT network.

Use these conventions when changing it:

- Keep secrets out of git. `.env` is ignored; `.env.example` contains names only.
- Treat `asterisk/*.tmpl` as the source of truth for files rendered into `/etc/asterisk`, and `sbc/*.tmpl` as the source of truth for files rendered into `/etc/opensips` and `/etc/rtpengine`. Never hand-edit the rendered files on either VM — re-running the matching `install.sh` will overwrite them.
- Treat `monitoring/*.tmpl` and `monitoring/*.sh` as the source of truth for the monitoring VM and zabbix-agent2 node setup. Never hand-edit `/etc/zabbix/*` or Grafana plugin state expecting it to survive; rerun the matching monitoring script.
- The local SIP client is baresip. Its `~/.baresip/accounts` domain points at the **SBC** IP, not Asterisk's (when the SBC layer is in use).
- SIP endpoints are provisioned per-extension from `asterisk/pjsip-endpoint.conf.tmpl`. The list lives in `.env` as `SIP_EXTENSIONS="1001 1002"`; each needs a matching `SIP_EXT_<num>_PASSWORD`. Rendered files land in `/etc/asterisk/pjsip.d/<ext>.conf` and are pruned on re-run when removed from `.env`. AORs include `support_path=yes` so PJSIP stores the SBC-inserted `Path:` header.
- The SBC config (`sbc/opensips.cfg.tmpl`) is templated with `${SBC_IP}` (the SBC's own IP — used in `socket=` and therefore in Via / Record-Route / Path headers) and `${ASTERISK_IP}` (the relay target). Both go in `.env`. Read them from `virsh net-dhcp-leases default` after the VMs boot — DHCP allocations are not fixed.
- The monitoring VM is `monitoring-deb13-cloudinit`; DHCP IP was `192.168.122.13`, but DHCP is not fixed. Read `MONITORING_IP` from `virsh net-dhcp-leases default` after boot and place it in each monitored node's `.env`. The monitoring VM also needs `ZABBIX_DB_PASSWORD` in its own `.env`.
- Monitored nodes use `zabbix-agent2` installed via `monitoring/setup-zabbix-agent.sh`. Use stable hostnames matching the libvirt domains unless there is a deliberate reason to override `ZABBIX_HOSTNAME`.
- The initial-INVITE branch in `sbc/opensips.cfg.tmpl` is direction-blind: it unconditionally sets `$du` to the Asterisk address for every INVITE that misses `loose_route()`. This breaks the outbound B2BUA leg (Asterisk-generated INVITE toward a registered softphone) because the SBC loops it back to Asterisk instead of relaying to the R-URI's softphone address. If you exercise `Dial(PJSIP/<ext>)`, gate the `$du` assignment on `$si != "${ASTERISK_IP}"` (or an equivalent direction check) so INVITEs coming from Asterisk fall through to their R-URI. The Path/Route return handling by `loose_route()` alone does not save you here; the `received=<uri>` parameter on the Path can trip its self-recognition and the request lands in the initial-INVITE branch.
- Extension `600` is the loopback test target (record + playback + echo). Pattern `_10XX` handles direct dial between softphones by starting `MixMonitor` and then calling `Dial(PJSIP/${EXTEN},20)` — the two-legged B2BUA path. Note: a single baresip process holding both `1001` and `1002` cannot self-call across accounts (baresip terminates the outgoing leg when it detects the incoming leg belongs to itself); use a second softphone or a second baresip instance on a different SIP port to exercise real end-to-end media between two extensions.
- Recordings land under `/var/spool/asterisk/monitor/`.
- Keep `install.sh` and `sbc/install.sh` idempotent so a fresh clone can reproduce either VM.
- Local-Whisper transcription runs as the `transcriber` systemd unit (`asterisk/transcriber.service`). It watches `/var/spool/asterisk/monitor/` and writes `<recording>.txt` next to each `<recording>.wav`. Install via `scripts/setup-transcriber.sh`; everything lives under `/opt/transcriber/` (`venv/` + `watcher.py` + `transcribe.py`). Model and forced language are read from env vars `WHISPER_MODEL` (default `base`) and `WHISPER_LANGUAGE` (default `tr`) at `watcher.py` startup. `base` on 8 kHz telephony audio hallucinates freely — for anything you plan to read, override to at least `small` via a `transcriber.service.d/*.conf` drop-in, and set `WHISPER_LANGUAGE` to match the actual speech (leave unset to auto-detect).
- Live observation: SBC daemons route to syslog (`local0` opensips, `local1` rtpengine). `tail -f /var/log/syslog` on the SBC VM shows both side-by-side; `journalctl -u opensips -u rtpengine-daemon` is the systemd-side equivalent. SIP capture: `sudo sngrep -d any port 5060` on any of host / SBC / Asterisk VM.
- Project-level skills live under `.claude/skills/`. Read the matching skill before adding a SIP endpoint, deploying to a VM, debugging registration, or rotating passwords — they encode the canonical sequence and the gotchas already learned.
