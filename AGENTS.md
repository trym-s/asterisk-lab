# Agent Notes

This repo is a reproducible Asterisk 22 LTS lab for Debian 13 / Ubuntu 26.04.

Use these conventions when changing it:

- Keep secrets out of git. `.env` is ignored; `.env.example` contains names only.
- Treat `asterisk/*.tmpl` as the source of truth for files rendered into `/etc/asterisk`. Never hand-edit `/etc/asterisk/*.conf` on the VM — re-running `install.sh` will overwrite it.
- The local SIP client is baresip.
- SIP endpoints are provisioned per-extension from `asterisk/pjsip-endpoint.conf.tmpl`. The list lives in `.env` as `SIP_EXTENSIONS="1001 1002"`; each needs a matching `SIP_EXT_<num>_PASSWORD`. Rendered files land in `/etc/asterisk/pjsip.d/<ext>.conf` and are pruned on re-run when removed from `.env`.
- Extension `600` is the loopback test target (record + playback + echo). Pattern `_10XX` handles direct dial between softphones (records + echo).
- Recordings land under `/var/spool/asterisk/monitor/`.
- Keep `install.sh` idempotent so a fresh clone can reproduce the lab.
- Local-Whisper transcription runs as the `transcriber` systemd unit (`asterisk/transcriber.service`). It watches `/var/spool/asterisk/monitor/` and writes `<recording>.txt` next to each `<recording>.wav`. Install via `scripts/setup-transcriber.sh`; everything lives under `/opt/transcriber/` (`venv/` + `watcher.py` + `transcribe.py`).
- Project-level skills live under `.claude/skills/`. Read the matching skill before adding a SIP endpoint, deploying to the VM, debugging registration, or rotating passwords — they encode the canonical sequence and the gotchas already learned.
