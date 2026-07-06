# Asterisk Domain Spec

The Asterisk VM provides the PBX, PJSIP endpoints, dialplan, call recordings,
and local Whisper transcription.

## Supported Behavior

- `make install` runs `install.sh` and `scripts/setup-transcriber.sh`.
- `install.sh` builds the pinned Asterisk version when needed, renders
  templates, starts `asterisk.service`, and prunes orphan endpoint configs.
- Endpoints are generated from `SIP_EXTENSIONS` and matching
  `SIP_EXT_<num>_PASSWORD` values in the target `.env`.
- Extension `600` answers, records a WAV, plays a prompt, and enters `Echo()`.
- Pattern `_10XX` records and bridges softphone-to-softphone calls through
  `Dial(PJSIP/${EXTEN},20)`.
- `transcriber.service` watches the monitor directory and writes `.txt`
  transcripts next to stable `.wav` files.
- Extension `1098` is reserved for Pipecat AudioSocket when that lane is
  deployed.
- Extension `1099` is reserved for LiveKit SIP gateway when that lane is
  deployed.
- Voicebot benchmark validation may require Asterisk-side recording evidence
  that distinguishes caller audio received by the VM from bot audio sent back
  toward the caller. Any such recording behavior is rendered from
  `asterisk/extensions.conf.tmpl`, not hand-edited on the VM.

## Source Files

- `install.sh`
- `asterisk/*.tmpl`
- `asterisk/rtp.conf`
- `asterisk/*.service`
- `scripts/setup-transcriber.sh`
- `scripts/watcher.py`
- `scripts/transcribe.py`
- `scripts/verify.sh`

## Current Runtime Outputs

- `/etc/asterisk/pjsip.conf`
- `/etc/asterisk/pjsip.d/<ext>.conf`
- `/etc/asterisk/extensions.conf`
- `/var/spool/asterisk/monitor/*.wav`
- `/var/spool/asterisk/monitor/*.txt`
- `/opt/transcriber/`

Rendered files are not source of truth.
