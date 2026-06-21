
## Environment

| Component | Value |
|---|---|
| Host OS | Arch Linux (rolling), kernel 7.0.12-arch1-1 |
| Host network | WiFi `wlp4s0`, 192.168.1.0/24 |
| Hypervisor | libvirt + QEMU/KVM |
| Host-side virtual net | libvirt `default` (NAT) → `virbr0` 192.168.122.1/24, internal dnsmasq for DHCP |
| Guest OS | Debian 13 (trixie) |
| Guest VM name | `asterisk-deb13` |
| Asterisk version | 22.9.0 (built from source, tag `22.9.0`) |
| Softphone | baresip on the Arch host |

---

## Architectural decisions

### Use libvirt for host-side virt instead of raw QEMU + `hostfwd`

Started with `qemu-system-x86_64 -nic user,hostfwd=tcp::2222-:22 ...`. Functional, but to make SIP/RTP work it would need 20+ `hostfwd=` entries hardcoded to specific UDP ports, references to interface names like `wlp4s0`, and PJSIP NAT workarounds (`external_media_address` etc.). Result is bespoke to one laptop and not reproducible.

Tried manual bridged networking next. WiFi clients cannot participate in a Linux bridge (802.11 disallows it), and Ethernet isn't available on the host.

Settled on libvirt's `default` NAT network. Provides the same host-only-NAT topology declaratively, ships on every distro, and the domain XML can use storage-pool volume references rather than absolute paths — so the same XML works on any host.

### Pin Asterisk to tag `22.9.0`, not branch `22`

A pinned tag is reproducible. A branch checkout drifts as upstream pushes maintenance commits. Trade-off: we don't get automatic security patches; we'd update the pin deliberately.

### Use baresip, not MicroSIP

MicroSIP is Windows-only. Available paths:
- MicroSIP under Wine → extra failure dimension (Wine networking, audio).
- Run a Windows VM just for MicroSIP → heavyweight.
- Use a Linux-native softphone such as baresip → SIP is RFC-standard, server-side config is identical.

Chose baresip on the Arch host for development. The lab now treats baresip as the expected local client.

### Commands (run inside the VM)

1. **Source build, version 22.9.0**

   ```bash
   cd ~/asterisk
   sudo make uninstall-all       # remove the earlier master install
   git fetch --all --tags
   git checkout 22.9.0
   make clean
   ./configure
   make -j$(nproc)
   sudo make install
   sudo make samples
   ```

2. **System user**

   ```bash
   sudo groupadd -r asterisk
   sudo useradd  -r -g asterisk \
     -d /var/lib/asterisk \
     -s /usr/sbin/nologin \
     -c "Asterisk PBX" asterisk
   ```

3. **Ownership**

   ```bash
   sudo chown -R asterisk:asterisk /etc/asterisk \
                                   /var/lib/asterisk \
                                   /var/spool/asterisk \
                                   /var/log/asterisk
   ```

4. **systemd unit** at `/etc/systemd/system/asterisk.service`

   ```ini
   [Unit]
   Description=Asterisk PBX
   Documentation=man:asterisk(8)
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   User=asterisk
   Group=asterisk
   RuntimeDirectory=asterisk
   ExecStart=/usr/sbin/asterisk -f -C /etc/asterisk/asterisk.conf
   ExecReload=/usr/sbin/asterisk -rx "core reload"
   Restart=on-failure
   RestartSec=2
   LimitNOFILE=8192
   LimitNPROC=8192

   [Install]
   WantedBy=multi-user.target
   ```

5. **Enable + start**

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now asterisk
   ```

6. **Verify**

   ```bash
   sudo systemctl status asterisk
   sudo journalctl -u asterisk -n 50 --no-pager
   sudo asterisk -rx 'core show version'
   ```

   Expected:
   - `Active: active (running)`
   - `Asterisk Ready.` line near end of journal
   - `Asterisk 22.9.0 built by ...`

---

### Commands (run on the Arch host)

1. **Install libvirt stack**
   ```bash
   sudo pacman -S --needed libvirt qemu-base dnsmasq iptables-nft virt-install
   sudo systemctl enable --now libvirtd.socket libvirtd.service
   sudo usermod -aG libvirt "$USER"
   newgrp libvirt
   ```

2. **Start the default NAT network** (already shipped predefined)
   ```bash
   sudo virsh net-start default
   sudo virsh net-autostart default
   ```

3. **Define the default storage pool** (not predefined — must be created)
   ```bash
   sudo virsh pool-define-as default dir --target /var/lib/libvirt/images
   sudo virsh pool-build default
   sudo virsh pool-start default
   sudo virsh pool-autostart default
   ```

4. **Move the existing qcow2 into the pool**
   ```bash
   sudo mv /home/vlhnac/local_dev/virtualisation/vms/debian/debian13.qcow2 \
           /var/lib/libvirt/images/asterisk-deb13.qcow2
   sudo chown root:root /var/lib/libvirt/images/asterisk-deb13.qcow2
   sudo chmod 0644 /var/lib/libvirt/images/asterisk-deb13.qcow2
   sudo virsh pool-refresh default
   sudo virsh vol-list default
   ```

5. **Domain XML** at `infra/libvirt/asterisk-deb13.xml` — uses `<source pool='default' volume='asterisk-deb13.qcow2'/>` (no hardcoded paths), `<cpu mode='host-passthrough'/>`, virtio NIC on the `default` network, serial console + VNC.

6. **Define + start**
   ```bash
   export LIBVIRT_DEFAULT_URI=qemu:///system     # critical — see P4 below
   virsh define infra/libvirt/asterisk-deb13.xml
   virsh start  asterisk-deb13
   ```

7. **Find the VM IP**
   ```bash
   sudo virsh net-dhcp-leases default
   #  Expiry Time           MAC                  Protocol  IP                 Hostname
   #  2026-06-16 20:16:34   52:54:00:a8:33:e6    ipv4      192.168.122.20/24  debian
   ```

8. **SSH in over the new bridged path** (no port forwarding)
   ```bash
   ssh deb@192.168.122.20
   ```

### Problems encountered
#### P4. `virsh` defaults to `qemu:///session`, hiding system-level resources

- **Symptom**: `virsh define ~/.../asterisk-deb13.xml` succeeded without sudo, but `virsh start asterisk-deb13` failed with `Storage pool not found: no storage pool with matching name 'default'`. Meanwhile `sudo virsh pool-list --all` clearly showed the pool was present and active.
- **Cause**: `virsh` without `sudo` connects to `qemu:///session` — a per-user libvirt context with its own (empty) set of pools, networks, and domains. `sudo virsh` connects to `qemu:///system` — the system-wide context where our pool and network live. The domain was defined in the session context; the disk it references lives only in the system context.
- **Fix**:
  ```bash
  # Remove the misplaced session-mode definition
  virsh --connect qemu:///session undefine asterisk-deb13

  # Set the default URI so plain virsh hits system mode
  export LIBVIRT_DEFAULT_URI=qemu:///system

  # Define + start in system mode (works without sudo because we're in the libvirt group)
  virsh define ~/local_dev/asterisk/infra/libvirt/asterisk-deb13.xml
  virsh start  asterisk-deb13
  ```
### Softphone deviation: baresip instead of Linphone


### Configs written (inside the VM)

**`/etc/asterisk/pjsip.conf`** :

```ini
[transport-udp]
type=transport
protocol=udp
bind=0.0.0.0:5060

[1001]
type=endpoint
context=from-softphones
disallow=all
allow=ulaw,alaw,opus
auth=1001
aors=1001
direct_media=no

[1001]
type=aor
max_contacts=1
remove_existing=yes

[1001]
type=auth
auth_type=userpass
username=1001
password=<redacted, rendered from SIP_EXT_1001_PASSWORD>
```

**`/etc/asterisk/rtp.conf`**:

```ini
[general]
rtpstart=10000
rtpend=10200
```

Both files chowned to `asterisk:asterisk`. Reloaded with `pjsip reload` + `module reload res_rtp_asterisk.so` (no daemon restart needed).

### Softphone config (on the host)

`~/.baresip/accounts`:

```
<sip:1001@192.168.122.20>;auth_pass=<SIP_EXT_1001_PASSWORD>;transport=udp;regint=3600;answermode=auto;audio_codecs=opus,PCMU,PCMA
```

Launched with `baresip`. SIP REGISTER → 401 → REGISTER(auth) → 200 OK in <1ms. Asterisk side:

```
Endpoint:  1001                                                 Not in use    0 of inf
   InAuth: 1001/1001
      Aor: 1001                                                 1
  Contact:  1001/sip:1001@192.168.122.1:50594  7700c0d9b5 NonQual  -nan
```

## Phase C+ — NOT STARTED

| Phase | Scope | Status |
|---|---|---|
| C | sngrep capture of REGISTER/401/REGISTER/200 + INVITE/TRYING/RINGING/OK/ACK/BYE | pending |
| D | `extensions.conf` dialplan with `MixMonitor` recording to `/var/spool/asterisk/monitor/` | implemented in repo, pending VM verification |
| E | Local-Whisper transcription via systemd `transcriber` watcher, output to `<recording>.txt` next to the WAV. | implemented in repo, verified on VM |
| F | Init git repo. Install scripts targeting fresh Debian 13. README + `docs/troubleshooting.md`. `AGENTS.md`. `.env.example`. Optional libvirt host bootstrap. | pending |

## Phase E — transcription implementation

`scripts/watcher.py` runs as the `transcriber` systemd unit on the box. It loads an `openai-whisper` model once (default `base`), polls `/var/spool/asterisk/monitor/` every 2 s, and writes `<recording>.txt` next to each `<recording>.wav` it sees. `scripts/transcribe.py` is the one-shot equivalent for manual runs. The venv lives at `/opt/transcriber/venv`, the app at `/opt/transcriber/`, and the model cache at `/var/lib/asterisk/.cache/whisper/`. `scripts/setup-transcriber.sh` provisions all of this idempotently.

## Current verification snapshot

Checked `deb@192.168.122.20` on 2026-06-21:

```text
hostname: debian
asterisk service: active
asterisk version: 22.9.0
pjsip endpoint 1001: present, currently Unavailable
from-softphones dialplan: missing on VM before re-running the updated repo install
```

---

## Current file layout

```
~/local_dev/asterisk/
├── PROCESS.md                              ← this file
├── todos.txt                               ← original task list (Turkish)
└── infra/
    └── libvirt/
        └── asterisk-deb13.xml              ← (pending) domain XML

~/local_dev/virtualisation/                 ← was qcow2 location; now empty
                                              (the directory itself may be removed)

/var/lib/libvirt/images/
└── asterisk-deb13.qcow2                    ← VM disk (was debian13.qcow2)
```

Inside the VM (Debian 13):

```
/etc/asterisk/                              ← 22.9.0 sample configs, asterisk-owned
/etc/systemd/system/asterisk.service        ← our unit file
/usr/sbin/asterisk                          ← installed binary, v22.9.0
/var/lib/asterisk/                          ← sounds, AGI, keys (asterisk-owned)
/var/spool/asterisk/monitor/                ← will receive recordings in Phase D
~/asterisk/                                 ← source tree, git tag 22.9.0
```

---
