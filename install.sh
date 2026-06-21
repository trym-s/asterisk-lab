#!/usr/bin/env bash
# Set up an Asterisk PBX on a fresh Debian 13 / Ubuntu 26.04 host.
# Reading order: deps → build asterisk → user → systemd → configs → start.
# Idempotent: re-running on a configured box is a series of "already done" skips.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# ---- env ------------------------------------------------------------
[ -f .env ] && { set -a; . .env; set +a; }
: "${SIP_EXT_1001_PASSWORD:?SIP_EXT_1001_PASSWORD not set; cp .env.example .env and fill it in}"
: "${ASTERISK_VERSION:=22.9.0}"

SUDO=$([ "$(id -u)" -eq 0 ] && echo "" || echo "sudo")
$SUDO -v 2>/dev/null || true

. /etc/os-release
case "${ID:-}" in debian|ubuntu) ;; *) echo "unsupported distro: ${ID:-?}" >&2; exit 1;; esac
echo "==> distro: $PRETTY_NAME"

# ---- 1. apt build prerequisites -------------------------------------
echo "==> apt prerequisites"
$SUDO apt-get update -qq
DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y --no-install-recommends \
  build-essential autoconf libtool pkg-config git wget ca-certificates gettext-base \
  sngrep python3 python3-venv

# ---- 2. build asterisk if not already at the target version ---------
SRC=/usr/local/src/asterisk
if [ -x /usr/sbin/asterisk ] && /usr/sbin/asterisk -V 2>/dev/null | grep -q "$ASTERISK_VERSION"; then
  echo "==> asterisk $ASTERISK_VERSION already installed; skipping build"
else
  echo "==> building asterisk $ASTERISK_VERSION (slow — first run is ~10 min)"
  [ -d "$SRC/.git" ] || $SUDO git clone https://github.com/asterisk/asterisk.git "$SRC"
  $SUDO git -C "$SRC" fetch --all --tags
  $SUDO git -C "$SRC" checkout "$ASTERISK_VERSION"
  $SUDO "$SRC/contrib/scripts/install_prereq" install
  ( cd "$SRC" && $SUDO ./configure && $SUDO make -j"$(nproc)" && $SUDO make install && $SUDO make samples )
fi

# ---- 3. system user + directory ownership ---------------------------
echo "==> asterisk system user"
getent group  asterisk >/dev/null || $SUDO groupadd -r asterisk
getent passwd asterisk >/dev/null || $SUDO useradd -r -g asterisk \
  -d /var/lib/asterisk -s /usr/sbin/nologin -c "Asterisk PBX" asterisk
for d in /etc/asterisk /var/lib/asterisk /var/spool/asterisk /var/log/asterisk; do
  [ -d "$d" ] && $SUDO chown -R asterisk:asterisk "$d"
done

# ---- 4. systemd unit ------------------------------------------------
echo "==> systemd unit"
$SUDO install -m 0644 asterisk/asterisk.service /etc/systemd/system/asterisk.service
$SUDO systemctl daemon-reload
$SUDO systemctl enable asterisk

# ---- 5. render configs from templates -------------------------------
echo "==> asterisk configs"
export SIP_EXT_1001_PASSWORD
$SUDO sh -c "envsubst < '$REPO_ROOT/asterisk/pjsip.conf.tmpl' > /etc/asterisk/pjsip.conf"
$SUDO install -m 0644 asterisk/extensions.conf.tmpl /etc/asterisk/extensions.conf
$SUDO install -m 0644 asterisk/rtp.conf /etc/asterisk/rtp.conf
$SUDO install -d -o asterisk -g asterisk -m 0755 /var/spool/asterisk/monitor
$SUDO chown asterisk:asterisk /etc/asterisk/pjsip.conf /etc/asterisk/extensions.conf /etc/asterisk/rtp.conf
$SUDO chmod 0640 /etc/asterisk/pjsip.conf   # contains password

# ---- 6. start, verify -----------------------------------------------
echo "==> (re)starting asterisk"
$SUDO systemctl restart asterisk
sleep 2
$SUDO systemctl is-active --quiet asterisk \
  || { echo "asterisk failed to start; see: journalctl -u asterisk -n 50" >&2; exit 1; }

echo
echo "done. asterisk $ASTERISK_VERSION running. verify:"
echo "  systemctl status asterisk"
echo "  sudo asterisk -rx 'pjsip show endpoints'"
echo "  sudo asterisk -rx 'dialplan show from-softphones'"
echo "  sudo sngrep -d any port 5060"
echo
echo "transcription (optional, runs locally on this box):"
echo "  sudo ./scripts/setup-transcriber.sh     # venv + transcriber systemd unit"
echo "  systemctl status transcriber"
