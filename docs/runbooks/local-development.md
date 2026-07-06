# Local Development

The lab is designed to be reproduced on fresh VMs. Local iteration on the
host is limited to editing templates, scripts, docs, and specs; runtime
lives on the VMs.

## Setup

```bash
git clone <this-repo> asterisk-lab
cd asterisk-lab
git config core.hooksPath .githooks

# Bring up VMs via libvirt (optional but reproducible)
./infra/libvirt/setup-host.sh
./infra/libvirt/create-cloudinit-vm.sh

# Read the current DHCP leases and populate /etc/asterisk-lab/env on each VM
virsh -c qemu:///system net-dhcp-leases default
```

## Daily loop

```bash
# On the Asterisk VM (after creating /etc/asterisk-lab/env):
make install       # builds Asterisk + provisions transcriber
make verify        # smoke-checks: 10 declarative checks, exits non-zero on first fail

# Deploy edits from the host to /opt/asterisk-lab/current on the Asterisk VM
make deploy VM=deb@<asterisk-vm-ip>

# SBC VM
make install-sbc
make verify-sbc
make deploy-sbc SBC_VM=deb@<sbc-vm-ip>

# Monitoring VM
make install-monitoring
make verify-monitoring
make deploy-monitoring MONITORING_VM=deb@<monitoring-vm-ip>

# Voicebot lanes on the Asterisk VM
make install-voicebot-livekit
make install-voicebot-pipecat
make logs-voicebot-livekit
make logs-voicebot-pipecat

# Follow logs during debugging
make logs
make logs-sbc
```

## Rules

- `/etc/asterisk-lab/env` on each VM is host-local. Never commit it. Never
  rsync it. Repo-local `.env` is only a host fallback.
- `/opt/asterisk-lab/current` on each VM is disposable rsync payload, not a
  source repository.
- Rendered configs in `/etc/asterisk`, `/etc/opensips`, `/etc/rtpengine`,
  `/etc/zabbix`, and Grafana provisioning state are outputs of the
  installers; edit the templates in this repo instead.
- The installers are idempotent; rerun them after every template edit.
