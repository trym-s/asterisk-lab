#!/usr/bin/env bash
# Bootstrap libvirt on the host so the asterisk VM can run under it.
# Run ONCE per host. Idempotent.
#
# This script does NOT install packages — install the prerequisites listed
# in the project README first (libvirt, qemu, dnsmasq, virtinst).
#
# After this completes, drop a Debian 13 qcow2 named asterisk-deb13.qcow2
# into /var/lib/libvirt/images/, then:
#   virsh define infra/libvirt/asterisk-deb13.xml
#   virsh start  asterisk-deb13
set -euo pipefail

err()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
step() { printf '\n==> %s\n' "$*"; }

# Preflight: required binaries (install via your distro's package manager)
missing=()
for bin in virsh modprobe systemctl usermod; do
  command -v "$bin" >/dev/null || missing+=("$bin")
done
[ ${#missing[@]} -eq 0 ] \
  || err "missing binaries: ${missing[*]}. See README 'Host dependencies'."

# Refuse to run if the kernel was upgraded without a reboot — modprobe
# would otherwise fail silently for sch_htb (rolling distros: Arch, etc).
[ -d "/lib/modules/$(uname -r)" ] \
  || err "running kernel $(uname -r) has no module tree; reboot and re-run"

step "loading sch_htb (libvirt installs an HTB qdisc on virbr0)"
sudo modprobe sch_htb
echo 'sch_htb' | sudo tee /etc/modules-load.d/sch_htb.conf >/dev/null

step "enabling libvirtd"
sudo systemctl enable --now libvirtd.socket libvirtd.service

if ! id -nG "$USER" | tr ' ' '\n' | grep -qx libvirt; then
  sudo usermod -aG libvirt "$USER"
  echo "  added $USER to libvirt group — log out and back in for it to apply"
fi

step "starting default NAT network"
sudo virsh net-start default 2>/dev/null || echo "  default network already active"
sudo virsh net-autostart default

step "ensuring default storage pool at /var/lib/libvirt/images"
if ! sudo virsh pool-info default >/dev/null 2>&1; then
  sudo virsh pool-define-as default dir --target /var/lib/libvirt/images
  sudo virsh pool-build      default
  sudo virsh pool-start      default
  sudo virsh pool-autostart  default
else
  echo "  default storage pool already exists"
fi

cat <<EOF

done. before running the VM:
  export LIBVIRT_DEFAULT_URI=qemu:///system   # add to your shell rc

then:
  sudo cp <your-debian13.qcow2> /var/lib/libvirt/images/asterisk-deb13.qcow2
  virsh define $(dirname "$0")/asterisk-deb13.xml
  virsh start  asterisk-deb13
  virsh net-dhcp-leases default               # get the VM's IP
EOF
