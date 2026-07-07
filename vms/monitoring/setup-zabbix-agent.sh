#!/usr/bin/env bash
# Install and configure zabbix-agent2 on any lab node.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# shellcheck source=/dev/null
. "$REPO_ROOT/infra/scripts/lib/env.sh"
load_lab_env "$REPO_ROOT"
: "${MONITORING_IP:?MONITORING_IP not set; add it to the lab env file or pass MONITORING_IP=<ip>}"
: "${ZABBIX_VERSION:=7.0}"
: "${ZABBIX_HOSTNAME:=$(hostname -f 2>/dev/null || hostname)}"

SUDO=sudo
$SUDO -v 2>/dev/null || true

# shellcheck source=/dev/null
. /etc/os-release
case "${ID:-}" in debian|ubuntu) ;; *) echo "unsupported distro: ${ID:-?}" >&2; exit 1;; esac
case "${VERSION_ID:-}" in
  13|13.*) ZABBIX_DEBIAN_MAJOR=13 ;;
  12|12.*) ZABBIX_DEBIAN_MAJOR=12 ;;
  *) echo "unsupported Debian/Ubuntu VERSION_ID for this lab: ${VERSION_ID:-?}" >&2; exit 1 ;;
esac

echo "==> Zabbix ${ZABBIX_VERSION} apt repository"
ZABBIX_RELEASE="zabbix-release_latest_${ZABBIX_VERSION}+debian${ZABBIX_DEBIAN_MAJOR}_all.deb"
ZABBIX_RELEASE_URL="https://repo.zabbix.com/zabbix/${ZABBIX_VERSION}/debian/pool/main/z/zabbix-release/${ZABBIX_RELEASE}"
if [ ! -f /etc/apt/sources.list.d/zabbix.list ] || ! grep -q "repo.zabbix.com/zabbix/${ZABBIX_VERSION}" /etc/apt/sources.list.d/zabbix.list; then
  tmp_deb="/tmp/${ZABBIX_RELEASE}"
  curl -fsSL "$ZABBIX_RELEASE_URL" -o "$tmp_deb"
  $SUDO dpkg -i "$tmp_deb"
  $SUDO apt-get update -qq
fi

echo "==> zabbix-agent2"
DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y --no-install-recommends \
  ca-certificates curl python3 zabbix-agent2

set_agent_conf() {
  local key="$1" value="$2" file="$3"
  local escaped
  escaped=$(printf "%s" "$value" | sed 's/[\/&]/\\&/g')
  if grep -qE "^#?${key}=" "$file"; then
    $SUDO sed -i "s/^#\\?${key}=.*/${key}=${escaped}/" "$file"
  else
    printf '%s=%s\n' "$key" "$value" | $SUDO tee -a "$file" >/dev/null
  fi
}

agent_conf=/etc/zabbix/zabbix_agent2.conf
$SUDO cp "$agent_conf" "${agent_conf}.bak"
set_agent_conf Server "127.0.0.1,${MONITORING_IP}" "$agent_conf"
set_agent_conf ServerActive "$MONITORING_IP" "$agent_conf"
set_agent_conf Hostname "$ZABBIX_HOSTNAME" "$agent_conf"

$SUDO install -d -m 0755 /etc/zabbix/zabbix_agent2.d
$SUDO install -m 0755 vms/monitoring/usr/local/bin/opensips-mi-zabbix /usr/local/bin/opensips-mi-zabbix
$SUDO install -m 0755 vms/monitoring/usr/local/bin/asterisk-metrics /usr/local/bin/asterisk-metrics
$SUDO install -m 0755 vms/monitoring/usr/local/bin/rtpengine-metrics /usr/local/bin/rtpengine-metrics
# shellcheck disable=SC2016
envsubst '${MONITORING_IP} ${ZABBIX_HOSTNAME}' \
  < vms/monitoring/etc/zabbix/zabbix_agent2.d/lab.conf.tmpl \
  | $SUDO tee /etc/zabbix/zabbix_agent2.d/lab.conf >/dev/null
$SUDO chmod 0644 /etc/zabbix/zabbix_agent2.d/lab.conf

if [ -d /run/opensips ] && getent group opensips >/dev/null 2>&1; then
  $SUDO usermod -aG opensips zabbix
  $SUDO chgrp opensips /run/opensips
  $SUDO chmod 0775 /run/opensips
  echo 'd /run/opensips 0775 opensips opensips -' \
    | $SUDO tee /etc/tmpfiles.d/opensips-mi-zabbix.conf >/dev/null
fi

# Asterisk CLI needs write access to /var/run/asterisk/asterisk.ctl. The
# simplest path that does not touch /etc/asterisk/asterisk.conf is to let the
# zabbix user run `asterisk -rx` via sudo without a password.
if [ -x /usr/sbin/asterisk ]; then
  echo 'zabbix ALL=(root) NOPASSWD: /usr/sbin/asterisk -rx *' \
    | $SUDO tee /etc/sudoers.d/zabbix-asterisk >/dev/null
  $SUDO chmod 0440 /etc/sudoers.d/zabbix-asterisk
fi

# rtpengine-ctl needs listen-cli enabled. Add it if the SBC install didn't.
if [ -f /etc/rtpengine/rtpengine.conf ] && ! grep -q '^listen-cli' /etc/rtpengine/rtpengine.conf; then
  $SUDO sed -i '/^listen-ng/a listen-cli = 127.0.0.1:9900' /etc/rtpengine/rtpengine.conf
  $SUDO systemctl restart rtpengine-daemon || true
fi

$SUDO systemctl daemon-reload
$SUDO systemctl enable zabbix-agent2 >/dev/null 2>&1 || true
$SUDO systemctl restart zabbix-agent2
sleep 1
$SUDO systemctl is-active --quiet zabbix-agent2 \
  || { echo "zabbix-agent2 failed to start; see: journalctl -u zabbix-agent2 -n 80" >&2; exit 1; }

echo "done. zabbix-agent2 is reporting as ${ZABBIX_HOSTNAME} to ${MONITORING_IP}."
