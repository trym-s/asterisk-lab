# Process Notes

This file is the short operational history for the Asterisk lab. It is kept in sync with the current repo layout and install flow; stale phase status notes were removed.

## Current Target

Fresh Debian 13 / Ubuntu 26.04 VM, with SSH/sudo and internet access already available.

From a clone of this repo:

```bash
cp .env.example .env
$EDITOR .env
make install
make verify
```

`make install` runs:

1. `install.sh`
2. `scripts/setup-transcriber.sh`

The scripts are intended to be idempotent: re-running should skip the Asterisk build when the pinned version is already installed, re-render config from templates, restart services, and refresh the transcriber files.

## Current Paths

Repo paths:

```text
install.sh
Makefile
README.md
AGENTS.md
.env.example
asterisk/
  asterisk.service
  transcriber.service
  pjsip.conf.tmpl
  pjsip-endpoint.conf.tmpl
  extensions.conf.tmpl
  rtp.conf
scripts/
  setup-transcriber.sh
  verify.sh
  watcher.py
  transcribe.py
  requirements.txt
infra/libvirt/
  setup-host.sh
  asterisk-deb13.xml
.claude/skills/
  adding-sip-endpoint/
  debugging-sip-registration/
  deploying-to-vm/
  rotating-passwords/
```

Target VM paths produced by install:

```text
/usr/local/src/asterisk/                 Asterisk source checkout
/usr/sbin/asterisk                       Installed Asterisk binary
/etc/systemd/system/asterisk.service     Asterisk service unit
/etc/asterisk/pjsip.conf                 Rendered from asterisk/pjsip.conf.tmpl
/etc/asterisk/pjsip.d/<ext>.conf         Rendered from asterisk/pjsip-endpoint.conf.tmpl
/etc/asterisk/extensions.conf            Rendered from asterisk/extensions.conf.tmpl
/etc/asterisk/rtp.conf                   Installed from asterisk/rtp.conf
/var/spool/asterisk/monitor/             WAV recordings and TXT transcripts
/opt/transcriber/                        watcher.py, transcribe.py, venv
/var/lib/asterisk/.cache/whisper/         Local Whisper model cache
/etc/systemd/system/transcriber.service  Transcriber watcher service unit
```

Secrets:

```text
.env                         Local/target secret file, ignored by git
.env.example                 Committed template, names only
SIP_EXT_<num>_PASSWORD        One password per SIP extension
```

## Implementation Decisions

### Asterisk Version

Asterisk is pinned to `22.9.0` via `ASTERISK_VERSION` in `.env.example`. `install.sh` checks `/usr/sbin/asterisk -V`; if the installed version already matches, it skips rebuilding.

The source checkout lives at `/usr/local/src/asterisk`, not under the user home directory.

### Config Source Of Truth

The repo templates under `asterisk/*.tmpl` are the source of truth. Do not hand-edit rendered files under `/etc/asterisk`; `install.sh` overwrites them on every run.

Endpoint config is generated per extension:

```text
SIP_EXTENSIONS="1001 1002"
SIP_EXT_1001_PASSWORD=...
SIP_EXT_1002_PASSWORD=...
```

The output is:

```text
/etc/asterisk/pjsip.d/1001.conf
/etc/asterisk/pjsip.d/1002.conf
```

If an extension is removed from `SIP_EXTENSIONS`, the matching orphan file in `/etc/asterisk/pjsip.d/` is pruned on the next `install.sh` run.

### Softphone

MicroSIP is Windows-only. This repo documents and tests with `baresip` on Linux. The SIP exchange is the same on the Asterisk side:

```text
REGISTER -> 401 Unauthorized
REGISTER with digest -> 200 OK
INVITE -> 100 Trying -> 180 Ringing -> 200 OK -> ACK
BYE -> 200 OK
```

### Dialplan And Recording

Extension `600` is the loopback test target. It answers, starts `MixMonitor`, plays a prompt, then enters `Echo()` so microphone audio is present in the recording.

Direct softphone dialing is covered by `_10XX`, also with `MixMonitor`.

Recordings are written as WAV files:

```text
/var/spool/asterisk/monitor/<timestamp>-<caller>-<extension>-<uniqueid>.wav
```

### Transcription

`scripts/setup-transcriber.sh` installs a local Whisper watcher as `transcriber.service`.

Runtime layout:

```text
/opt/transcriber/venv/
/opt/transcriber/watcher.py
/opt/transcriber/transcribe.py
/var/lib/asterisk/.cache/whisper/
```

The watcher polls `/var/spool/asterisk/monitor/` and writes:

```text
<recording>.txt
```

next to each `.wav`.

## Verification Checklist

After `make install` on a fresh VM:

```bash
make verify
systemctl status asterisk --no-pager
journalctl -u asterisk -n 100 --no-pager
sudo asterisk -rvvv
```

Inside the Asterisk CLI:

```text
pjsip show endpoints
pjsip show contacts
dialplan show from-softphones
```

From another VM shell, watch SIP signaling:

```bash
sudo sngrep -d any port 5060
```

Expected after softphone registration and a call to `600`:

```text
REGISTER
401 Unauthorized
REGISTER
200 OK
INVITE
100 Trying
180 Ringing
200 OK
ACK
BYE
200 OK
```

Recording/transcript checks:

```bash
ls -l /var/spool/asterisk/monitor/*.wav
ls -l /var/spool/asterisk/monitor/*.txt
journalctl -u transcriber -n 100 --no-pager
```

## Known Issues And Fixes

### `virsh` Defaults To `qemu:///session`

Symptom: domain definition succeeds, but start fails because the `default` pool or network is missing.

Cause: plain `virsh` may connect to `qemu:///session`, while the libvirt default pool/network usually live in `qemu:///system`.

Fix:

```bash
export LIBVIRT_DEFAULT_URI=qemu:///system
virsh define infra/libvirt/asterisk-deb13.xml
virsh start asterisk-deb13
```

### Small VM OOM During Asterisk Build

Symptom: compile fails or `cc1` is killed.

Cause: `install.sh` defaults to `MAKE_JOBS=$(nproc)`.

Fix: use a VM with at least 4 GB RAM, or limit build parallelism before running install:

```bash
sudo MAKE_JOBS=2 ./install.sh
sudo ./scripts/setup-transcriber.sh
```

### `.env` Missing On Target

Symptom: `install.sh` exits with `SIP_EXTENSIONS not set`.

Cause: `.env` is intentionally ignored by git and excluded from deploy.

Fix:

```bash
cp .env.example .env
$EDITOR .env
```

### Repeated `401 Unauthorized`

Symptom: `sngrep` shows `REGISTER -> 401 -> REGISTER -> 401` loop.

Cause: softphone password does not match `SIP_EXT_<num>_PASSWORD`.

Fix: update `.env`, re-run `sudo ./install.sh`, then update/restart the softphone.

### `verify.sh` And Short Pipelines

Under `set -o pipefail`, commands like `pip show ... | head -1` can fail with `SIGPIPE` even when `pip show` succeeded. `scripts/verify.sh` avoids that pattern; keep future checks similarly direct.

## Agent Context

`AGENTS.md` captures the repo-wide operating rules:

- Keep secrets out of git.
- Treat `asterisk/*.tmpl` as source of truth.
- Use baresip as the local Linux softphone.
- Manage endpoints through `.env`.
- Keep `install.sh` idempotent.
- Use `/var/spool/asterisk/monitor/` for recordings and transcripts.

Project skills under `.claude/skills/` document common operations:

- add/remove SIP endpoint
- deploy to VM
- debug SIP registration
- rotate SIP passwords
