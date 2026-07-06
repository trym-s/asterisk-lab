# Process Notes

Operational reference for the Asterisk lab. Current repo layout and install flow only — execution logs and one-off debugging narratives have been dropped.

Spec-driven source of truth lives under `docs/specs/`. Use `AGENTS.md` and
`PLANS.md` before treating any workflow here as current.
This file is a current-state index, not an acceptance contract.

## Current Target

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

Scripts are idempotent: re-running skips the Asterisk build when the pinned version is already installed, re-renders config from templates, restarts services, refreshes the transcriber files.

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
/var/lib/asterisk/.cache/whisper/        Local Whisper model cache
/etc/systemd/system/transcriber.service  Transcriber watcher service unit
```

Secrets:

```text
.env                         Local/target secret file, ignored by git
.env.example                 Committed template, names only
SIP_EXT_<num>_PASSWORD       One password per SIP extension
```

## Implementation Decisions

### Asterisk Version

Asterisk is pinned to `22.9.0` via `ASTERISK_VERSION` in `.env.example`. `install.sh` checks `/usr/sbin/asterisk -V`; if the installed version already matches, it skips rebuilding. Source checkout lives at `/usr/local/src/asterisk`.

### Config Source Of Truth

Templates under `asterisk/*.tmpl` are the source of truth. Do not hand-edit rendered files under `/etc/asterisk`; `install.sh` overwrites them on every run.

Endpoint config is generated per extension:

```text
SIP_EXTENSIONS="1001 1002"
SIP_EXT_1001_PASSWORD=...
SIP_EXT_1002_PASSWORD=...
```

Output:

```text
/etc/asterisk/pjsip.d/1001.conf
/etc/asterisk/pjsip.d/1002.conf
```

If an extension is removed from `SIP_EXTENSIONS`, the orphan file in `/etc/asterisk/pjsip.d/` is pruned on the next `install.sh` run.

### Softphone

MicroSIP is Windows-only. This repo documents and tests with `baresip` on Linux. SIP exchange on the Asterisk side:

```text
REGISTER -> 401 Unauthorized
REGISTER with digest -> 200 OK
INVITE -> 100 Trying -> 180 Ringing -> 200 OK -> ACK
BYE -> 200 OK
```

### Dialplan And Recording

Extension `600` is the loopback test target. It answers, starts `MixMonitor`, plays a prompt, then enters `Echo()` so microphone audio is present in the recording.

Direct softphone dialing is covered by `_10XX`, also with `MixMonitor`.

Recordings:

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

The watcher polls `/var/spool/asterisk/monitor/` and writes `<recording>.txt` next to each `.wav`.

Known bug: watcher fires on file creation, before `MixMonitor` finishes writing, producing empty `.txt` output for long calls. Fix in progress: require mtime quiet for N seconds before processing.

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

Watch SIP signaling:

```bash
sudo sngrep -d any port 5060
```

Recording/transcript checks:

```bash
ls -l /var/spool/asterisk/monitor/*.wav
ls -l /var/spool/asterisk/monitor/*.txt
journalctl -u transcriber -n 100 --no-pager
```

## Known Issues And Fixes

### `virsh` Defaults To `qemu:///session`

Domain definition succeeds but start fails because the `default` pool or network is missing. Fix:

```bash
export LIBVIRT_DEFAULT_URI=qemu:///system
virsh define infra/libvirt/asterisk-deb13.xml
virsh start asterisk-deb13
```

### Small VM OOM During Asterisk Build

`install.sh` defaults to `MAKE_JOBS=$(nproc)`. Use a VM with at least 4 GB RAM, or limit parallelism:

```bash
sudo MAKE_JOBS=2 ./install.sh
sudo ./scripts/setup-transcriber.sh
```

### `verify.sh` And Short Pipelines

Under `set -o pipefail`, commands like `pip show ... | head -1` can fail with `SIGPIPE` even when `pip show` succeeded. `scripts/verify.sh` avoids that pattern; keep future checks similarly direct.

## Agent Context

`AGENTS.md` captures the repo-wide operating rules:

- Keep secrets out of git.
- Treat `asterisk/*.tmpl` as source of truth.
- Use baresip as the local Linux softphone.
- Manage endpoints through `.env`.
- Keep `install.sh` idempotent.

Project skills under `.claude/skills/`:

- add/remove SIP endpoint
- deploy to VM
- debug SIP registration
- rotate SIP passwords

## OpenSIPS SBC

Mode: stateless SIP proxy + RTPengine for media relay. Both daemons on one VM. Topology-hiding B2BUA is out of scope.

### Topology

```
                       libvirt default network (192.168.122.0/24)
                       ─────────────────────────────────────────
host (baresip)            asterisk-deb13-cloudinit       opensips-sbc-deb13-cloudinit
192.168.122.1             ASTERISK_IP                    SBC_IP
   │                            │                              │
   │   SIP UDP 5060             │                              │
   ├───────────────────────────────────────────────────────────►
   │                                                           │
   │                              ◄────────────────────────────┤
   │                                                           │
   │                            Asterisk PJSIP                 OpenSIPS 3.6 LTS
   │                            transport-udp 0.0.0.0:5060     listen udp:SBC_IP:5060
   │                            RTP 10000-10200                rtpengine ctl 127.0.0.1:2223
   │                                                           RTP relay 30000-40000
```

Signaling: `host ⇄ SBC ⇄ Asterisk` on UDP 5060. SBC inserts `Via`, `Record-Route`, and `Path` (for REGISTER).

Media: `host ⇄ SBC(30000-40000) ⇄ Asterisk(10000-10200)` via RTPengine userspace relay.

### VM Provisioning

```bash
DOMAIN=opensips-sbc-deb13-cloudinit \
SSH_PUBKEY_FILE=~/.ssh/id_ed25519.pub \
DISK_SIZE=20G \
MEMORY_GIB=2 \
VCPUS=2 \
./infra/libvirt/create-cloudinit-vm.sh
```

Reference XML: `infra/libvirt/opensips-sbc-deb13-cloudinit.xml`. IP comes from libvirt DHCP.

### Install Flow

`sbc/install.sh` (idempotent):

1. Add `apt.opensips.org` repo and signing key.
2. `apt install opensips opensips-rtpengine-module ngcp-rtpengine-daemon rsyslog`.
   (`rsyslog` is required — Debian 13 minimal image has journald only, and the syslog observation flow needs `/var/log/syslog`.)
3. Render `sbc/opensips.cfg.tmpl` to `/etc/opensips/opensips.cfg` with `envsubst '${SBC_IP} ${ASTERISK_IP}'`. The whitelist is required — a bare `envsubst` destroys OpenSIPS pseudo-variables like `$du`.
4. Render `sbc/rtpengine.conf.tmpl` to `/etc/rtpengine/rtpengine.conf`.
5. Flip `/etc/default/opensips` to `RUN_OPENSIPS=yes` (Debian's ships-off gate).
6. `systemctl enable --now opensips ngcp-rtpengine-daemon`.

Modules loaded: `signaling`, `tm`, `sl`, `rr`, `path`, `proto_udp`, `sipmsgops`, `textops`, `rtpengine`, `mi_fifo`, `maxfwd`.

### Installed files (SBC VM)

```text
OpenSIPS:
  /usr/sbin/opensips                                        daemon binary
  /etc/opensips/opensips.cfg                                rendered config
  /etc/default/opensips                                     env file; RUN_OPENSIPS gate
  /usr/lib/systemd/system/opensips.service                  systemd unit
  /usr/lib/x86_64-linux-gnu/opensips/modules/*.so           built-in modules
  /usr/lib/x86_64-linux-gnu/opensips/modules/rtpengine.so   OpenSIPS↔rtpengine glue
  /run/opensips/opensips_fifo                               MI FIFO (created at runtime)

rtpengine:
  /usr/bin/rtpengine                                        daemon binary
  /etc/rtpengine/rtpengine.conf                             rendered config
  /etc/default/rtpengine-daemon                             env file: CONFIG_FILE, MANAGE_IPTABLES, SET_USER
  /usr/lib/systemd/system/rtpengine-daemon.service          systemd unit (rtpengine.service alias)
```

### OpenSIPS Config

`/etc/opensips/opensips.cfg` skeleton:

```c
socket=udp:${SBC_IP}:5060
log_facility=LOG_LOCAL0

modparam("rtpengine", "rtpengine_sock", "udp:127.0.0.1:2223")
modparam("mi_fifo", "reply_dir", "/run/opensips/")

route {
    if (!mf_process_maxfwd_header(10)) {
        sl_send_reply(483, "Too Many Hops");
        exit;
    }

    if (has_totag()) {
        if (loose_route()) {
            if (is_method("BYE"))         { rtpengine_delete(); }
            else if (is_method("INVITE")) { record_route(); rtpengine_offer(); }
            t_relay();
            exit;
        }
        sl_send_reply(404, "Not here");
        exit;
    }

    if (is_method("REGISTER")) {
        append_hf("Supported: path\r\n");
        add_path_received();
        $du = "sip:${ASTERISK_IP}:5060";
        t_relay();
        exit;
    }

    if (is_method("INVITE")) {
        record_route();
        rtpengine_offer();
        $du = "sip:${ASTERISK_IP}:5060";
        t_relay();
        exit;
    }

    t_relay();
}

onreply_route {
    if (is_method("INVITE")
        && ($rs == 180 || $rs == 183 || $rs == 200)
        && has_body("application/sdp")) {
        rtpengine_answer();
    }
}
```

Required config choices and why:

- `socket=udp:${SBC_IP}:5060` — binding on `0.0.0.0` causes OpenSIPS to advertise `0.0.0.0` in outbound `Via` / `Path` headers, which Asterisk rejects with `420 Bad Extension`.
- `append_hf("Supported: path\r\n")` before `add_path_received()` — baresip does not advertise `Supported: path`, so PJSIP rejects the proxy-inserted `Path:` (RFC 3327 consent check) even with `support_path=yes` on the AOR. The proxy injects consent on the UAC's behalf.
- `onreply_route` gate on `is_method("INVITE") && has_body("application/sdp")` — bodyless replies (REGISTER 200, OPTIONS qualify 200, BYE 200) or non-INVITE replies with SDP (baresip's OPTIONS qualify responses carry SDP) must not call `rtpengine_answer()`. Otherwise syslog fills with `Unknown call-id` errors and real issues get masked.
- Integer literals must not be quoted in OpenSIPS 3.x: `mf_process_maxfwd_header(10)`, `sl_send_reply(483, "…")`.
- Reply status in 3.x is `$rs`; the bare `status` token is not valid.
- MI FIFO reply directory must live under `/run/opensips/` — Linux protected FIFOs in `/tmp` fail when caller and OpenSIPS users differ.

### RTPengine Config

`/etc/rtpengine/rtpengine.conf`:

```ini
[rtpengine]
interface    = ${SBC_IP}
listen-ng    = 127.0.0.1:2223
listen-cli   = 127.0.0.1:9900
port-min     = 30000
port-max     = 40000
table        = -1
log-level    = 6
log-facility = local1
```

`/etc/default/rtpengine-daemon`: `MANAGE_IPTABLES=no`.

- `listen-ng = 127.0.0.1:2223` — Debian package default; matches the OpenSIPS `rtpengine_sock` modparam.
- `listen-cli = 127.0.0.1:9900` — required for `rtpengine-ctl` used by the Zabbix helper.
- `table = -1` and `MANAGE_IPTABLES=no` — forces userspace forwarding. The `rtpengine-kernel-dkms` package is not installed; kernel mode would otherwise emit `FAILED TO CREATE KERNEL TABLE 0` errors on every start.
- `log-facility = local1` — separates from OpenSIPS (`local0`) in `/var/log/syslog`.

### Asterisk-Side Changes

- `asterisk/pjsip-endpoint.conf.tmpl`: `[type=aor]` block has `support_path=yes` so PJSIP stores the `Path:` header from REGISTER. Without it, PJSIP tries to reach the softphone directly via Contact IP, defeating the SBC.
- Everything else unchanged. The `from-softphones` context is unaffected; `${CALLERID(num)}` still resolves to the originating extension. Auth digest is preserved by the stateless proxy.

### Host Softphone (baresip)

`~/.baresip/accounts`:

```text
<sip:1001@${SBC_IP}>;auth_pass=<SIP_EXT_1001_PASSWORD>;transport=udp;regint=3600;answermode=auto;audio_codecs=opus,PCMU,PCMA
<sip:1002@${SBC_IP}>;auth_pass=<SIP_EXT_1002_PASSWORD>;transport=udp;regint=3600;answermode=auto;audio_codecs=opus,PCMU,PCMA
```

Auth password is unchanged from the direct-to-Asterisk case — the SBC is transparent to digest.

### Syslog And Observation

Both daemons write to syslog:

- OpenSIPS: `log_facility=LOG_LOCAL0`
- RTPengine: `log-facility=local1`

`tail -f /var/log/syslog` on the SBC VM shows both streams. Both also appear in `journalctl -u opensips` / `journalctl -u rtpengine-daemon`.

sngrep points during a call:

- Host: `sudo sngrep -d any port 5060` — softphone↔SBC leg
- SBC VM: same command — both legs
- Asterisk VM: same command — SBC↔Asterisk leg

Media verification on the SBC: `sudo tcpdump -i any -n udp portrange 30000-40000` should show two-way RTP during a call.

### Repo Layout Deltas

```text
sbc/
  opensips.cfg.tmpl
  rtpengine.conf.tmpl
  install.sh
  verify.sh
infra/libvirt/
  opensips-sbc-deb13-cloudinit.xml
```

`.env.example` adds:

```text
SBC_IP=
ASTERISK_IP=
```

Both are learned from libvirt DHCP after first boot; update `.env` when the lease changes and re-run `make deploy-sbc`.

Makefile targets:

```text
make install-sbc        ssh to SBC VM, run sbc/install.sh
make verify-sbc         ssh to SBC VM, run sbc/verify.sh
make logs-sbc           ssh to SBC VM, tail -f /var/log/syslog
make deploy-sbc         rsync repo to SBC VM
```

`make install` / `make verify` / `make deploy` remain Asterisk-only.

### verify.sh Checks (SBC)

- `systemctl is-active opensips`
- `systemctl is-active ngcp-rtpengine-daemon`
- `ss -ulnp | grep 2223` — ng control socket up
- `ss -ulnp | grep ${SBC_IP}:5060` — OpenSIPS bound
- MI FIFO reachable via JSON-RPC

### End-To-End Verification

Expected signaling at the SBC sngrep window during REGISTER + call to 600:

```text
REGISTER (host → SBC)
REGISTER (SBC → Asterisk, +Via +Path +Supported:path)
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
... two-way RTP via SBC_IP:30000-40000 ...
BYE  (rtpengine_delete frees the ports)
200 OK
```

Recording paths on the Asterisk VM are unchanged — the SBC is transparent to the dialplan.

### DHCP Address Drift

libvirt's `default` network gives leases from the DHCP pool without persistent reservation. After a VM restart or start-order change, `SBC_IP` and `ASTERISK_IP` can differ from previous runs. When this happens:

1. `virsh -c qemu:///system net-dhcp-leases default` to read current leases.
2. Update `.env` (`SBC_IP`, `ASTERISK_IP`).
3. `make deploy-sbc` re-renders `/etc/opensips/opensips.cfg` and restarts opensips.
4. If Asterisk moved, re-point baresip: `sed -i 's/<old-sbc>/<new-sbc>/g' ~/.baresip/accounts`.

Long-term fix candidate: DHCP host reservations in libvirt's `default` network XML pinning MAC → IP, or render configs from `virsh domifaddr` output at deploy time so IPs are never typed by hand. For the lab we keep the re-render dance explicit — it's a useful demonstration of the SBC ↔ Asterisk coupling.

## Monitoring VM: Zabbix + Grafana

Third VM role:

```text
monitoring-deb13-cloudinit
  PostgreSQL 17
  Zabbix 7.0 LTS server + Apache PHP frontend
  zabbix-agent2
  Grafana 13.1 + alexanderzobnin-zabbix-app 6.4.1

asterisk-deb13-cloudinit
  zabbix-agent2

opensips-sbc-deb13-cloudinit
  zabbix-agent2
  OpenSIPS MI FIFO metric helper
```

Repo files under `monitoring/`:

```text
monitoring/install.sh                       monitoring VM installer
monitoring/setup-zabbix-agent.sh            zabbix-agent2 setup for lab nodes
monitoring/verify.sh                        monitoring VM smoke checks
monitoring/verify-agent.sh                  monitored-node agent checks
monitoring/zabbix-web.conf.php.tmpl         → /etc/zabbix/web/zabbix.conf.php
monitoring/zabbix-agent-lab.conf.tmpl       → /etc/zabbix/zabbix_agent2.d/lab.conf
monitoring/opensips-mi.py                   → /usr/local/bin/opensips-mi-zabbix
monitoring/asterisk-metrics.py              → /usr/local/bin (asterisk -rx wrapper)
monitoring/rtpengine-metrics.sh             → /usr/local/bin (rtpengine-ctl parser)
monitoring/provision-observability.py       creates Zabbix host/items via API
monitoring/grafana-*.yaml/json              datasource + dashboard provisioning
```

Make targets:

```bash
make deploy-monitoring MONITORING_VM=deb@<monitoring-ip>
make deploy-agent-asterisk VM=deb@<asterisk-ip>
make deploy-agent-sbc SBC_VM=deb@<sbc-ip>
make verify-monitoring
make verify-zabbix-agent
```

SSH override for hosts with a broken global SSH config include: `SSH="ssh -F /dev/null"`. The Makefile passes `$(SSH)` to rsync via `RSYNC_SSH ?= $(SSH)`.

### Monitoring env

Monitoring VM `.env`:

```text
MONITORING_IP=
ZABBIX_DB_PASSWORD=
ZABBIX_VERSION=7.0
```

Monitored nodes need at least:

```text
MONITORING_IP=
ZABBIX_VERSION=7.0
```

SBC also needs `SBC_IP` and `ASTERISK_IP` (see DHCP Address Drift above).

### Zabbix frontend fixes baked into installer/template

1. `php-pgsql` is installed (default `php-mysql`-only image shows `DB type "POSTGRESQL" is not supported`).
2. `locale-gen en_US.UTF-8` is run (Debian cloud image ships only `C`, `C.utf8`, `POSIX`).
3. `zabbix-web.conf.php.tmpl` disables Elasticsearch history explicitly:

   ```php
   $HISTORY['url'] = '';
   $HISTORY['types'] = [];
   ```

### OpenSIPS metrics transport

`opensips-cli` / `opensipsctl` are not available in the current APT sources. Metrics use the `mi_fifo` module directly with OpenSIPS 3.6 JSON-RPC syntax:

```text
:reply_fifo:{"jsonrpc":"2.0","method":"get_statistics","id":"...","params":[["all"]]}
```

The legacy line format (`:get_statistics:reply_fifo\nall\n\n`) fails with `mi_fifo_callback: cannot parse command`.

`setup-zabbix-agent.sh` installs `/usr/local/bin/opensips-mi-zabbix`, adds `zabbix` to the `opensips` group, sets `/run/opensips` group-writable, and installs:

```text
d /run/opensips 0775 opensips opensips -
```

Helper creates reply FIFOs under `/run/opensips`, uses a 5 s timeout.

### Zabbix items

Hosts (in Zabbix group `Asterisk Lab`):

```text
opensips-sbc-deb13-cloudinit  → visible name "OpenSIPS SBC"    25 items
asterisk-deb13-cloudinit       → visible name "Asterisk PBX"    9 items
```

OpenSIPS SBC items:

```text
lab.opensips.mi.ping                            MI FIFO reachable (1/0)
lab.opensips.stat[rcv_requests]                 SIP requests received (counter)
lab.opensips.stat[fwd_requests]                 SIP requests forwarded (counter)
lab.opensips.stat[drop_requests]                dropped by script logic
lab.opensips.stat[err_requests]                 script/route errors
lab.opensips.stat[2xx_transactions]             successful call transactions
lab.opensips.stat[4xx_transactions]             auth/route/user failures
lab.opensips.stat[5xx_transactions]             server-side failures
lab.opensips.stat[tm:inuse_transactions]        concurrent SIP tx (≈ concurrent calls)
lab.opensips.stat[tm:UAC_transactions]          OpenSIPS-originated tx
lab.opensips.stat[tm:UAS_transactions]          OpenSIPS-received tx
lab.opensips.stat[tm:timeout_finalresponse_inv] INVITE timed out with no final reply
lab.opensips.stat[core:bad_URIs_rcvd]           malformed Request-URI count
lab.opensips.stat[core:bad_msg_hdr]             malformed SIP headers count
lab.opensips.stat[used_size]                    shared memory in use (bytes)
lab.opensips.stat[free_size]                    shared memory free (bytes)
lab.systemd.active[opensips]                    service up (1/0)
lab.systemd.active[rtpengine-daemon]            service up (1/0)
lab.rtpengine[ping]                             rtpengine CLI reachable (1/0)
lab.rtpengine[sessions_current]                 active RTP sessions (gauge)
lab.rtpengine[sessions_total]                   total sessions since start
lab.rtpengine[packets]                          cumulative relayed RTP packets
lab.rtpengine[bytes]                            cumulative relayed RTP bytes
lab.rtpengine[errors]                           cumulative relay errors
lab.rtpengine[timeouts]                         cumulative RTP-inactivity timeouts
```

Asterisk PBX items:

```text
lab.systemd.active[asterisk]                    service up (1/0)
lab.systemd.active[transcriber]                 transcriber up (1/0)
lab.asterisk[channels]                          active PJSIP channels (gauge)
lab.asterisk[calls_active]                      active calls (gauge)
lab.asterisk[calls_processed]                   cumulative calls since boot
lab.asterisk[endpoints_total]                   PJSIP contacts registered
lab.asterisk[endpoints_available]               contacts with Status=Avail
lab.asterisk[recordings_count]                  .wav files in spool
lab.asterisk[recordings_bytes]                  spool size in bytes
```

Counters are process counters and reset when the target daemon restarts.

### Privileged data access

`asterisk -rx` needs write access to `/var/run/asterisk/asterisk.ctl`. `setup-zabbix-agent.sh` installs:

```text
/etc/sudoers.d/zabbix-asterisk
    zabbix ALL=(root) NOPASSWD: /usr/sbin/asterisk -rx *
```

The Zabbix UserParameter invokes `sudo -n /usr/sbin/asterisk -rx <command>`, parsed by `monitoring/asterisk-metrics.py`.

`rtpengine-ctl` uses `-ip 127.0.0.1:9900`; `setup-zabbix-agent.sh` patches an existing `/etc/rtpengine/rtpengine.conf` if `listen-cli` is missing. `list totals` output feeds `sessions_current` (from the "currently running sessions" block) and `packets`/`bytes`/`errors` (last occurrence per label under "Total statistics", userspace+kernel sum).

### Zabbix API notes

- `item.update` rejects `hostid`. Provisioner strips `hostid` and `key_` from update payloads while `item.create` keeps both.
- `item.get` with `filter.key_` is the reliable existence check; matching on `name` is unreliable (names get hand-edited).

### Grafana

Plugin: `alexanderzobnin-zabbix-app @ 6.4.1`. Datasource type `alexanderzobnin-zabbix-datasource`.

File provisioning:

```text
/etc/grafana/provisioning/datasources/zabbix.yaml
/etc/grafana/provisioning/dashboards/asterisk-lab.yaml
/var/lib/grafana/dashboards/asterisk-lab/opensips-sbc-overview.json
/var/lib/grafana/dashboards/asterisk-lab/asterisk-pbx-overview.json
```

Dashboards:

```text
http://<MONITORING_IP>:3000/d/opensips-sbc-overview/opensips-sbc-overview
http://<MONITORING_IP>:3000/d/asterisk-pbx-overview/asterisk-pbx-overview
```

opensips-sbc-overview panels: MI status, active RTP sessions, in-use SIP transactions, SIP request counters, transactions by response class, rtpengine traffic delta + errors, call setup issues (INVITE timeouts, RTP timeouts, bad URIs / headers), OpenSIPS shared memory used/free.

asterisk-pbx-overview panels: Asterisk + transcriber service status, active channels, registered endpoints (avail vs total), concurrent channels + calls, calls processed cumulative, recording spool bytes + file count.

Grafana admin password is not stored in the repo — set at first login.

### Verification targets

Known-good on a clean lab:

```text
monitoring/verify.sh on monitoring VM:  20/20 OK
monitoring/verify-agent.sh on SBC:       7/7 OK
sbc/verify.sh on SBC:                   11/11 OK
```
