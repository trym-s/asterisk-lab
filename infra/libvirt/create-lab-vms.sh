#!/usr/bin/env bash
# One-shot lab bring-up: host bootstrap, then all three cloud-init VMs
# (Asterisk, SBC, monitoring) in sequence, then an SSH reachability check
# with a DHCP-lease-IP summary table.
#
# Idempotent: setup-host.sh and create-cloudinit-vm.sh each skip already
# -provisioned pieces, so re-running this script is safe (it will start any
# VM that is shut off and just re-check the ones that are already running).
#
# Run with sudo (libvirt system connection + optional host bootstrap need
# root):
#   sudo ./infra/libvirt/create-lab-vms.sh
#
# Only VM *creation* and SSH reachability are checked here. Secrets
# (/etc/asterisk-lab/env) and make install/verify on each VM are a separate,
# deliberate manual step — see docs/runbooks/local-development.md.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LIBVIRT_DIR="$REPO_ROOT/infra/libvirt"

err()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
step() { printf '\n==> %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || err "run with sudo: sudo $0"

# sudo resets HOME to /root; resolve the invoking user's pubkey/home unless
# the caller already overrode them.
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"
SSH_PUBKEY_FILE="${SSH_PUBKEY_FILE:-$REAL_HOME/.ssh/id_ed25519.pub}"
SSH_PRIVKEY_FILE="${SSH_PUBKEY_FILE%.pub}"
VM_USER="${VM_USER:-deb}"
export SSH_PUBKEY_FILE VM_USER

[ -r "$SSH_PUBKEY_FILE" ] || err "SSH public key not readable: $SSH_PUBKEY_FILE (set SSH_PUBKEY_FILE=...)"

ASTERISK_DOMAIN="${ASTERISK_DOMAIN:-asterisk-deb13-cloudinit}"
SBC_DOMAIN="${SBC_DOMAIN:-opensips-sbc-deb13-cloudinit}"
MONITORING_DOMAIN="${MONITORING_DOMAIN:-monitoring-deb13-cloudinit}"

step "host bootstrap (libvirt, KVM, default network/pool)"
"$LIBVIRT_DIR/setup-host.sh"

step "creating/starting $ASTERISK_DOMAIN (${ASTERISK_MEMORY_GIB:-4} GiB / ${ASTERISK_VCPUS:-4} vcpu / ${ASTERISK_DISK_SIZE:-30G})"
DOMAIN="$ASTERISK_DOMAIN" DISK_SIZE="${ASTERISK_DISK_SIZE:-30G}" \
  MEMORY_GIB="${ASTERISK_MEMORY_GIB:-4}" VCPUS="${ASTERISK_VCPUS:-4}" \
  "$LIBVIRT_DIR/create-cloudinit-vm.sh"

step "creating/starting $SBC_DOMAIN (${SBC_MEMORY_GIB:-2} GiB / ${SBC_VCPUS:-2} vcpu / ${SBC_DISK_SIZE:-20G})"
DOMAIN="$SBC_DOMAIN" DISK_SIZE="${SBC_DISK_SIZE:-20G}" \
  MEMORY_GIB="${SBC_MEMORY_GIB:-2}" VCPUS="${SBC_VCPUS:-2}" \
  "$LIBVIRT_DIR/create-cloudinit-vm.sh"

step "creating/starting $MONITORING_DOMAIN (${MONITORING_MEMORY_GIB:-4} GiB / ${MONITORING_VCPUS:-2} vcpu / ${MONITORING_DISK_SIZE:-40G})"
DOMAIN="$MONITORING_DOMAIN" DISK_SIZE="${MONITORING_DISK_SIZE:-40G}" \
  MEMORY_GIB="${MONITORING_MEMORY_GIB:-4}" VCPUS="${MONITORING_VCPUS:-2}" \
  "$LIBVIRT_DIR/create-cloudinit-vm.sh"

VIRSH=(virsh -c qemu:///system)

lease_ip() {
  "${VIRSH[@]}" domifaddr "$1" --source lease 2>/dev/null \
    | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | head -1
}

check_ssh() {
  ssh -i "$SSH_PRIVKEY_FILE" -o BatchMode=yes -o ConnectTimeout=5 \
    -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=accept-new \
    "$VM_USER@$1" 'echo ok' >/dev/null 2>&1
}

step "waiting for DHCP leases and checking SSH reachability"
printf '\n%-32s %-16s %-12s\n' "DOMAIN" "IP" "SSH"
overall_ok=0
for domain in "$ASTERISK_DOMAIN" "$SBC_DOMAIN" "$MONITORING_DOMAIN"; do
  ip=""
  deadline=$(( $(date +%s) + 90 ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    ip="$(lease_ip "$domain")"
    [ -n "$ip" ] && break
    sleep 3
  done

  if [ -z "$ip" ]; then
    printf '%-32s %-16s %-12s\n' "$domain" "-" "NO-LEASE"
    overall_ok=1
    continue
  fi

  ssh_deadline=$(( $(date +%s) + 60 ))
  ssh_ok=1
  while [ "$(date +%s)" -lt "$ssh_deadline" ]; do
    if check_ssh "$ip"; then
      ssh_ok=0
      break
    fi
    sleep 3
  done

  if [ "$ssh_ok" -eq 0 ]; then
    printf '%-32s %-16s %-12s\n' "$domain" "$ip" "OK"
  else
    printf '%-32s %-16s %-12s\n' "$domain" "$ip" "UNREACHABLE"
    overall_ok=1
  fi
done

[ "$overall_ok" -eq 0 ] \
  || err "one or more VMs failed the SSH reachability check (see table above)"

cat <<EOF

All three VMs are up and SSH-reachable as '$VM_USER'.

Next (secrets are never rsynced - see docs/runbooks/local-development.md):
  1. Place /etc/asterisk-lab/env on each VM (SIP_EXTENSIONS + passwords on
     Asterisk; SBC_IP + ASTERISK_IP on the SBC; MONITORING_IP +
     ZABBIX_DB_PASSWORD on monitoring).
  2. make deploy             VM=deb@<asterisk-ip>
  3. make deploy-sbc          SBC_VM=deb@<sbc-ip>
  4. make deploy-monitoring   MONITORING_VM=deb@<monitoring-ip>
  5. make verify / make verify-sbc / make verify-monitoring on each VM.
EOF
