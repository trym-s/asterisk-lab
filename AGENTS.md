# Agent Notes

This repo is a reproducible Asterisk 22 LTS lab for Debian 13 / Ubuntu 26.04.

Use these conventions when changing it:

- Keep secrets out of git. `.env` is ignored; `.env.example` contains names only.
- Treat `asterisk/*.tmpl` as the source of truth for files rendered into `/etc/asterisk`.
- The local SIP client  is baresip
- Endpoint `1001` and `1002` is the softphone user.
- Extension `600` is the local test call target and records WAV files under `/var/spool/asterisk/monitor`.
- Keep `install.sh` idempotent so a fresh clone can reproduce the lab.
- Local-Whisper transcription runs as the `transcriber` systemd unit (`asterisk/transcriber.service`). It watches `/var/spool/asterisk/monitor/` and writes `<recording>.txt` next to each `<recording>.wav`. Install via `scripts/setup-transcriber.sh`; everything lives under `/opt/transcriber/` (`venv/` + `watcher.py` + `transcribe.py`).
