# Agent Notes

This repo is a reproducible two-VM lab for Debian 13 / Ubuntu 26.04:
**Asterisk 22 LTS PBX** and an **OpenSIPS 3.6 LTS SBC** with rtpengine.
Host softphone (baresip) talks to the SBC; the SBC relays signaling and
media to Asterisk. Both VMs run on the same libvirt default NAT network.

Use these conventions when changing it:

- Keep secrets out of git. `.env` is ignored; `.env.example` contains names only.
- Treat `asterisk/*.tmpl` as the source of truth for files rendered into `/etc/asterisk`, and `sbc/*.tmpl` as the source of truth for files rendered into `/etc/opensips` and `/etc/rtpengine`. Never hand-edit the rendered files on either VM — re-running the matching `install.sh` will overwrite them.
- The local SIP client is baresip. Its `~/.baresip/accounts` domain points at the **SBC** IP, not Asterisk's (when the SBC layer is in use).
- SIP endpoints are provisioned per-extension from `asterisk/pjsip-endpoint.conf.tmpl`. The list lives in `.env` as `SIP_EXTENSIONS="1001 1002"`; each needs a matching `SIP_EXT_<num>_PASSWORD`. Rendered files land in `/etc/asterisk/pjsip.d/<ext>.conf` and are pruned on re-run when removed from `.env`. AORs include `support_path=yes` so PJSIP stores the SBC-inserted `Path:` header.
- The SBC config (`sbc/opensips.cfg.tmpl`) is templated with `${SBC_IP}` (the SBC's own IP — used in `socket=` and therefore in Via / Record-Route / Path headers) and `${ASTERISK_IP}` (the relay target). Both go in `.env`. Read them from `virsh net-dhcp-leases default` after the VMs boot — DHCP allocations are not fixed.
- Extension `600` is the loopback test target (record + playback + echo). Pattern `_10XX` handles direct dial between softphones (records + echo).
- Recordings land under `/var/spool/asterisk/monitor/`.
- Keep `install.sh` and `sbc/install.sh` idempotent so a fresh clone can reproduce either VM.
- Local-Whisper transcription runs as the `transcriber` systemd unit (`asterisk/transcriber.service`). It watches `/var/spool/asterisk/monitor/` and writes `<recording>.txt` next to each `<recording>.wav`. Install via `scripts/setup-transcriber.sh`; everything lives under `/opt/transcriber/` (`venv/` + `watcher.py` + `transcribe.py`).
- Live observation: SBC daemons route to syslog (`local0` opensips, `local1` rtpengine). `tail -f /var/log/syslog` on the SBC VM shows both side-by-side; `journalctl -u opensips -u rtpengine-daemon` is the systemd-side equivalent. SIP capture: `sudo sngrep -d any port 5060` on any of host / SBC / Asterisk VM.
- Project-level skills live under `.claude/skills/`. Read the matching skill before adding a SIP endpoint, deploying to a VM, debugging registration, or rotating passwords — they encode the canonical sequence and the gotchas already learned.
