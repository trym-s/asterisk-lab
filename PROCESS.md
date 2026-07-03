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


### Opensips VM Setup

Mode: stateless SIP proxy + RTPengine for media relay. Both daemons on one VM.
Topology-hiding B2BUA is explicitly out of scope for this iteration and parked
for a follow-up spec.

#### Topology

```
                       libvirt default network (192.168.122.0/24)
                       ─────────────────────────────────────────
host (baresip)            asterisk-deb13-cloudinit       opensips-sbc-deb13-cloudinit
192.168.122.1             192.168.122.20                 192.168.122.30
   │                            │                              │
   │   SIP UDP 5060             │                              │
   ├───────────────────────────────────────────────────────────►
   │                                                           │
   │                              ◄────────────────────────────┤
   │                                  SIP UDP 5060             │
   │                                                           │
   │                            Asterisk PJSIP                 OpenSIPS 3.6 LTS
   │                            transport-udp 0.0.0.0:5060     listen=udp:0.0.0.0:5060
   │                            RTP 10000-10200                rtpengine ctl 127.0.0.1:22222
   │                                                           RTP relay 30000-31000
```

Signaling path: `host(122.1) ⇄ SBC(122.30) ⇄ Asterisk(122.20)` on UDP 5060.
SBC inserts `Via`, `Record-Route`, and `Path` (for REGISTER) so all subsequent
in-dialog traffic returns through it.

Media path: `host(122.1:rtp) ⇄ SBC(122.30:30000-31000) ⇄ Asterisk(122.20:10000-10200)`.
RTPengine relays UDP between the two halves.

#### VM Provisioning

Reuse the existing libvirt cloud-init flow:

```bash
DOMAIN=opensips-sbc-deb13-cloudinit \
SSH_PUBKEY_FILE=~/.ssh/id_ed25519.pub \
DISK_SIZE=20G \
MEMORY_GIB=2 \
VCPUS=2 \
./infra/libvirt/create-cloudinit-vm.sh
```

`create-cloudinit-vm.sh` is already parametrized — no script change. A
reference XML `infra/libvirt/opensips-sbc-deb13-cloudinit.xml` mirrors the
Asterisk one for manual `virsh define`. IP comes from libvirt DHCP; expected
range around `192.168.122.30`.

#### OpenSIPS: install and SIP role

OpenSIPS 3.6 LTS installs from the official APT repo (`apt.opensips.org`) on
Debian 13. The packaged systemd unit (`/lib/systemd/system/opensips.service`)
is used as-is.

Idempotent `sbc/install.sh`:

1. Add `apt.opensips.org` repo and signing key.
2. `apt install opensips opensips-rtpengine-module ngcp-rtpengine-daemon`.
3. Render `sbc/opensips.cfg.tmpl` to `/etc/opensips/opensips.cfg` via
   `envsubst` (same pattern as `asterisk/*.tmpl`).
4. Render `sbc/rtpengine.conf.tmpl` to `/etc/rtpengine/rtpengine.conf`.
5. `systemctl enable --now opensips ngcp-rtpengine-daemon`.

Modules loaded: `signaling`, `tm`, `sl`, `rr`, `path`, `proto_udp`,
`sipmsgops`, `textops`, `rtpengine`, `mi_fifo`.

Config skeleton (`/etc/opensips/opensips.cfg`):

```c
listen=udp:0.0.0.0:5060
log_facility=LOG_LOCAL0          # syslog → /var/log/syslog

modparam("rtpengine", "rtpengine_sock", "udp:127.0.0.1:22222")

route {
    if (!mf_process_maxfwd_header(10)) {
        sl_send_reply(483, "Too Many Hops");
        exit;
    }

    # in-dialog (ACK, BYE, re-INVITE) — Record-Route brings them back here
    if (has_totag()) {
        if (loose_route()) {
            if (is_method("BYE"))          { rtpengine_delete(); }
            else if (is_method("INVITE"))  { record_route(); rtpengine_offer(); }
            t_relay();
            exit;
        }
        sl_send_reply(404, "Not here");
        exit;
    }

    # initial REGISTER → add Path, relay to Asterisk
    if (is_method("REGISTER")) {
        add_path_received();
        $du = "sip:$ASTERISK_IP:5060";
        t_relay();
        exit;
    }

    # initial INVITE → Record-Route, SDP rewrite, relay to Asterisk
    if (is_method("INVITE")) {
        record_route();
        rtpengine_offer();
        $du = "sip:$ASTERISK_IP:5060";
        t_relay();
        exit;
    }

    t_relay();
}

onreply_route {
    if (status =~ "(180|183|200)") { rtpengine_answer(); }
}
```

`$ASTERISK_IP` rendered from `.env` at install time.

Behavior:

- **REGISTER**: `add_path_received()` inserts a `Path:` header so Asterisk's
  PJSIP stores the SBC as the route to the softphone. Contact is left
  unchanged — Asterisk sees the softphone IP as Contact but routes through
  Path. This is the stateless-proxy form of topology preservation; full
  topology hiding requires B2BUA (deferred).
- **INVITE**: `record_route()` pins in-dialog traffic to the SBC.
  `rtpengine_offer()` rewrites SDP `c=` to the SBC IP and `m=` to a port
  from RTPengine's range, before `t_relay()` to Asterisk.
- **Response (180/183/200)**: `onreply_route` calls `rtpengine_answer()` so
  RTPengine learns Asterisk's side of the media and can complete the bridge.
- **BYE**: `rtpengine_delete()` releases the port pair.

Repo files:

```text
sbc/
  opensips.cfg.tmpl        config template (envsubst)
  rtpengine.conf.tmpl      rtpengine daemon config template
  install.sh               APT repo + packages + render + enable
  verify.sh                smoke checks for opensips + rtpengine + sockets
```

#### RTPengine: install and config

RTPengine ships in Debian as `ngcp-rtpengine-daemon` (Sipwise upstream
packaging). Installed via the same `sbc/install.sh` apt step. systemd unit
provided by the package.

Config at `/etc/rtpengine/rtpengine.conf`:

```ini
[rtpengine]
interface  = 192.168.122.30
listen-ng  = 127.0.0.1:22222
port-min   = 30000
port-max   = 31000
log-level  = 6
log-facility = local1
```

- `interface` — IP where RTPengine binds for media; same as the SBC VM IP.
  RTP from both legs lands here.
- `listen-ng` — bencode ng control socket. OpenSIPS speaks to this from
  localhost; matches the `rtpengine_sock` modparam above.
- `port-min`/`port-max` — RTP/RTCP allocation range. Each session takes one
  pair on each leg (even RTP, odd RTCP), so 1000 ports comfortably covers
  the lab.
- `log-facility=local1` — separate syslog facility from OpenSIPS (`local0`)
  so `tail -f /var/log/syslog` shows both with clear prefixes.

Userspace forwarding only — no `xt_RTPENGINE` kernel module. Easier to
introspect with `tcpdump` and `strace`; kernel mode is a future optimization.

`sbc/verify.sh` checks:

- `systemctl is-active opensips`
- `systemctl is-active ngcp-rtpengine-daemon`
- `ss -ulnp | grep 22222` — ng control socket up
- `ss -ulnp | grep 192.168.122.30:5060` — OpenSIPS bound
- `opensips-cli -x mi version` — management interface responds

#### Asterisk-side changes

Minimal. The stateless proxy preserves the softphone's `Authorization:` header,
so PJSIP authenticates with the same credentials as before — no change to
`pjsip-endpoint.conf.tmpl` auth section.

Two adjustments needed:

- `asterisk/pjsip-endpoint.conf.tmpl`: add `support_path=yes` to the `[type=aor]`
  block so PJSIP stores the `Path:` header from REGISTER. Without it, Asterisk
  ignores Path and tries to reach the softphone directly via Contact IP —
  works on the same /24 in lab but defeats the SBC for any callback.
- The `from-softphones` context in `extensions.conf.tmpl` is unchanged — the
  SBC is transparent to dialplan; `${CALLERID(num)}` still resolves to the
  extension that originated the call.

What deliberately stays the same:

- PJSIP `identify_by` default (`username,auth_username`) — REGISTER auth digest
  still arrives from softphone, validated as before. No IP-based identification
  needed.
- `qualify_frequency=60` on AOR — OPTIONS from Asterisk to softphone now routes
  via Path → SBC → softphone. Requires the OpenSIPS route to handle
  `loose_route()` on out-of-dialog requests with `Route:` headers; the
  skeleton above is illustrative and the implementation will refine the
  `loose_route()` placement to cover this.

#### Host softphone (baresip) reconfig

`~/.baresip/accounts` entries now point at the SBC IP instead of Asterisk's:

```text
<sip:1001@192.168.122.30>;auth_pass=<SIP_EXT_1001_PASSWORD>;transport=udp;regint=3600;answermode=auto;audio_codecs=opus,PCMU,PCMA
<sip:1002@192.168.122.30>;auth_pass=<SIP_EXT_1002_PASSWORD>;transport=udp;regint=3600;answermode=auto;audio_codecs=opus,PCMU,PCMA
```

The auth password is unchanged — it lives in Asterisk; SBC is transparent.

#### Syslog routing and live observation

Both daemons route to syslog facilities so a single `tail -f /var/log/syslog`
on the SBC VM shows the full picture:

- OpenSIPS: `log_facility=LOG_LOCAL0`
- RTPengine: `log-facility=local1`

Debian's default `/etc/rsyslog.conf` routes `*.info` (and below) to
`/var/log/syslog`. No rsyslog config change required for the lab. Optional
later: split into `/var/log/opensips.log` and `/var/log/rtpengine.log` via
`/etc/rsyslog.d/opensips.conf`.

sngrep observation points during a call:

- Host (softphone side): `sudo sngrep -d any port 5060` — shows softphone↔SBC leg
- SBC VM: `sudo sngrep -d any port 5060` — shows both legs (entry + exit)
- Asterisk VM: `sudo sngrep -d any port 5060` — shows SBC↔Asterisk leg

Three windows side-by-side make the Via stacking and Record-Route insertion
visible end-to-end. For media verification: `sudo tcpdump -i any -n
udp portrange 30000-31000` on the SBC VM should show two-way RTP during a
call; zero traffic there with audio working = RTPengine not engaged (see
RTPengine failure signature in this section).

#### Repo layout deltas

New top-level directory parallel to `asterisk/`:

```text
sbc/
  opensips.cfg.tmpl
  rtpengine.conf.tmpl
  install.sh
  verify.sh
infra/libvirt/
  opensips-sbc-deb13-cloudinit.xml    reference XML for manual virsh define
```

`.env.example` gains:

```text
# SBC VM IP, learned from libvirt DHCP after first boot of opensips-sbc-deb13-cloudinit.
# Used by the Asterisk-side templates only if we ever IP-restrict; today
# Asterisk identifies endpoints by auth_username so this is informational.
SBC_IP=192.168.122.30

# Asterisk VM IP, used by sbc/opensips.cfg.tmpl render to set the relay target.
ASTERISK_IP=192.168.122.20
```

Makefile gains targets that mirror the Asterisk side but operate on the SBC VM:

```text
make install-sbc        ssh to SBC VM, run sbc/install.sh
make verify-sbc         ssh to SBC VM, run sbc/verify.sh
make logs-sbc           ssh to SBC VM, tail -f /var/log/syslog
make deploy-sbc         rsync repo to SBC VM (mirrors existing `make deploy`)
```

The existing `make install` / `make verify` / `make deploy` stay
Asterisk-only — no two-VM coupling in a single command.

#### End-to-end verification

After both VMs up and host baresip reconfigured:

```bash
# on host
baresip

# on SBC VM
make verify-sbc                                  # opensips + rtpengine active
sudo sngrep -d any port 5060                     # observe both legs
sudo tcpdump -i any -n udp portrange 30000-31000 # confirm RTP through SBC
tail -f /var/log/syslog                          # opensips + rtpengine live

# on Asterisk VM
make verify                                      # existing checks
sudo asterisk -rx 'pjsip show contacts'          # shows Path entry
sudo sngrep -d any port 5060                     # observe SBC↔Asterisk leg
```

Expected signaling at the SBC sngrep window during REGISTER + call to 600:

```text
REGISTER (host → SBC)
REGISTER (SBC → Asterisk, +Via +Path)
401 Unauthorized (Asterisk → SBC)
401 Unauthorized (SBC → host)
REGISTER w/ digest (host → SBC)
REGISTER w/ digest (SBC → Asterisk, +Via +Path)
200 OK (Asterisk → SBC)
200 OK (SBC → host)

INVITE sip:600 (host → SBC)
INVITE sip:600 (SBC → Asterisk, +Via +Record-Route, SDP c=/m= rewritten)
100 Trying
180 Ringing
200 OK (Asterisk → SBC, SDP rewritten on the way back)
200 OK (SBC → host)
ACK
... two-way RTP via 192.168.122.30:30000-31000 ...
BYE (and rtpengine_delete frees the ports)
200 OK
```

Recording and transcript paths on the Asterisk VM are unchanged — the SBC is
transparent to the dialplan, so `/var/spool/asterisk/monitor/*.wav` and the
matching `.txt` files appear exactly as before.

#### Execution log — Step 1: SBC VM created

Date: 2026-06-28.

Command run from the libvirt host (this machine), inside the repo root:

```bash
DOMAIN=opensips-sbc-deb13-cloudinit \
DISK_SIZE=20G \
MEMORY_GIB=2 \
VCPUS=2 \
./infra/libvirt/create-cloudinit-vm.sh
```

What the script did, step by step:

1. Confirmed libvirt pool `default` exists (`virsh pool-info default`).
2. Downloaded the Debian 13 (trixie) genericcloud image from
   `cloud.debian.org`, ~324 MB, into the host cache directory below.
3. Converted+resized to an independent 20 GB qcow2 for this VM
   (`qemu-img convert -O qcow2` then `qemu-img resize`).
4. Wrote `user-data` (cloud-config: hostname, user `deb`, sudo NOPASSWD,
   the host's `~/.ssh/id_ed25519.pub`) and `meta-data` (instance-id,
   local-hostname), then packed both into a NoCloud seed ISO with
   `cloud-localds`.
5. Uploaded the qcow2 and seed ISO into libvirt's `default` storage pool
   as named volumes (`virsh vol-create-as` + `virsh vol-upload`).
6. Rendered a libvirt domain XML (q35, host-passthrough CPU, 2 vCPU,
   2 GiB RAM, virtio NIC on `default` network) and wrote it to the cache.
7. `virsh define <xml>` then `virsh start`.

Host-side files produced (cache dir is shared with the Asterisk run, so the
base image was actually already there from before — only the per-VM artifacts
are new):

```text
/var/tmp/asterisk-lab-cloudinit/
  debian-13-genericcloud-amd64.qcow2                   base image, cached
  opensips-sbc-deb13-cloudinit.qcow2                   this VM's disk (pre-upload)
  opensips-sbc-deb13-cloudinit-seed.iso                this VM's cloud-init seed
  opensips-sbc-deb13-cloudinit.xml                     domain XML used for `virsh define`
  seed/
    user-data                                          cloud-config YAML
    meta-data                                          instance-id + hostname
```

libvirt-managed artifacts (live in the `default` pool, typically under
`/var/lib/libvirt/images/`):

```text
default pool volumes:
  opensips-sbc-deb13-cloudinit.qcow2                   VM disk
  opensips-sbc-deb13-cloudinit-seed.iso                cloud-init seed CDROM

libvirt domain (persistent):
  opensips-sbc-deb13-cloudinit                         running, virsh ID 1
```

Cloud-init `user-data` content (paraphrased — the literal heredoc lives in
`infra/libvirt/create-cloudinit-vm.sh`):

```yaml
#cloud-config
hostname: opensips-sbc-deb13-cloudinit
manage_etc_hosts: true
ssh_pwauth: false
disable_root: true
users:
  - default
  - name: deb
    groups: [sudo]
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    lock_passwd: true
    ssh_authorized_keys:
      - <host's id_ed25519.pub>
runcmd:
  - systemctl enable --now ssh || systemctl enable --now sshd || true
```

This is what gave us a passwordless-sudo `deb` user reachable over SSH on
first boot.

Result state:

- Domain `opensips-sbc-deb13-cloudinit` running.
- VM IP from libvirt DHCP: **`192.168.122.3`** — not the `192.168.122.30`
  the topology diagram earlier in this section shows. DHCP simply gave the
  next free address in the 122.0/24 range. The diagram value should be
  treated as illustrative; the operational SBC IP is whatever
  `virsh net-dhcp-leases default` reports.
- MAC `52:54:00:7a:0c:c0`, NIC inside the VM is `enp1s0`.
- OS: Debian 13.5 (trixie), kernel 6.12.94 from the cloud image.
- SSH verified: `ssh deb@192.168.122.3` returns `hostname` and
  `cat /etc/debian_version` without password prompt, using the host's
  `id_ed25519`.

Verification commands and their output shape:

```bash
virsh -c qemu:///system list
#  Id   Name                           State
# ----------------------------------------------
#  1    opensips-sbc-deb13-cloudinit   running

virsh -c qemu:///system net-dhcp-leases default | grep opensips-sbc
#  2026-06-28 22:25:43   52:54:00:7a:0c:c0   ipv4   192.168.122.3/24   opensips-sbc-deb13-cloudinit   ...

virsh -c qemu:///system domifaddr opensips-sbc-deb13-cloudinit --source lease
#  Name    MAC address         Protocol   Address
#  vnet0   52:54:00:7a:0c:c0   ipv4       192.168.122.3/24

ssh deb@192.168.122.3 'hostname; cat /etc/debian_version'
# opensips-sbc-deb13-cloudinit
# 13.5
```

Notes for follow-up steps:

- The `.env.example` line `SBC_IP=192.168.122.30` in this spec is illustrative.
  When we render configs we will set `SBC_IP=192.168.122.3` to match the
  actual lease. If the VM ever gets a different lease (after destroy/recreate
  or a different DHCP allocation), update `.env` and re-render.
- The cloud image cache (`/var/tmp/asterisk-lab-cloudinit/`) is shared across
  domains — re-running the script for a third VM would skip the download.
- Script's DHCP wait window (8 s) was not long enough for this run; the lease
  appeared a few seconds later. Not a script bug, just a timing race; a
  follow-up `virsh net-dhcp-leases default` resolves it.

#### Execution log — Step 2: OpenSIPS + rtpengine installed

Date: 2026-06-28. All commands run via `ssh deb@192.168.122.3 …` from the
libvirt host.

Pre-flight: Debian 13.5 trixie, `apt-cache` empty for `opensips*` before
adding upstream repo; `rtpengine-daemon` IS in Debian's own repo (under the
plain `rtpengine` name family, not `ngcp-rtpengine-daemon` as the spec
assumed).

Commands run, in order:

```bash
# 1) trust the OpenSIPS signing key (modern signed-by, not legacy apt-key)
sudo install -d -m 0755 /usr/share/keyrings
sudo curl -fsSL https://apt.opensips.org/opensips-org.gpg \
     -o /usr/share/keyrings/opensips-org.gpg

# 2) add the OpenSIPS 3.6 LTS repo for Debian 13 trixie
echo "deb [signed-by=/usr/share/keyrings/opensips-org.gpg] \
https://apt.opensips.org trixie 3.6-releases" \
   | sudo tee /etc/apt/sources.list.d/opensips.list

# 3) refresh package index
sudo apt-get update

# 4) install (the rtpengine OpenSIPS module is bundled in the core opensips
#    package — there is no separate opensips-rtpengine-module apt package)
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
     opensips rtpengine-daemon
```

Versions landed:

- OpenSIPS 3.6.7 (git `eaee48e28e`) from `apt.opensips.org`
- rtpengine 12.5.1.31-1 (Sipwise upstream, packaged by Debian)
- rtpengine-recording-daemon and rtpengine-perftest pulled in as recommends;
  harmless extras, not used in this lab.

Files installed:

```text
OpenSIPS:
  /usr/sbin/opensips                                main daemon binary (not in deb user's PATH)
  /etc/opensips/opensips.cfg                        default config (untouched so far)
  /etc/opensips/scenario_callcenter.xml             example scenario, unused
  /etc/default/opensips                             env file; gates startup with RUN_OPENSIPS
  /etc/init.d/opensips                              sysvinit script (systemd unit takes priority)
  /usr/lib/systemd/system/opensips.service          systemd unit
  /usr/lib/x86_64-linux-gnu/opensips/modules/*.so   all built-in modules
  /usr/lib/x86_64-linux-gnu/opensips/modules/rtpengine.so   the OpenSIPS↔rtpengine module

rtpengine:
  /usr/bin/rtpengine                                daemon binary
  /etc/rtpengine/rtpengine.conf                     default config (commented template + working defaults)
  /etc/default/rtpengine-daemon                     env file: CONFIG_FILE, MANAGE_IPTABLES=yes, SET_USER=rtpengine
  /usr/lib/systemd/system/rtpengine-daemon.service  systemd unit (also rtpengine.service alias)
```

Service state after install:

| Service           | enabled | active   | listening                  |
|-------------------|---------|----------|----------------------------|
| `opensips`        | yes     | inactive | nothing                    |
| `rtpengine-daemon`| yes     | active   | `127.0.0.1:2223` UDP (ng)  |

Two important nuances that diverge from the design doc above and must be
carried into the config templates we author next:

1. **`opensips` won't start until `/etc/default/opensips` is edited.** Debian
   convention: the env file ships with `RUN_OPENSIPS=no` so an unconfigured
   server doesn't auto-start. The systemd unit reads this env file. We will
   flip it to `yes` only after our `opensips.cfg.tmpl` is rendered and we
   trust the config.

2. **rtpengine's default ng port is `2223`, not `22222`.** The design
   section's `modparam("rtpengine", "rtpengine_sock", "udp:127.0.0.1:22222")`
   line was based on the upstream GitHub README, but Debian's packaged
   default config lists `listen-ng = localhost:2223`. Easiest path is to
   keep the packaged default and write the OpenSIPS modparam as
   `udp:127.0.0.1:2223`. PROCESS.md spec text in the OpenSIPS section above
   should be read with this correction.

Other observed defaults in `/etc/rtpengine/rtpengine.conf` worth carrying
forward:

- `interface = any` — rtpengine binds RTP on every interface. For the lab
  this is fine; in production we'd narrow to the SBC's egress IP.
- `port-min = 30000 / port-max = 40000` — matches the design's media range
  expectation (lab spec said `30000-31000`; the packaged default is wider
  but a strict superset, so leave as-is unless we have a reason to narrow).
- `table = 0` plus `MANAGE_IPTABLES=yes` — the daemon is *configured* for
  kernel-mode forwarding, but the `rtpengine-kernel-dkms` package was not
  installed, so it falls back to userspace silently. For the lab, userspace
  is what we want; no action needed.
- `listen-cli = localhost:2224` and `listen-http = localhost:2225` — CLI
  and HTTP MI sockets, useful later for live introspection.

Sanity outputs (verbatim shape):

```bash
opensips -V
# version: opensips 3.6.7 (x86_64/linux)
# flags: STATS: On, DISABLE_NAGLE, USE_MCAST, ...
# git revision: eaee48e28e

systemctl is-enabled opensips        # enabled
systemctl is-active  opensips        # inactive

systemctl is-enabled rtpengine-daemon  # enabled
systemctl is-active  rtpengine-daemon  # active

sudo ss -ulnp | grep -E "rtpengine|22|5060"
# UNCONN 0 0 127.0.0.1:2223 0.0.0.0:* users:(("rtpengine",pid=4382,fd=6))
# UNCONN 0 0     [::1]:2223    [::]:* users:(("rtpengine",pid=4382,fd=5))
```

No SIP port (5060) is bound yet — OpenSIPS isn't running, so nothing
listens for SIP. That's the next step.

#### Execution log — Step 3: minimal opensips.cfg + rtpengine clean-up

Date: 2026-06-28.

Goal: replace Debian's default "Residential" `opensips.cfg` (~265 lines,
local registrar) with a minimal stateless proxy that adds `Path:` on
REGISTER, `Record-Route:` + rtpengine SDP rewrite on INVITE, and relays
everything to Asterisk. Start the service and confirm it listens on
`0.0.0.0:5060/udp`.

Repo additions:

```text
sbc/
  opensips.cfg.tmpl    minimal SBC config; ${ASTERISK_IP} is the only
                       substitution variable. Authoritative source —
                       /etc/opensips/opensips.cfg on the VM is a render.
```

Render + deploy command (from the libvirt host, in the repo root):

```bash
ASTERISK_IP=192.168.122.20 envsubst '${ASTERISK_IP}' < sbc/opensips.cfg.tmpl \
  | ssh deb@192.168.122.3 'sudo tee /etc/opensips/opensips.cfg > /dev/null'
```

The whitelist `'${ASTERISK_IP}'` on `envsubst` is load-bearing. Without it
(`envsubst` with no args expands every `$WORD`), OpenSIPS's own pseudo-
variables get destroyed — `$du` (destination URI) becomes empty string,
config fails to parse. First render attempt hit this; second render with
whitelist passed.

Syntax check used:

```bash
sudo /usr/sbin/opensips -C -f /etc/opensips/opensips.cfg
# config file ok, exiting...
# Listening on udp: 0.0.0.0 [0.0.0.0]:5060
```

Two syntax fixes the parser caught on the way (carried into the template):

1. `mf_process_maxfwd_header("10")` → `mf_process_maxfwd_header(10)`. OpenSIPS
   3.x is strict: that param is declared as integer, a quoted string is a
   `bad command` error.
2. `sl_send_reply("483", "Too Many Hops")` → `sl_send_reply(483, "Too Many Hops")`.
   Same rule — first arg is integer.
3. `onreply_route { if (status =~ "(180|183|200)") ... }` →
   `if ($rs == 180 || $rs == 183 || $rs == 200)`. In 3.x reply status is the
   `$rs` pseudo-variable; the bare word `status` is not a valid token.

Service startup:

```bash
sudo sed -i 's/^RUN_OPENSIPS=no/RUN_OPENSIPS=yes/' /etc/default/opensips
sudo systemctl restart opensips
```

Debian's env file gates startup with `RUN_OPENSIPS=no`. The systemd unit
sources `/etc/default/opensips` and refuses to start until this is `yes`.
This is the official "don't auto-run an unconfigured server" hook.

Auxiliary install needed for the design's syslog routing to actually work:

```bash
sudo apt-get install -y rsyslog
```

Debian 13's minimal cloud image ships with **no rsyslog** — everything goes
to systemd-journald only, and `/var/log/syslog` does not exist. The spec's
"`tail -f /var/log/syslog` shows both daemons" flow needs rsyslog installed.
After installing rsyslog and restarting both daemons, syslog facilities
`LOG_LOCAL0` (opensips) and `local1` (rtpengine) land in `/var/log/syslog`
side-by-side as expected. Both also continue to appear in
`journalctl -u opensips` / `journalctl -u rtpengine-daemon`.

`opensips-cli` was NOT found in either Debian's repo or in the
`apt.opensips.org` 3.6-releases pocket for trixie. It is a separate Python
tool. For now we drive the MI from the FIFO directly:

```bash
ls -l /run/opensips/opensips_fifo
# prw-rw-rw- 1 opensips opensips ... /run/opensips/opensips_fifo
```

(0666 from the `mi_fifo` modparam in the config.) `opensips-cli` install
can be revisited when verification scripting needs it.

rtpengine clean-up (also done in this step because the kernel-mode noise
clutters the syslog stream we just enabled):

```bash
sudo sed -i -E 's/^table = 0$/table = -1/; \
                 s/^# log-facility = daemon$/log-facility = local1/' \
            /etc/rtpengine/rtpengine.conf
sudo sed -i 's/^MANAGE_IPTABLES=yes/MANAGE_IPTABLES=no/' \
            /etc/default/rtpengine-daemon
sudo systemctl restart rtpengine-daemon
```

`table = -1` forces userspace forwarding only (the `xt_RTPENGINE` kernel
module was never installed, so kernel mode was silently failing with
"FAILED TO CREATE KERNEL TABLE 0" + "FAILED TO CREATE NFTABLES CHAINS"
ERROR lines in syslog). `MANAGE_IPTABLES=no` stops the daemon from even
attempting nftables setup. `log-facility = local1` separates rtpengine
syslog lines from opensips's `local0`, so `tail -f /var/log/syslog | grep
rtpengine` is clean.

Final state after Step 3:

| Service           | active | listens                                       |
|-------------------|--------|-----------------------------------------------|
| `opensips`        | yes    | `0.0.0.0:5060/udp` (9 worker forks total)     |
| `rtpengine-daemon`| yes    | `127.0.0.1:2223/udp` ng (IPv4 + IPv6 loop)    |

Clean syslog excerpt (rtpengine startup with userspace mode forced):

```text
opensips-sbc … rtpengine[…]: INFO: [crypto] Generating new DTLS certificate
opensips-sbc … rtpengine[…]: INFO: [core] Startup complete, version 12.5.1.31-1
opensips-sbc … rtpengine[…]: INFO: [http] Websocket listener thread running
opensips-sbc … systemd[1]: Started rtpengine-daemon.service - RTP/media Proxy Daemon.
```

No ERR lines, no fallback warnings.

Modules confirmed loaded by opensips (from syslog at restart):
`signaling`, `sl`, `tm`, `rr`, `maxfwd`, `sipmsgops`, `textops`, `path`,
`rtpengine`, `mi_fifo`, `proto_udp`.

What did NOT happen yet:

- Asterisk VM is still shut off; relay target `192.168.122.20:5060` is
  unreachable. Any REGISTER/INVITE arriving at the SBC right now will
  produce a 408 timeout downstream from `t_relay()`.
- baresip on the host still points at the (offline) Asterisk VM IP. No
  SIP traffic is flowing yet.
- No actual call has crossed the SBC.

Next step is to start the Asterisk VM, refresh `ASTERISK_IP` if DHCP
gives a different lease, then point baresip at the SBC and watch the
first end-to-end REGISTER + call cross all three legs.

#### Execution log — Step 4 (partial): Asterisk VM restarted, SBC re-rendered

Date: 2026-06-28.

Asterisk VM brought up:

```bash
virsh -c qemu:///system start asterisk-deb13-cloudinit
virsh -c qemu:///system net-dhcp-leases default | grep asterisk
# 2026-06-28 23:08:39  52:54:00:81:b0:da  ipv4  192.168.122.247/24  asterisk-deb13-cloudinit
```

**Surprise — Asterisk did NOT get `192.168.122.20` back.** libvirt's dnsmasq
lease cache had expired (the VM was off for a while; the SBC VM came up
first and took `122.3`). DHCP gave Asterisk `192.168.122.247` from the
upper end of the pool. This is normal DHCP behavior, not a misconfig.

Implication: any code/config that hardcodes `192.168.122.20` is now stale.
The SBC's `$du` line was rendered against 122.20 in Step 3 — we re-rendered:

```bash
ASTERISK_IP=192.168.122.247 envsubst '${ASTERISK_IP}' < sbc/opensips.cfg.tmpl \
  | ssh deb@192.168.122.3 'sudo tee /etc/opensips/opensips.cfg > /dev/null'
sudo /usr/sbin/opensips -C -f /etc/opensips/opensips.cfg     # ok
sudo systemctl reload-or-restart opensips                    # active
```

Quick reading: `grep '\$du' /etc/opensips/opensips.cfg` confirms both
`$du = "sip:192.168.122.247:5060";` lines are updated.

Asterisk health on the VM:

```bash
sudo systemctl is-active asterisk             # active
sudo ss -ulnp | grep ':5060 '                 # asterisk on 0.0.0.0:5060
sudo asterisk -rx 'pjsip show endpoints' | head
# Endpoint: 1001  Unavailable  0 of inf
# Endpoint: 1002  Unavailable  0 of inf
```

Both endpoints are `Unavailable` because no baresip has registered yet
(directly OR through the SBC). That registration is the next move.

Carry-over notes / what is still pending for "full Step 4":

- Asterisk PJSIP needs `support_path=yes` on the AOR for it to honor the
  `Path:` header the SBC inserts. Without it, when Asterisk has to reach
  the softphone (qualify OPTIONS, callback INVITE) it would try Contact's
  IP directly instead of routing through the SBC. Edit needed in
  `asterisk/pjsip-endpoint.conf.tmpl`, then re-run `make install` on the
  Asterisk VM.
- baresip on the host still has `<sip:1001@192.168.122.20>` (the
  pre-rebuild Asterisk IP). The accounts file must point at the SBC:
  `<sip:1001@192.168.122.3>`. SIP auth domain follows registrar — baresip
  signaling now goes to SBC; SBC adds Path and relays to Asterisk's
  current `122.247`.
- After the two above, the first real REGISTER will cross the chain. We
  watch it in sngrep simultaneously on host, SBC (`/var/log/syslog` +
  sngrep), and Asterisk VM.

A repeating risk to flag for the deploy story: this DHCP-shuffle happens
any time the cache expires or VM start order changes. Long-term fix:
either DHCP host reservations in libvirt's `default` network XML (pin MAC
→ IP), or render configs from `virsh domifaddr` output at deploy time so
the IPs are never typed by hand. For the lab we keep the re-render dance
explicit — it's a useful demonstration of the SBC ↔ Asterisk coupling.

#### Execution log — Step 4 (rest): support_path on Asterisk + baresip → SBC

Date: 2026-06-28.

Asterisk-side template change (`asterisk/pjsip-endpoint.conf.tmpl`):

```diff
 [${SIP_EXT}]
 type=aor
 max_contacts=1
 remove_existing=yes
 qualify_frequency=60
+support_path=yes
```

`support_path=yes` tells PJSIP to honor the `Path:` header from REGISTER per
RFC 3327. Without it, Asterisk would only remember the softphone's `Contact:`
IP and try to send qualify OPTIONS / callback INVITEs directly to the
softphone, bypassing the SBC.

Deploy:

```bash
make deploy VM=deb@192.168.122.247
```

Two side-issues handled on the way:

- The Asterisk VM had no `rsync` binary (Debian 13 minimal cloud image).
  Quick `apt-get install -y rsync` before the deploy worked. Going forward
  rsync should land in `install.sh`'s apt prerequisites list so a fresh
  Asterisk VM doesn't trip on this.
- `make deploy` also re-runs `setup-transcriber.sh`. It's idempotent — every
  pip requirement reports "already satisfied" and the systemd unit is
  re-installed in place. No harm; just a long pip dependency dump at the
  tail of the deploy output.

Verification on the Asterisk VM:

```bash
sudo grep -A5 'type=aor' /etc/asterisk/pjsip.d/1001.conf
# type=aor
# max_contacts=1
# remove_existing=yes
# qualify_frequency=60
# support_path=yes

sudo asterisk -rx 'pjsip show aor 1001' | grep support_path
# support_path : true
```

Host baresip re-pointed at the SBC (`~/.baresip/accounts`):

```bash
cp ~/.baresip/accounts ~/.baresip/accounts.bak.20260628
sed -i 's/192\.168\.122\.20/192.168.122.3/g' ~/.baresip/accounts
```

Backup file saved next to the original; rewrite is global on that file but
only the two active account lines contained the old IP. Result:

```text
<sip:1001@192.168.122.3>;auth_pass=...;transport=udp;regint=3600;...
<sip:1002@192.168.122.3>;auth_pass=...;transport=udp;regint=3600;...
```

Auth passwords untouched — Asterisk still validates digest. SIP REGISTER
will now go host → SBC (122.3) → Asterisk (122.247).

State of the chain after Step 4:

| Hop                        | Service           | Listens at              | Ready? |
|----------------------------|-------------------|-------------------------|--------|
| Host (baresip)             | not yet started   | n/a                     | config OK |
| SBC VM (192.168.122.3)     | opensips          | `0.0.0.0:5060/udp`      | yes    |
| SBC VM (192.168.122.3)     | rtpengine-daemon  | `127.0.0.1:2223/udp` ng | yes    |
| Asterisk VM (192.168.122.247) | asterisk       | `0.0.0.0:5060/udp` + PJSIP | yes |

No REGISTER has happened yet — baresip hasn't been launched. That is the
next step: start baresip, watch REGISTER (and the 401/200) cross all three
legs in three side-by-side sngrep windows, then dial `600` for the first
end-to-end call with RTP traversal through rtpengine.

#### Execution log — Step 5: first REGISTER through the SBC (three bugs fixed)

Date: 2026-06-28.

baresip was started; it consistently failed in three sequential ways before
the first endpoint registered. Each diagnosis was driven by an Asterisk-side
hint (journal `NOTICE`/`WARNING` lines) plus a tcpdump capture on the SBC.

**Bug 1 — password mismatch.** Initial symptom: Asterisk journal showed
`Failed to authenticate` for every REGISTER, and baresip stayed at
`401 Unauthorized (Asterisk PBX 22.9.0)`. The SBC was transparent; the
401 even said "Asterisk PBX". That made it clear auth failed against
Asterisk, not the SBC. Direct comparison:

```text
Asterisk /etc/asterisk/pjsip.d/{1001,1002}.conf:
  password=testpass1001  /  password=testpass1002
Host  ~/.baresip/accounts:
  auth_pass=LinphoneDevPass_2026!  /  auth_pass=BaskaBirSifre_2026!
```

This mismatch predated the SBC work — the baresip file had drifted from
some earlier round of password rotation. Fixed on the host:

```bash
cp ~/.baresip/accounts ~/.baresip/accounts.bak.20260628
sed -i -E '67s/auth_pass=[^;]*/auth_pass=testpass1001/;
           68s/auth_pass=[^;]*/auth_pass=testpass1002/' ~/.baresip/accounts
```

baresip restarted. Auth now passed → next failure surfaced.

**Bug 2 — opensips advertising `0.0.0.0` in Via and Path.** Symptom flipped
from 401 to `420 Bad Extension`. tcpdump on the SBC showed the REGISTER
that opensips was relaying to Asterisk carried:

```text
Via:  SIP/2.0/UDP 0.0.0.0:5060;branch=...
Path: <sip:0.0.0.0;lr;received=sip:192.168.122.1:48027>
```

Cause: the config used `socket=udp:0.0.0.0:5060`. OpenSIPS bound on
all interfaces correctly, but it also wrote the literal `0.0.0.0` into
outbound headers because it had no other "self" IP to use. Fix in template:

```diff
-socket=udp:0.0.0.0:5060
+socket=udp:${SBC_IP}:5060
```

Render now needs both variables; deploy:

```bash
SBC_IP=192.168.122.3 ASTERISK_IP=192.168.122.247 \
  envsubst '${SBC_IP} ${ASTERISK_IP}' < sbc/opensips.cfg.tmpl \
  | ssh deb@192.168.122.3 'sudo tee /etc/opensips/opensips.cfg >/dev/null'
sudo systemctl restart opensips
sudo ss -ulnp | grep :5060
# UNCONN ... 192.168.122.3:5060 ...
```

Confirmed: opensips now binds specifically on the SBC IP, headers carry it.

**Bug 3 — Path without `Supported: path`.** Asterisk still returned 420.
The actual reason landed in the journal (which we hadn't surfaced earlier):

```text
WARNING res_pjsip_registrar.c:784 register_aor_core:
  Invalid modifications made to REGISTER request from '1001' by intervening proxy
```

RFC 3327 says: when a registrar receives a REGISTER carrying a `Path:`
header inserted by a proxy, the UAC must have advertised `Supported: path`
to consent to that modification. baresip does not advertise it. With
`support_path=yes` on the AOR, PJSIP still rejects on the consent check,
not the support check. Standard remediation is for the proxy itself to
inject `Supported: path` on the UAC's behalf. Template fix:

```diff
 if (is_method("REGISTER")) {
+    append_hf("Supported: path\r\n");
     add_path_received();
     $du = "sip:${ASTERISK_IP}:5060";
     t_relay();
     exit;
 }
```

`append_hf` comes from `textops.so` which was already loaded. Re-render
and restart opensips. Within seconds baresip's next retry produced a clean
flow.

**Resulting first registration:**

```bash
sudo asterisk -rx 'pjsip show contacts'
#  Contact:  1001/sip:1001@192.168.122.1:48027   Avail   RTT 1.863 ms

sudo asterisk -rx 'pjsip show contact 1001/sip:1001@192.168.122.1:48027'
#  path     : <sip:192.168.122.3;lr;received=sip:192.168.122.1:48027>
#  uri      : sip:1001@192.168.122.1:48027
#  via_addr : 192.168.122.1
#  via_port : 48027
```

Reading that output:

- `path` is now correctly built from the SBC IP. PJSIP will route any
  outbound traffic to this AOR (callback INVITE, qualify OPTIONS) via the
  SBC's URI in the Path, not directly to the softphone.
- `uri` is the softphone's actual contact — the SBC did not rewrite Contact
  in the REGISTER (this is the stateless-proxy form of pass-through; full
  topology hiding would replace this with the SBC IP and require B2BUA).
- `Avail` with RTT 1.863 ms is the proof that an Asterisk-originated
  OPTIONS round-tripped through SBC → softphone → SBC → Asterisk
  successfully. The whole SIP path is up.

1002 is still `Unavailable` at log-write time — baresip's per-account
retry backoff is staggered; it will register on its next attempt without
further intervention.

Final picture of the chain after Step 5's REGISTER phase:

| Hop                                  | Role         | Status      |
|--------------------------------------|--------------|-------------|
| Host baresip (192.168.122.1:48027)   | UAC          | registered  |
| SBC opensips (192.168.122.3:5060)    | proxy + Path | relaying    |
| SBC rtpengine (127.0.0.1:2223 ng)    | media (idle) | ready       |
| Asterisk PJSIP (192.168.122.247:5060)| registrar    | endpoint Not in use |

Next inside Step 5: dial `600` from baresip and watch the call complete
end-to-end with RTP passing through rtpengine.

#### Step 5 (continued): first call to 600 through the SBC

Date: 2026-06-28.

baresip dialed `sip:600@192.168.122.3` (the SBC IP, not Asterisk's). The
call lasted from `19:46:01` to `19:46:36` (~35 s).

**rtpengine session lifecycle** (call-id `c2543b6137e0be87`):

```text
19:46:01.232  offer  from 127.0.0.1:54979 → reply (allocated port pair)
19:46:01.234  offer  from 127.0.0.1:38761 → reply (idempotent, INVITE retransmit
                                                  hit a different worker)
19:46:01.245  answer from 127.0.0.1:38761 → reply (learned Asterisk's media side)
19:46:36.538  delete from 127.0.0.1:56410 → "Scheduling deletion of entire call in 30 seconds"
```

The `delete`'s "Scheduling deletion of entire call" message only appears
when there was a *live session* to tear down. That is the unambiguous proof
that rtpengine had a media bridge built and was relaying RTP between
softphone and Asterisk during the call — neither side was talking directly
to the other.

**Asterisk recording landed normally:**

```bash
sudo ls -lh /var/spool/asterisk/monitor/
# -rw-r--r-- 1 asterisk asterisk 551K  19:46  20260628-194601-1001-600-1782675961.0.wav
```

~551 KB for 35 seconds of stereo (MixMonitor records two-leg). Filename
encoding follows the existing dialplan template: `<timestamp>-<caller>-<dialed>-<uniqueid>`.

**Bug 4 (the only real bug from the call) — `onreply_route` fired on every
200 OK, not just SDP-bearing ones.** Symptoms in syslog during and after
the call:

```text
ERROR:rtpengine:rtpe_function_call:    proxy replied with error: Unknown call-id
ERROR:rtpengine:rtpe_function_call_ok: proxy didn't return "ok" result
ERROR:rtpengine:rtpengine_offer_answer_body: can't extract body from the message
```

`onreply_route` called `rtpengine_answer()` on the 200 OK reply to
REGISTER, OPTIONS-qualify, and BYE — all bodyless. For each, rtpengine
either had no matching call-id (REGISTER/OPTIONS) or there was no SDP to
parse (BYE). Functionally harmless (the actual INVITE 200 OK still got
its `rtpengine_answer` because that one DID have a body and DID match the
prior offer's call-id), but it pollutes syslog and would mask real
issues. Template fix:

```diff
 onreply_route {
-    if ($rs == 180 || $rs == 183 || $rs == 200) {
+    if (($rs == 180 || $rs == 183 || $rs == 200) && has_body("application/sdp")) {
         rtpengine_answer();
     }
 }
```

Re-rendered + restarted. Next call should run completely clean.

**Race condition uncovered in the existing transcriber (NOT an SBC bug):**

```text
Jun 28 19:46:02 ... transcribing /var/spool/asterisk/monitor/<file>.wav
Jun 28 19:46:03 ... wrote /var/spool/asterisk/monitor/<file>.txt
```

The watcher pounced on the WAV one second after `MixMonitor` opened it,
while the call was still ongoing for another 34 seconds. It transcribed
the empty/near-empty initial slice (0-byte `.txt`). Re-running the
transcriber on the completed file by hand produced a meaningful (if
hallucinated) transcript — confirming the transcription engine itself
works. The watcher needs to wait for file stability (mtime quiet for N
seconds) before processing. This bug existed before the SBC work; it
just became visible because we ran a complete call top-to-bottom with
fresh eyes. Tracked as a follow-up to fix in `scripts/watcher.py`.

**Summary of Step 5:**

The SBC-mediated path is fully working end to end. Four bugs surfaced, all
fixed in the template (template now at correct shape for the lab):

| # | Bug                                          | Layer            | Fix                                  |
|---|----------------------------------------------|------------------|--------------------------------------|
| 1 | Password mismatch                            | baresip vs .env  | Realigned baresip auth_pass values   |
| 2 | opensips bound `0.0.0.0`, wrote it into headers | `socket=` directive | `socket=udp:${SBC_IP}:5060` (new env) |
| 3 | RFC 3327: Path without Supported:path → 420  | opensips REGISTER route | `append_hf("Supported: path\r\n");` before `add_path_received()` |
| 4 | `rtpengine_answer()` on all 200 OK responses | opensips onreply | Gate with `is_method("INVITE") && has_body("application/sdp")` |

End-state checks pass:

- baresip 1001 `Avail`, RTT 1.8 ms via SBC.
- pjsip contact records `path: <sip:192.168.122.3;lr;received=sip:192.168.122.1:48027>`.
- rtpengine offer/answer/delete cycle observed for the call.
- WAV recording landed on Asterisk VM.
- Transcript engine works (race condition in the trigger logic is a
  pre-existing watcher issue, not an SBC issue).

**Bug 4 retest revealed a second case the gate needed to catch.** After
deploying the first version of the gate (`has_body("application/sdp")` only),
the next qualify cycle still produced `Unknown call-id` errors. Reason:
baresip responds to Asterisk's qualify `OPTIONS` *with an SDP body* (a
capability advertisement carrying `m=audio 9 RTP/AVP 0 8 101` and codec
attributes). The body check alone passed those through and `rtpengine_answer()`
fired against an unknown call-id.

Tightened gate:

```diff
-if (($rs == 180 || $rs == 183 || $rs == 200)
-    && has_body("application/sdp")) {
+if (is_method("INVITE")
+    && ($rs == 180 || $rs == 183 || $rs == 200)
+    && has_body("application/sdp")) {
     rtpengine_answer();
 }
```

In `onreply_route` `is_method()` matches against the CSeq method (the
request the reply belongs to), so this correctly excludes OPTIONS / REGISTER
/ BYE responses.

Verification — 70 s window after restart (one full qualify cycle for both
endpoints), watching the cumulative error counter in `/var/log/syslog`:

```bash
sudo grep -c -E 'ERROR|Unknown call-id|can.t extract' /var/log/syslog
# before wait: 204
# after  wait: 204     ← zero delta; no new errors despite OPTIONS exchange
```

Clean retest call also leaves zero new errors (call 2: `20260628-201947-1001-600-....wav`, 631 KB).

## Monitoring VM: Zabbix + Grafana

Added a third VM role:

```text
monitoring-deb13-cloudinit        current DHCP: 192.168.122.13
  PostgreSQL 17
  Zabbix 7.0 LTS server + Apache PHP frontend
  zabbix-agent2
  Grafana 13.1
  Grafana Zabbix plugin

asterisk-deb13-cloudinit          current DHCP: 192.168.122.247
  zabbix-agent2

opensips-sbc-deb13-cloudinit      current DHCP: 192.168.122.3
  zabbix-agent2
  OpenSIPS MI FIFO metric helper
```

The monitoring VM is provisioned by repo-owned files under `monitoring/`.
Do not hand-edit rendered monitoring state and expect it to survive; rerun
the matching script:

```text
monitoring/install.sh                  monitoring VM installer
monitoring/setup-zabbix-agent.sh       zabbix-agent2 setup for lab nodes
monitoring/verify.sh                   monitoring VM smoke checks
monitoring/verify-agent.sh             monitored-node agent checks
monitoring/zabbix-web.conf.php.tmpl    rendered to /etc/zabbix/web/zabbix.conf.php
monitoring/zabbix-agent-lab.conf.tmpl  rendered to /etc/zabbix/zabbix_agent2.d/lab.conf
monitoring/opensips-mi.py              installed as /usr/local/bin/opensips-mi-zabbix
monitoring/provision-observability.py  creates Zabbix host/items through Zabbix API
monitoring/grafana-*.yaml/json         datasource + dashboard file provisioning
```

Make targets added:

```bash
make deploy-monitoring MONITORING_VM=deb@192.168.122.13
make deploy-agent-asterisk VM=deb@192.168.122.247
make deploy-agent-sbc SBC_VM=deb@192.168.122.3
make verify-monitoring
make verify-zabbix-agent
```

Because this host currently has a bad global SSH config include ownership
(`/etc/ssh/ssh_config.d/20-systemd-ssh-proxy.conf`), lab deploys were run
with:

```bash
SSH="ssh -F /dev/null"
```

The Makefile now passes `$(SSH)` to rsync via `RSYNC_SSH ?= $(SSH)`, so the
same override works for both the SSH command and the rsync transport.

### Monitoring secrets and per-VM env

`.env` is still excluded from deploy. Monitoring-specific names in
`.env.example`:

```text
MONITORING_IP=
ZABBIX_DB_PASSWORD=
ZABBIX_VERSION=7.0
```

The monitoring VM needs `MONITORING_IP`, `ZABBIX_DB_PASSWORD`, and
`ZABBIX_VERSION` in its local `~/asterisk-lab/.env`.

Monitored nodes need at least:

```text
MONITORING_IP=192.168.122.13
ZABBIX_VERSION=7.0
```

The SBC also needs fresh SIP routing IPs:

```text
SBC_IP=192.168.122.3
ASTERISK_IP=192.168.122.247
```

This was an actual failure: SBC `.env` still had `ASTERISK_IP=192.168.122.20`
after DHCP changed Asterisk to `192.168.122.247`. OpenSIPS relayed REGISTER
to the stale IP and baresip saw `408 Request Timeout`. Updating `.env` and
rerunning `make deploy-sbc` fixed the 408.

### Zabbix frontend fixes learned

Two frontend pitfalls were fixed in `monitoring/install.sh` and
`monitoring/zabbix-web.conf.php.tmpl`:

1. Zabbix web showed `DB type "POSTGRESQL" is not supported... MYSQL`.
   Cause: `php-pgsql` was missing. The installer now installs `php-pgsql`,
   and `monitoring/verify.sh` checks `php -m` includes `pgsql`.
2. Zabbix dashboard showed `Locale for language "en_US" is not found`.
   Cause: Debian cloud image only had `C`, `C.utf8`, and `POSIX`. The
   installer now enables and runs `locale-gen en_US.UTF-8`.
3. Zabbix dashboard raised Elasticsearch errors such as
   `file_get_contents(/uint*/_search)`. Cause: the rendered Zabbix web config
   set `$HISTORY['types']` despite no Elasticsearch URL. The template now uses:

```php
$HISTORY['url'] = '';
$HISTORY['types'] = [];
```

### OpenSIPS metrics path

`opensips-cli` / `opensipsctl` are not available in the current SBC APT
sources. `apt.opensips.org` for this VM exposes OpenSIPS core/modules but no
`opensips-cli` package. OpenSIPS 3.6's `mi_fifo` module is already loaded, so
metrics use the official MI FIFO JSON-RPC transport.

OpenSIPS 3.6 FIFO syntax is JSON-RPC, not the older line-oriented command
format:

```text
:reply_fifo:{"jsonrpc":"2.0","method":"get_statistics","id":"...","params":[["all"]]}
```

The old `:get_statistics:reply_fifo\nall\n\n` shape logs
`mi_fifo_callback: cannot parse command`.

Linux protected FIFOs also matter. `/tmp` reply FIFOs fail with permission
errors when caller and OpenSIPS users differ. The SBC template now sets:

```text
modparam("mi_fifo", "reply_dir", "/run/opensips/")
```

`monitoring/setup-zabbix-agent.sh` installs `/usr/local/bin/opensips-mi-zabbix`,
adds `zabbix` to the `opensips` group, sets `/run/opensips` to group-writable,
and installs a tmpfiles rule:

```text
d /run/opensips 0775 opensips opensips -
```

The helper creates reply FIFOs under `/run/opensips`, changes their group to
`opensips`, uses a 5 s timeout, and talks JSON-RPC over
`/run/opensips/opensips_fifo`.

### Zabbix items collected from OpenSIPS/SBC

Zabbix host:

```text
host: opensips-sbc-deb13-cloudinit
visible name: OpenSIPS SBC
group: Asterisk Lab
agent interface: 192.168.122.3:10050
```

Provisioned item keys:

```text
lab.opensips.mi.ping
lab.opensips.stat[rcv_requests]
lab.opensips.stat[fwd_requests]
lab.opensips.stat[drop_requests]
lab.opensips.stat[err_requests]
lab.opensips.stat[2xx_transactions]
lab.opensips.stat[4xx_transactions]
lab.opensips.stat[5xx_transactions]
lab.opensips.stat[used_size]
lab.opensips.stat[free_size]
lab.systemd.active[opensips]
lab.systemd.active[rtpengine-daemon]
```

Live validation examples from the monitoring VM:

```bash
zabbix_get -s 192.168.122.3 -k lab.opensips.mi.ping
# 1

zabbix_get -s 192.168.122.3 -k 'lab.opensips.stat[used_size]'
# 3511312

zabbix_get -s 192.168.122.3 -k 'lab.opensips.stat[free_size]'
# 63539488
```

After a baresip REGISTER storm, OpenSIPS counters were visible through Zabbix:

```bash
zabbix_get -s 192.168.122.3 -k 'lab.opensips.stat[rcv_requests]'
# 23 before OpenSIPS restart, reset to 2 after restart
```

Counters are OpenSIPS process counters and reset when OpenSIPS restarts.

### Grafana

Grafana plugin:

```text
alexanderzobnin-zabbix-app @ 6.4.1
datasource type: alexanderzobnin-zabbix-datasource
```

Grafana file provisioning installed:

```text
/etc/grafana/provisioning/datasources/zabbix.yaml
/etc/grafana/provisioning/dashboards/asterisk-lab.yaml
/var/lib/grafana/dashboards/asterisk-lab/opensips-sbc-overview.json
```

Dashboard URL:

```text
http://192.168.122.13:3000/d/opensips-sbc-overview/opensips-sbc-overview
```

Dashboard panels:

```text
OpenSIPS MI status
OpenSIPS + rtpengine service status
SIP request counters
2xx / 4xx / 5xx transaction counters
OpenSIPS shared memory used/free
```

Grafana default `admin/admin` worked initially but was later no longer valid,
so the password was changed through the UI or by Grafana first-login flow.
The repo does not store the current Grafana admin password.

### Current verification status

Known-good checks after monitoring work:

```text
monitoring/verify.sh on monitoring VM: 20/20 OK
monitoring/verify-agent.sh on SBC:     7/7 OK
sbc/verify.sh on SBC:                  11/11 OK
```

Zabbix API verified:

```text
Zabbix API version: 7.0.27
OpenSIPS SBC host exists with 12 provisioned items
```

Host web checks:

```text
http://192.168.122.13/zabbix/      -> 200
http://192.168.122.13:3000/login   -> 200
Grafana dashboard URL              -> 302 to login/dashboard
```

### Baresip registration after monitoring/SBC changes

The initial post-monitoring registration failure had two separate causes:

1. `408 Request Timeout` from OpenSIPS:
   SBC `.env` had stale `ASTERISK_IP=192.168.122.20`. Current Asterisk IP is
   `192.168.122.247`. Updating `.env` and rerunning `make deploy-sbc` fixed
   relay routing.
2. Repeating `401 Unauthorized` from Asterisk:
   Asterisk logs showed `Failed to authenticate`. Host `~/.baresip/accounts`
   passwords did not match the Asterisk VM `.env` values for 1001/1002. The
   host baresip accounts were updated from the VM `.env` without printing the
   secret values.

Reminder: one `401 Unauthorized` is normal in SIP digest auth. A healthy flow is:

```text
REGISTER -> 401 Unauthorized
REGISTER with Authorization -> 200 OK
```

Repeated 401s with `Failed to authenticate` mean password drift.
