# Asterisk onboarding

End-to-end Asterisk 22 LTS setup on Debian/Ubuntu: source build, PJSIP softphone registration with baresip, sngrep capture, call recording, transcription.

## Start Here (for agents and repo maintainers)

Read in this order:

1. `AGENTS.md` - agent rulebook, directory ownership, working rules, done criteria.
2. `PLANS.md` - live execution state.
3. `docs/specs/` the governing spec if `PLANS.md` points to one, paired with `docs/prompts/`.
4. `docs/memory/` - proven decisions and durable facts.
5. `docs/runbooks/` - operational procedures and plan/spec rules.

This README is human onboarding, not the acceptance contract.

The deliverable is a repo you can clone onto a fresh Debian 13 / Ubuntu 26.04 box and bring up to a working Asterisk PBX with one command.

An optional second VM adds an **OpenSIPS 3.6 LTS SBC** with rtpengine so both SIP signaling and RTP media travel host softphone ⇄ SBC ⇄ Asterisk. A third VM can run **Zabbix 7.0 LTS + Grafana** for lab monitoring. The SBC and monitoring layers are described in their own sections below; Asterisk-only operation is unchanged.

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
| QEMU/KVM + `qemu-img` | `qemu-base`       | `qemu-system-x86` + `qemu-utils`               | `qemu-kvm` + `qemu-img`          |
| `dnsmasq`         | `dnsmasq`             | `dnsmasq-base` (pulled in by libvirt)          | bundled with `libvirt-daemon`    |
| NAT helpers       | `iptables-nft`        | (default)                                      | (default)                        |
| `virt-install`    | `virt-install`        | `virtinst`                                     | `virt-install`                   |
| `cloud-localds`   | `cloud-image-utils`   | `cloud-image-utils`                            | `cloud-utils` / `cloud-utils-growpart` |
| `curl`            | `curl`                | `curl`                                         | `curl`                           |

In addition, the host kernel must have the `sch_htb` traffic-control module available (`/lib/modules/$(uname -r)/kernel/net/sched/sch_htb.ko*`). Standard kernels ship it; the bootstrap script loads it.

### Option A: reproducible SSH-ready VM with cloud-init

This is the fastest non-interactive path. It downloads the official Debian 13 genericcloud image, expands it to a fresh independent qcow2 disk, creates a NoCloud seed ISO with your SSH public key, defines `asterisk-deb13-cloudinit`, starts it, and prints the DHCP lease when available.

```bash
# 1. Install the host dependencies above with your package manager.

# 2. Run the libvirt bootstrap. Loads sch_htb, enables libvirtd, starts
#    the default NAT network, creates the default storage pool.
./infra/libvirt/setup-host.sh

# 3. Create and start the VM. Defaults:
#    DOMAIN=asterisk-deb13-cloudinit
#    SSH_PUBKEY_FILE=$HOME/.ssh/id_ed25519.pub
#    DISK_SIZE=30G
#    MEMORY_GIB=4
#    VCPUS=4
./infra/libvirt/create-cloudinit-vm.sh

# 4. Find the VM IP if it was not printed yet.
virsh -c qemu:///system domifaddr asterisk-deb13-cloudinit --source lease

# 5. SSH in and follow the Quick start above.
ssh deb@<vm-ip>
```

Useful overrides:

```bash
DOMAIN=asterisk-deb13-test \
SSH_PUBKEY_FILE=~/.ssh/id_ed25519.pub \
DISK_SIZE=30G \
MEMORY_GIB=4 \
VCPUS=4 \
./infra/libvirt/create-cloudinit-vm.sh
```

The generated VM uses independent libvirt volumes:

```text
/var/lib/libvirt/images/<DOMAIN>.qcow2
/var/lib/libvirt/images/<DOMAIN>-seed.iso
```

The seed ISO contains only host/user bootstrap data: hostname, username, sudo rule, and your SSH public key. It does not contain SIP passwords; those still belong in the target VM's `/etc/asterisk-lab/env`.

### Option B: manual qcow2 VM

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
Makefile                 install / verify / deploy / logs targets for both VMs (`make help`)
install.sh               builds Asterisk + renders configs on the Asterisk VM
asterisk/
  pjsip.conf.tmpl              transport + #include pjsip.d/*.conf
  pjsip-endpoint.conf.tmpl     rendered once per SIP_EXTENSIONS entry → pjsip.d/<ext>.conf
                                   (AOR carries support_path=yes for the SBC path)
  extensions.conf.tmpl         answers extension 600 and records WAV calls
  rtp.conf
  asterisk.service             systemd unit for asterisk
  transcriber.service          systemd unit for the watcher (hardened)
sbc/                     SBC VM (OpenSIPS 3.6 LTS + rtpengine)
  opensips.cfg.tmpl            stateless proxy + Path + rtpengine-managed media
  rtpengine.conf.tmpl          interface = ${SBC_IP}, 30000–40000, userspace
  install.sh                   idempotent: apt repo, packages, render, RUN_OPENSIPS=yes
  verify.sh                    11 smoke checks (services, sockets, parses, mi_fifo)
scripts/
  transcribe.py                local-Whisper one-shot transcriber
  watcher.py                   polls monitor dir, transcribes new WAVs in place
  setup-transcriber.sh         installs venv + transcriber systemd unit
  requirements.txt             pinned openai-whisper + torch
  verify.sh                    smoke checks (asterisk, dialplan, transcriber)
infra/libvirt/           optional libvirt convenience
  asterisk-deb13.xml                 domain XML using default pool + default network
  asterisk-deb13-cloudinit.xml       reference XML for the default Asterisk cloud-init VM
  opensips-sbc-deb13-cloudinit.xml   reference XML for the SBC cloud-init VM
  create-cloudinit-vm.sh             downloads Debian cloud image + seed ISO + starts VM
  setup-host.sh                      host-side libvirt bootstrap
monitoring/               Monitoring VM (Zabbix 7.0 LTS + PostgreSQL + Grafana)
  install.sh                    idempotent monitoring stack installer
  setup-zabbix-agent.sh         idempotent zabbix-agent2 installer for lab nodes
  zabbix-web.conf.php.tmpl      rendered frontend config for /etc/zabbix/web
  verify.sh                     monitoring VM smoke checks
  verify-agent.sh               monitored-node agent smoke checks
.github/workflows/
  lint.yml                     shellcheck + ruff on push/PR
PROCESS.md               running log of decisions, errors, and fixes
.env.example             config template (copy to .env, fill in, never commit)
```

---

## Adding the OpenSIPS SBC layer

This step is optional. If you only need Asterisk, skip it — the rest of the
repo continues to work exactly as before. Adding the SBC inserts an
OpenSIPS 3.6 LTS proxy plus rtpengine between the host softphone and the
Asterisk PBX so both SIP signaling and RTP media flow through it.

Topology end-state (libvirt default NAT, IPs from DHCP):

```text
host (baresip)        opensips-sbc-deb13-cloudinit        asterisk-deb13-cloudinit
                  SIP UDP 5060             SIP UDP 5060
   ─────────────────────────► OpenSIPS ─────────────────────────►
                                  │
                                  └─ rtpengine (ng on 127.0.0.1:2223)
                                       relays RTP UDP 30000–40000
```

OpenSIPS is a **stateless proxy** in this lab: it does not rewrite
`Call-ID` or `From`/`To` tags, but it does stack a `Via`, insert
`Record-Route`, add a `Path` on REGISTER, inject `Supported: path` so
Asterisk accepts that Path, and call `rtpengine_offer/answer/delete` on
INVITE/200/BYE to keep media flowing through the SBC. Topology-hiding
B2BUA is parked for a follow-up.

### 1. Provision the SBC VM

Same libvirt cloud-init script as the Asterisk VM, with a different domain
name and smaller resource caps (the SBC is light):

```bash
DOMAIN=opensips-sbc-deb13-cloudinit \
DISK_SIZE=20G \
MEMORY_GIB=2 \
VCPUS=2 \
  ./infra/libvirt/create-cloudinit-vm.sh

virsh -c qemu:///system net-dhcp-leases default | grep opensips-sbc
# e.g. 192.168.122.3   opensips-sbc-deb13-cloudinit
```

### 2. Place the lab env on the SBC VM

The SBC needs to know its own IP (used in `socket=` and therefore in
`Via` / `Record-Route` / `Path` headers) and the Asterisk VM's IP (the
relay target). Both come from `virsh net-dhcp-leases default`.

```bash
ssh deb@<sbc-ip>
sudo install -d -m 0755 /etc/asterisk-lab
sudo tee /etc/asterisk-lab/env >/dev/null <<EOF
SBC_IP=<sbc-ip>
ASTERISK_IP=<asterisk-ip>
EOF
sudo chmod 600 /etc/asterisk-lab/env
```

### 3. Deploy and verify

From the host:

```bash
make deploy-sbc SBC_VM=deb@<sbc-ip>
ssh deb@<sbc-ip> 'cd /opt/asterisk-lab/current && sudo ./sbc/verify.sh'
```

`deploy-sbc` rsyncs the SBC payload to `/opt/asterisk-lab/current` and runs `sbc/install.sh` on the SBC VM —
idempotent: re-run any time after editing `sbc/opensips.cfg.tmpl` or
`sbc/rtpengine.conf.tmpl`. `make verify-sbc` is the same `sbc/verify.sh`
but executed locally on the SBC VM (mirrors `make verify` on the
Asterisk side); use it after SSHing in, or invoke the script directly
over SSH as shown above. `verify.sh` prints one line per check:

```text
== opensips ==
  opensips.service active                      OK
  opensips 3.6.x installed                     OK
  opensips.cfg parses                          OK
  udp/5060 bound by opensips                   OK
  mi_fifo present (0666)                       OK

== rtpengine ==
  rtpengine-daemon.service active              OK
  udp/2223 bound by rtpengine                  OK
  userspace mode (table=-1)                    OK
  log-facility=local1                          OK

== shared ==
  rsyslog active (/var/log/syslog)             OK
  sngrep installed                             OK

11/11 OK
```

### 4. Point baresip at the SBC

Edit `~/.baresip/accounts` on the host so the SIP domain in each account
is the **SBC IP**, not Asterisk's:

```text
<sip:1001@<sbc-ip>>;auth_pass=<SIP_EXT_1001_PASSWORD>;transport=udp;regint=3600;answermode=auto;audio_codecs=opus,PCMU,PCMA
<sip:1002@<sbc-ip>>;auth_pass=<SIP_EXT_1002_PASSWORD>;transport=udp;regint=3600;answermode=auto;audio_codecs=opus,PCMU,PCMA
```

Restart baresip. The auth passwords are unchanged — Asterisk still
validates digest; the SBC is transparent to auth.

Verify the registration crossed both legs:

```bash
ssh deb@<asterisk-ip> 'sudo asterisk -rx "pjsip show contacts"'
# Contact: 1001/sip:1001@<host-ip>:<port>   Avail   RTT 1–3 ms

ssh deb@<asterisk-ip> 'sudo asterisk -rx "pjsip show contact 1001/sip:1001@<host-ip>:<port>" | grep ^path'
# path : <sip:<sbc-ip>;lr;received=sip:<host-ip>:<port>>
```

Two side-by-side `sudo sngrep -d any port 5060` windows (one on the SBC
VM, one on the Asterisk VM) show the full REGISTER + INVITE flow on
their respective legs.

### 5. Live observation

Both OpenSIPS and rtpengine route to syslog:

```bash
ssh deb@<sbc-ip> 'sudo tail -f /var/log/syslog'        # or: make logs-sbc
                                                       # opensips lines: facility local0
                                                       # rtpengine lines: facility local1
ssh deb@<sbc-ip> 'sudo tcpdump -i any -n udp portrange 30000-40000'   # RTP through rtpengine
```

If `tcpdump` on those ports shows zero packets during an active call
while audio is working, RTP is bypassing the SBC — typical cause is
`rtpengine_offer()` returning error (check `/var/log/syslog`).

---

## Verification after install

```bash
make verify                                     # asterisk lab: 10+ checks; exits non-zero on first failure
ssh deb@<sbc-ip> 'cd /opt/asterisk-lab/current && sudo ./sbc/verify.sh'   # (optional) SBC lab: 11 checks
```

`make verify` and `make verify-sbc` both run the smoke-check script locally on whichever host invokes them — they mirror the asymmetry that `make install` already has. To verify a remote VM, SSH in and run `make verify[-sbc]` from there, or call the script over SSH as shown.

`verify.sh` covers `asterisk.service` active, version, each PJSIP endpoint listed in `/etc/asterisk/pjsip.d/` present (discovered at runtime — no hardcoded list), dialplan `600` loaded, `/var/spool/asterisk/monitor` writable by `asterisk`, `transcriber.service` active, venv python runnable, `openai-whisper` installed, base model cached, `watcher.py` present.

`sbc/verify.sh` covers `opensips.service` + `rtpengine-daemon.service` active, opensips 3.6 binary present, `opensips.cfg` parses, UDP `5060` bound by opensips, UDP `2223` bound by rtpengine, MI FIFO present, rtpengine in userspace mode + log-facility `local1`, rsyslog active (so `/var/log/syslog` exists), and sngrep installed.

`monitoring/verify.sh` covers PostgreSQL, the Zabbix database/schema, `zabbix-server`, local `zabbix-agent2`, Apache, Grafana, Zabbix/Grafana listening ports, local `zabbix_get`, and the Grafana Zabbix plugin. `monitoring/verify-agent.sh` covers `zabbix-agent2` on monitored nodes.

For a manual look:

```bash
sudo asterisk -rx 'pjsip show endpoints'        # one entry per SIP_EXTENSIONS; Unavailable until softphone registers
sudo asterisk -rx 'pjsip show contacts'         # populated after baresip REGISTER
journalctl -u asterisk -u transcriber -f        # or: make logs (over SSH to $(VM))
```

## Adding the monitoring VM

The monitoring layer adds a third Debian 13 cloud-init VM running Zabbix
7.0 LTS with PostgreSQL, Apache-hosted Zabbix frontend, Grafana, and the
Grafana Zabbix plugin.

```text
host / operator browser
          │
          ▼
monitoring-deb13-cloudinit
  Zabbix UI     http://<monitoring-ip>/zabbix
  Grafana       http://<monitoring-ip>:3000
  Zabbix server tcp/10051
          ▲
          │ zabbix-agent2 tcp/10050
          ├── asterisk-deb13-cloudinit
          └── opensips-sbc-deb13-cloudinit
```

### 1. Provision the monitoring VM

Reuse the generic cloud-init VM creator:

```bash
DOMAIN=monitoring-deb13-cloudinit \
DISK_SIZE=40G \
MEMORY_GIB=4 \
VCPUS=2 \
  ./infra/libvirt/create-cloudinit-vm.sh

virsh -c qemu:///system net-dhcp-leases default | grep monitoring
```

### 2. Place the lab env on the monitoring VM

`make deploy-monitoring` excludes env files, so create
`/etc/asterisk-lab/env` once on the target. `ZABBIX_DB_PASSWORD` is a local
database secret and must not be committed.

```bash
ssh deb@<monitoring-ip>
sudo install -d -m 0755 /etc/asterisk-lab
sudo tee /etc/asterisk-lab/env >/dev/null <<EOF
MONITORING_IP=<monitoring-ip>
ZABBIX_DB_PASSWORD=<strong-local-db-password>
ZABBIX_VERSION=7.0
EOF
sudo chmod 600 /etc/asterisk-lab/env
exit
```

### 3. Deploy and verify monitoring

```bash
make deploy-monitoring MONITORING_VM=deb@<monitoring-ip>
ssh deb@<monitoring-ip> 'cd /opt/asterisk-lab/current && sudo ./monitoring/verify.sh'
```

Grafana's package default login is `admin` / `admin`; rotate it on first
login. Zabbix frontend setup is available at
`http://<monitoring-ip>/zabbix`.

### 4. Install agents on lab nodes

Each monitored node needs `MONITORING_IP` in `/etc/asterisk-lab/env`.

```bash
ssh deb@<asterisk-ip> 'printf "\nMONITORING_IP=<monitoring-ip>\n" | sudo tee -a /etc/asterisk-lab/env'
make deploy-agent-asterisk VM=deb@<asterisk-ip>
ssh deb@<asterisk-ip> 'cd /opt/asterisk-lab/current && sudo ./monitoring/verify-agent.sh'

ssh deb@<sbc-ip> 'printf "\nMONITORING_IP=<monitoring-ip>\n" | sudo tee -a /etc/asterisk-lab/env'
make deploy-agent-sbc SBC_VM=deb@<sbc-ip>
ssh deb@<sbc-ip> 'cd /opt/asterisk-lab/current && sudo ./monitoring/verify-agent.sh'
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

On the host, install baresip and add one account per extension in `SIP_EXTENSIONS` to `~/.baresip/accounts`. The SIP domain after the `@` is whichever VM you want baresip to register against — the Asterisk VM IP for direct-to-Asterisk operation, or the SBC VM IP if you have the SBC layer up:

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

### Without SBC (direct baresip ↔ Asterisk)

With `sudo sngrep -d any port 5060` running on the Asterisk VM, a baresip
REGISTER followed by `/dial sip:600@<asterisk-ip>` produces:

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

### With SBC (baresip → OpenSIPS → Asterisk)

Same flow, now visible on **two** sngrep windows side-by-side — one on the
SBC VM, one on the Asterisk VM. On each leg the message shape is the same
six-step exchange (REGISTER+401+REGISTER+200, INVITE+Trying+Ringing+200,
ACK, BYE+200). What differs is what the SBC injects between the legs:

| Header / SDP element        | Direct        | Through SBC                                  |
|-----------------------------|---------------|----------------------------------------------|
| `Via:` stack                | one hop       | two hops (SBC's `Via` on top of baresip's)   |
| `Record-Route:` on INVITE   | absent        | present, pointing at SBC                     |
| `Path:` on REGISTER         | absent        | present, pointing at SBC                     |
| `Supported: path` on REGISTER | absent      | injected by SBC so Asterisk accepts Path     |
| SDP `c=` (connection IP)    | softphone IP  | SBC IP (rewritten by rtpengine)              |
| SDP `m=` audio port         | softphone port| port from rtpengine's 30000–40000 range      |
| RTP path                    | host ↔ Asterisk direct | host ↔ SBC:30000-40000 ↔ Asterisk |

On the Asterisk side, `pjsip show contact <ext>/<uri>` confirms the SBC
took effect: the `path:` line is populated with the SBC URI, and
`via_addr` / `via_port` show the softphone's true location.

If REGISTER returns `420 Bad Extension`: the SBC must inject
`Supported: path` (RFC 3327 requires the UAC's consent before a proxy
inserts Path; baresip does not advertise it). `sbc/opensips.cfg.tmpl`
does this with `append_hf("Supported: path\r\n")` immediately before
`add_path_received()`.

If RTP goes the wrong way (audio works but `tcpdump -i any -n udp
portrange 30000-40000` on the SBC sees nothing): `rtpengine_offer()` /
`_answer()` may be failing — `/var/log/syslog` on the SBC shows the
reason. Tighten the `onreply_route` gate to fire only on INVITE
responses with SDP if rtpengine reports "Unknown call-id" on non-INVITE
200s (Asterisk's qualify OPTIONS can return SDP from baresip).

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

On Debian 13 with Python 3.13, the pinned `torch==2.12.1` wheel currently pulls CUDA-related wheels even on a CPU-only VM. A fresh cloud-init VM test completed successfully, but the transcriber footprint was material: `/opt/transcriber` was about 4.9 GB and `/var/tmp/pip-cache` about 2.7 GB after install. Use a 30 GB VM disk or larger unless you switch to a CPU-only torch wheel strategy.

**systemd hardening on `transcriber.service`.** Beyond `User=asterisk`, the unit sets `ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`, explicit `ReadWritePaths`, the `ProtectKernel*` group, `NoNewPrivileges`, `RestrictNamespaces`, and friends. `MemoryDenyWriteExecute=true` is **intentionally not set** — PyTorch / numba JIT writes executable pages at runtime and crashes with SIGSYS if it's enabled. `systemd-analyze security transcriber` rates the unit ~5.8 MEDIUM; further hardening (`SystemCallFilter=@system-service`, `CapabilityBoundingSet=`, `ProtectProc=invisible`) is feasible but needs runtime testing to avoid breaking numpy/torch.

**Small VM builds.** Asterisk's source build defaults to `MAKE_JOBS=$(nproc)`. On small VMs this can OOM-kill the compiler. Use at least 4 GB RAM, or run a constrained build:

```bash
sudo MAKE_JOBS=2 ./install.sh
sudo ./scripts/setup-transcriber.sh
```

**`verify.sh` and `pipefail`.** Avoid piping `pip show ...` into `head -1` under `set -o pipefail` — `head` closes the pipe early, `pip` gets `SIGPIPE` and exits 141, and the check reports `FAIL` even though pip succeeded. Same trap with any short-circuiting downstream (`head`, `grep -q`, `awk 'NR==1'`). The current `verify.sh` avoids the pattern; preserve that on extension.

**`make deploy` excludes env files on purpose.** Secrets stay placed manually on the target at `/etc/asterisk-lab/env` (or through production-grade `systemd-creds`/vault). A pipeline that rsyncs a real `.env` into a VM is a leak surface and any audit would flag it.

## Agent context

This repo includes `AGENTS.md` so future agent runs keep the same lab assumptions: templates under `asterisk/*.tmpl` and `sbc/*.tmpl` are the sources of truth, secrets and per-VM config (`SBC_IP`, `ASTERISK_IP`, SIP passwords) stay in `/etc/asterisk-lab/env`, the Linux softphone is baresip, endpoints live in `SIP_EXTENSIONS`, and extension `600` records WAV files under `/var/spool/asterisk/monitor/`.

Project-level skills under `.claude/skills/` document the most common ops flows — adding/removing a SIP endpoint, deploying to the lab VM, debugging registration failures, rotating passwords. Read the matching skill before acting on those tasks.

`PROCESS.md` is the running operational log: design decisions, evolved configs, and the full trail of bugs surfaced while bringing the SBC layer up (password drift, OpenSIPS binding `0.0.0.0` leaking into headers, RFC 3327 `Supported: path` requirement, and gating `rtpengine_answer()` to INVITE-only). Reach for it when an SBC-related decision needs context.
