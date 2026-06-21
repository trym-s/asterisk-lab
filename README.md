# Asterisk onboarding

End-to-end Asterisk 22 LTS setup on Debian/Ubuntu: source build, PJSIP softphone registration with baresip, sngrep capture, call recording, transcription.

The deliverable is a repo you can clone onto a fresh Debian 13 / Ubuntu 26.04 box and bring up to a working Asterisk PBX with one command.

---

## Quick start (on the target — a fresh Debian 13 / Ubuntu 26.04 VM)

```bash
git clone <this-repo>
cd asterisk-lab
cp .env.example .env
$EDITOR .env                   # fill in SIP_EXT_1001_PASSWORD
sudo ./install.sh              # ~10–15 min on first run; asterisk build is slow
```

End state: `asterisk.service` active, PJSIP endpoint `1001` ready to accept REGISTER from baresip using the password from `.env`, and extension `600` ready to answer and record test calls.

The install script is idempotent — re-running on a configured box is fast (existing pieces are detected and skipped).

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
asterisk/                asterisk artefacts copied into the target box
  pjsip.conf.tmpl              substitutes ${SIP_EXT_1001_PASSWORD}
  extensions.conf.tmpl         answers extension 600 and records WAV calls
  rtp.conf
  asterisk.service             systemd unit
infra/libvirt/           optional libvirt convenience
  asterisk-deb13.xml           domain XML using default pool + default network
  setup-host.sh                host-side libvirt bootstrap
scripts/
  transcribe.py                local-Whisper one-shot transcriber (no API key)
  watcher.py                   polls monitor dir, transcribes new WAVs in place
  setup-transcriber.sh         installs venv + transcriber systemd unit on the box
install.sh               top-level: runs end-to-end inside the target VM
PROCESS.md               running log of decisions, errors, and fixes
.env.example             secrets template (copy to .env, fill in, never commit)
```

---

## Verification after install

```bash
systemctl status asterisk                       # active (running)
journalctl -u asterisk -n 100 --no-pager        # systemd/journal logs
sudo asterisk -rx 'core show version'           # Asterisk 22.x.y
sudo asterisk -rx 'pjsip show endpoints'        # endpoint 1001, state Unavailable until softphone registers
sudo asterisk -rx 'dialplan show from-softphones'
```

When baresip registers with `username=1001`, `password=$SIP_EXT_1001_PASSWORD`, `domain=<VM IP>`, the endpoint state shifts to `Not in use`.

## Baresip client

On the host, install baresip and add an account like this to `~/.baresip/accounts`:

```text
<sip:1001@192.168.122.20>;auth_pass=<SIP_EXT_1001_PASSWORD>;transport=udp;regint=3600;answermode=auto;audio_codecs=opus,PCMU,PCMA
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

## Transcribe a recording — local Whisper (auto)

Default path: a systemd watcher transcribes new recordings on the box, no API key needed.

```bash
sudo ./scripts/setup-transcriber.sh    # ~3–5 min: apt deps + venv + torch + whisper base model
systemctl status transcriber           # active (running)
journalctl -u transcriber -f           # live processing log
```

What the installer does:

- creates a venv at `/opt/transcriber/venv` with `openai-whisper` (CPU PyTorch)
- copies `watcher.py` + `transcribe.py` to `/opt/transcriber/`
- pre-downloads the `base` model into `/var/lib/asterisk/.cache/whisper/`
- installs `transcriber.service`, runs as user `asterisk`

The watcher polls `/var/spool/asterisk/monitor/` and writes `<recording>.txt` **next to** each `<recording>.wav`:

```text
/var/spool/asterisk/monitor/1782054757.2.wav
/var/spool/asterisk/monitor/1782054757.2.txt   ← transcript, same basename
```

Override defaults via the unit's environment (Turkish, base model, 2 s poll):

```ini
Environment=WHISPER_MODEL=small
Environment=WHISPER_LANGUAGE=en
Environment=POLL_INTERVAL=5
```

For a one-shot transcription from the shell (no service):

```bash
sudo -u asterisk /opt/transcriber/venv/bin/python /opt/transcriber/transcribe.py \
  /var/spool/asterisk/monitor/<recording>.wav
```


## Agent context

This repo includes `AGENTS.md` so future agent runs keep the same lab assumptions: templates under `asterisk/*.tmpl` are the source of truth, secrets stay in `.env`, the Linux softphone is baresip, endpoint `1001` is the SIP user, and extension `600` records WAV files under `/var/spool/asterisk/monitor/`.
