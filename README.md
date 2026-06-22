# Asterisk onboarding

End-to-end Asterisk 22 LTS setup on Debian/Ubuntu: source build, PJSIP softphone registration with baresip, sngrep capture, call recording, transcription.

The deliverable is a repo you can clone onto a fresh Debian 13 / Ubuntu 26.04 box and bring up to a working Asterisk PBX with one command.

---

## Quick start (on the target — a fresh Debian 13 / Ubuntu 26.04 VM)

```bash
git clone <this-repo>
cd asterisk-lab
cp .env.example .env
$EDITOR .env                   # fill in SIP_EXTENSIONS + SIP_EXT_<n>_PASSWORD per entry
make install                   # asterisk + transcriber; ~10–15 min on first run
make verify                    # smoke checks; should print "N/N OK"
```

`make install` runs `install.sh` (builds Asterisk from source, renders configs, enables `asterisk.service`) and then `scripts/setup-transcriber.sh` (creates `/opt/transcriber/venv` from pinned `scripts/requirements.txt`, pre-downloads the Whisper `base` model, enables `transcriber.service`). Both scripts are idempotent — re-running on a configured box detects existing pieces and skips.

End state: each endpoint listed in `SIP_EXTENSIONS` (e.g. `1001`, `1002`) accepts REGISTER from baresip with its matching `SIP_EXT_<n>_PASSWORD`; extension `600` answers and records to `/var/spool/asterisk/monitor/`; the watcher transcribes each new `.wav` to a `.txt` next to it. Adding another endpoint later is two lines in `.env` and a re-run of `make install`.

---

## Host-side: running the VM under libvirt (optional)

If you want to run the target VM under libvirt, there's a one-time host setup script at `infra/libvirt/setup-host.sh`. You can also skip this entirely and use any other VM/cloud provider  the install script doesn't care.

### Host dependencies

The host bootstrap script does **not** install packages. Install these on the host first using your distro's package manager:

| Tool / capability | Arch                  | Debian / Ubuntu                                | Fedora / RHEL                    |
|-------------------|-----------------------|------------------------------------------------|----------------------------------|
| `virsh`           | `libvirt`             | `libvirt-clients` + `libvirt-daemon-system`    | `libvirt-client` + `libvirt-daemon` |
| QEMU/KVM          | `qemu-base`           | `qemu-system-x86`                              | `qemu-kvm`                       |
| `dnsmasq`         | `dnsmasq`             | `dnsmasq-base` (pulled in by libvirt)          | bundled with `libvirt-daemon`    |
| NAT helpers       | `iptables-nft`        | (default)                                      | (default)                        |
| `virt-install`    | `virt-install`        | `virtinst`                                     | `virt-install`                   |

In addition, the host kernel must have the `sch_htb` traffic-control module available (`/lib/modules/$(uname -r)/kernel/net/sched/sch_htb.ko*`). Standard kernels ship it; the bootstrap script loads it.

### Steps

```bash
# 1. Install the host dependencies above with your package manager.

# 2. Run the libvirt bootstrap. Loads sch_htb, enables libvirtd, starts
#    the default NAT network, creates the default storage pool.
./infra/libvirt/setup-host.sh

# 3. Place a Debian 13 qcow2 in the default pool (qcow2 is the standard
#    QEMU/libvirt disk image; grab one from https://cloud.debian.org/images/
#    or install from an ISO into a fresh qcow2).
sudo cp /path/to/debian13.qcow2 /var/lib/libvirt/images/asterisk-deb13.qcow2

# 4. Define and boot the VM.
export LIBVIRT_DEFAULT_URI=qemu:///system    # put this in your shell rc too
virsh define infra/libvirt/asterisk-deb13.xml
virsh start  asterisk-deb13
virsh net-dhcp-leases default                # → VM IP, e.g. 192.168.122.20

# 5. SSH in and follow the Quick start above.
ssh deb@192.168.122.20
```

---

## Repository layout

```
Makefile                 install / verify / deploy / logs / clean (`make help`)
install.sh               builds Asterisk + renders configs on the target VM
asterisk/
  pjsip.conf.tmpl              transport + #include pjsip.d/*.conf
  pjsip-endpoint.conf.tmpl     rendered once per SIP_EXTENSIONS entry → pjsip.d/<ext>.conf
  extensions.conf.tmpl         answers extension 600 and records WAV calls
  rtp.conf
  asterisk.service             systemd unit for asterisk
  transcriber.service          systemd unit for the watcher (hardened)
scripts/
  transcribe.py                local-Whisper one-shot transcriber
  watcher.py                   polls monitor dir, transcribes new WAVs in place
  setup-transcriber.sh         installs venv + transcriber systemd unit
  requirements.txt             pinned openai-whisper + torch
  verify.sh                    smoke checks (asterisk, dialplan, transcriber)
infra/libvirt/           optional libvirt convenience
  asterisk-deb13.xml           domain XML using default pool + default network
  setup-host.sh                host-side libvirt bootstrap
.github/workflows/
  lint.yml                     shellcheck + ruff on push/PR
PROCESS.md               running log of decisions, errors, and fixes
.env.example             secrets template (copy to .env, fill in, never commit)
```

---

## Verification after install

```bash
make verify                                     # 10 checks; exits non-zero on first failure
```

`verify.sh` covers `asterisk.service` active, version, each PJSIP endpoint listed in `/etc/asterisk/pjsip.d/` present (discovered at runtime — no hardcoded list), dialplan `600` loaded, `/var/spool/asterisk/monitor` writable by `asterisk`, `transcriber.service` active, venv python runnable, `openai-whisper` installed, base model cached, `watcher.py` present.

For a manual look:

```bash
sudo asterisk -rx 'pjsip show endpoints'        # one entry per SIP_EXTENSIONS; Unavailable until softphone registers
sudo asterisk -rx 'pjsip show contacts'         # populated after baresip REGISTER
journalctl -u asterisk -u transcriber -f        # or: make logs (over SSH to $(VM))
```

When baresip registers with `username=<ext>`, `password=$SIP_EXT_<ext>_PASSWORD`, `domain=<VM IP>`, that endpoint shifts from `Unavailable` to `Not in use`.

## Asterisk CLI

Interactive CLI for live inspection — attach to the running daemon over its local socket:

```bash
sudo asterisk -rvvv     # -r = remote (attach), -vvv = verbosity level 3
```

Useful inside the CLI:

```text
core show channels
pjsip show endpoints
pjsip show contacts
dialplan show from-softphones
exit                    # detach (asterisk keeps running)
```

For non-interactive scripting use `sudo asterisk -rx '<command>'` (the form `verify.sh` uses).

## Softphone choice (microsip → baresip)

The brief asks for **microsip**, which is Windows-only. On Linux the equivalent SIP exchange — REGISTER → 401 Unauthorized → REGISTER (with digest) → 200 OK; INVITE → 100 Trying → 180 Ringing → 200 OK → ACK; BYE → 200 OK — is reproducible end-to-end with **baresip**. The Asterisk side is identical either way; this section uses baresip throughout.

## Baresip client

On the host, install baresip and add one account per extension in `SIP_EXTENSIONS` to `~/.baresip/accounts`:

```text
<sip:1001@192.168.122.20>;auth_pass=<SIP_EXT_1001_PASSWORD>;transport=udp;regint=3600;answermode=auto;audio_codecs=opus,PCMU,PCMA
<sip:1002@192.168.122.20>;auth_pass=<SIP_EXT_1002_PASSWORD>;transport=udp;regint=3600;answermode=auto;audio_codecs=opus,PCMU,PCMA
```

Start baresip:

```bash
baresip
```

Verify registration from the VM:

```bash
sudo asterisk -rx 'pjsip show endpoints'
sudo asterisk -rx 'pjsip show contacts'
```

Observe SIP signaling in another VM shell:

```bash
sudo sngrep -d any port 5060
```

From baresip, dial the Asterisk test extension:

```text
/dial sip:600@192.168.122.20
```

Asterisk answers extension `600`, runs `MixMonitor`, and writes WAV files here:

```text
/var/spool/asterisk/monitor/
```

## SIP signaling reference

With `sudo sngrep -d any port 5060` running on the VM, a baresip REGISTER followed by `/dial sip:600@<VM IP>` produces the following message flow (each line is one SIP message visible in sngrep):

```text
REGISTER (no auth)              → 401 Unauthorized
REGISTER (with digest response) → 200 OK
INVITE   (sip:600@<VM IP>)      → 100 Trying
                                → 180 Ringing
                                → 200 OK
ACK
   ...two-way RTP audio on UDP 10000–10200...
BYE                             → 200 OK
```

If REGISTER never reaches `200 OK`: check the digest password matches `.env`, that UDP 5060 is reachable from host to VM, and `journalctl -u asterisk -n 50` for `WWW-Authenticate` mismatches.

## Transcripts

`transcriber.service` polls `/var/spool/asterisk/monitor/` and writes `<recording>.txt` next to each `<recording>.wav`. Defaults: Whisper `base`, Turkish, 2 s poll. Override in the unit's `[Service]` block:

```ini
Environment=WHISPER_MODEL=small
Environment=WHISPER_LANGUAGE=en
Environment=POLL_INTERVAL=5
```

One-shot transcription from the shell (no service):

```bash
sudo -u asterisk /opt/transcriber/venv/bin/python /opt/transcriber/transcribe.py \
  /var/spool/asterisk/monitor/<recording>.wav
```

## Production notes

A few decisions in this repo are deliberate and worth flagging for a future maintainer:

**Pinned transcriber dependencies (`scripts/requirements.txt`).** `openai-whisper==20250625` and `torch==2.12.1` are pinned, not floated. Whisper bumps occasionally break torch ABI; an unpinned install means the box you provision tomorrow runs different code than the one that worked yesterday. Pin is top-level only; transitives still float. For full reproducibility upgrade to `pip-tools` or `uv lock` and freeze a `requirements.lock` from a clean venv.

**systemd hardening on `transcriber.service`.** Beyond `User=asterisk`, the unit sets `ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`, explicit `ReadWritePaths`, the `ProtectKernel*` group, `NoNewPrivileges`, `RestrictNamespaces`, and friends. `MemoryDenyWriteExecute=true` is **intentionally not set** — PyTorch / numba JIT writes executable pages at runtime and crashes with SIGSYS if it's enabled. `systemd-analyze security transcriber` rates the unit ~5.8 MEDIUM; further hardening (`SystemCallFilter=@system-service`, `CapabilityBoundingSet=`, `ProtectProc=invisible`) is feasible but needs runtime testing to avoid breaking numpy/torch.

**Small VM builds.** Asterisk's source build defaults to `MAKE_JOBS=$(nproc)`. On small VMs this can OOM-kill the compiler. Use at least 4 GB RAM, or run a constrained build:

```bash
sudo MAKE_JOBS=2 ./install.sh
sudo ./scripts/setup-transcriber.sh
```

**`verify.sh` and `pipefail`.** Avoid piping `pip show ...` into `head -1` under `set -o pipefail` — `head` closes the pipe early, `pip` gets `SIGPIPE` and exits 141, and the check reports `FAIL` even though pip succeeded. Same trap with any short-circuiting downstream (`head`, `grep -q`, `awk 'NR==1'`). The current `verify.sh` avoids the pattern; preserve that on extension.

**`make deploy` excludes `.env` on purpose.** Secrets stay placed manually on the target (`scp .env vm:~/asterisk-lab/.env`, or production-grade `systemd-creds`/vault). A pipeline that rsyncs a real `.env` into a VM is a leak surface — any audit would flag it.

## Agent context

This repo includes `AGENTS.md` so future agent runs keep the same lab assumptions: templates under `asterisk/*.tmpl` are the source of truth, secrets stay in `.env`, the Linux softphone is baresip, endpoints live in `SIP_EXTENSIONS`, and extension `600` records WAV files under `/var/spool/asterisk/monitor/`.

Project-level skills under `.claude/skills/` document the most common ops flows — adding/removing a SIP endpoint, deploying to the lab VM, debugging registration failures, rotating passwords. Read the matching skill before acting on those tasks.
