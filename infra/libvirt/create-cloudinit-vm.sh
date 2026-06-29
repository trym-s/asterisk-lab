#!/usr/bin/env bash
# Create a fresh, SSH-ready Debian 13 VM under libvirt using the official
# Debian genericcloud image plus a NoCloud cloud-init seed ISO.
set -euo pipefail

DOMAIN="${DOMAIN:-asterisk-deb13-cloudinit}"
POOL="${POOL:-default}"
VM_USER="${VM_USER:-deb}"
SSH_PUBKEY_FILE="${SSH_PUBKEY_FILE:-$HOME/.ssh/id_ed25519.pub}"
DISK_SIZE="${DISK_SIZE:-30G}"
MEMORY_GIB="${MEMORY_GIB:-4}"
VCPUS="${VCPUS:-4}"
WORKDIR="${WORKDIR:-/var/tmp/asterisk-lab-cloudinit}"
BASE_IMAGE_URL="${BASE_IMAGE_URL:-https://cloud.debian.org/images/cloud/trixie/latest/debian-13-genericcloud-amd64.qcow2}"

DISK_VOL="${DOMAIN}.qcow2"
SEED_VOL="${DOMAIN}-seed.iso"
BASE_IMAGE="$WORKDIR/debian-13-genericcloud-amd64.qcow2"
VM_IMAGE="$WORKDIR/$DISK_VOL"
SEED_DIR="$WORKDIR/seed"
SEED_ISO="$WORKDIR/$SEED_VOL"
DOMAIN_XML="$WORKDIR/$DOMAIN.xml"

err() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
step() { printf '\n==> %s\n' "$*"; }

need() {
  command -v "$1" >/dev/null 2>&1 || err "missing '$1'"
}

need curl
need qemu-img
need cloud-localds
need virsh
need stat

[ -r "$SSH_PUBKEY_FILE" ] || err "SSH public key not readable: $SSH_PUBKEY_FILE"

VIRSH=(virsh -c qemu:///system)

if "${VIRSH[@]}" dominfo "$DOMAIN" >/dev/null 2>&1; then
  state=$("${VIRSH[@]}" domstate "$DOMAIN" 2>/dev/null || true)
  if [ "$state" = "shut off" ]; then
    step "domain $DOMAIN already exists; starting it"
    "${VIRSH[@]}" start "$DOMAIN"
  else
    step "domain $DOMAIN already exists and is $state"
  fi
  "${VIRSH[@]}" domifaddr "$DOMAIN" --source lease || true
  exit 0
fi

step "checking libvirt pool '$POOL'"
"${VIRSH[@]}" pool-info "$POOL" >/dev/null

step "preparing cloud image in $WORKDIR"
mkdir -p "$WORKDIR" "$SEED_DIR"
[ -s "$BASE_IMAGE" ] || curl -L --fail --output "$BASE_IMAGE" "$BASE_IMAGE_URL"
qemu-img convert -O qcow2 "$BASE_IMAGE" "$VM_IMAGE"
qemu-img resize "$VM_IMAGE" "$DISK_SIZE"

step "creating cloud-init seed for user '$VM_USER'"
pubkey=$(cat "$SSH_PUBKEY_FILE")
cat > "$SEED_DIR/user-data" <<EOF
#cloud-config
hostname: $DOMAIN
manage_etc_hosts: true
ssh_pwauth: false
disable_root: true
package_update: true
packages:
  - rsync
users:
  - default
  - name: $VM_USER
    gecos: Asterisk Lab User
    groups: [sudo]
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    lock_passwd: true
    ssh_authorized_keys:
      - $pubkey
runcmd:
  - systemctl enable --now ssh || systemctl enable --now sshd || true
EOF

cat > "$SEED_DIR/meta-data" <<EOF
instance-id: ${DOMAIN}-001
local-hostname: $DOMAIN
EOF

cloud-localds "$SEED_ISO" "$SEED_DIR/user-data" "$SEED_DIR/meta-data"

create_volume() {
  local volume="$1"
  local file="$2"
  local format="$3"
  local size
  size=$(stat -c '%s' "$file")

  if "${VIRSH[@]}" vol-info --pool "$POOL" "$volume" >/dev/null 2>&1; then
    err "volume already exists: $volume. Delete it or choose DOMAIN=<new-name>."
  fi

  "${VIRSH[@]}" vol-create-as "$POOL" "$volume" "$size" --format "$format"
  "${VIRSH[@]}" vol-upload --pool "$POOL" "$volume" "$file"
}

step "uploading independent libvirt volumes"
create_volume "$DISK_VOL" "$VM_IMAGE" qcow2
create_volume "$SEED_VOL" "$SEED_ISO" raw

step "rendering libvirt XML"
cat > "$DOMAIN_XML" <<EOF
<domain type='kvm'>
  <name>$DOMAIN</name>
  <memory unit='GiB'>$MEMORY_GIB</memory>
  <vcpu>$VCPUS</vcpu>

  <os>
    <type arch='x86_64' machine='q35'>hvm</type>
    <boot dev='hd'/>
  </os>

  <features>
    <acpi/>
    <apic/>
  </features>

  <cpu mode='host-passthrough'/>

  <clock offset='utc'>
    <timer name='rtc' tickpolicy='catchup'/>
    <timer name='hpet' present='no'/>
  </clock>

  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>

  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>

    <disk type='volume' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source pool='$POOL' volume='$DISK_VOL'/>
      <target dev='vda' bus='virtio'/>
    </disk>

    <disk type='volume' device='cdrom'>
      <driver name='qemu' type='raw'/>
      <source pool='$POOL' volume='$SEED_VOL'/>
      <target dev='sda' bus='sata'/>
      <readonly/>
    </disk>

    <interface type='network'>
      <source network='default'/>
      <model type='virtio'/>
    </interface>

    <serial type='pty'><target port='0'/></serial>
    <console type='pty'><target type='serial' port='0'/></console>

    <graphics type='vnc' port='-1' autoport='yes' listen='127.0.0.1'/>
  </devices>
</domain>
EOF

step "defining and starting $DOMAIN"
"${VIRSH[@]}" define "$DOMAIN_XML"
"${VIRSH[@]}" start "$DOMAIN"

step "waiting briefly for DHCP lease"
sleep 8
"${VIRSH[@]}" domifaddr "$DOMAIN" --source lease || true

cat <<EOF

done. When an address appears above, SSH in with:
  ssh $VM_USER@<vm-ip>

Then follow the repo quick start inside the VM.
EOF
