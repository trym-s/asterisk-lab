#!/usr/bin/env bash
# Set up an Asterisk PBX on a fresh Debian 13 / Ubuntu 26.04 host.
# Reading order: deps → build asterisk → user → systemd → configs → start.
# Idempotent: re-running on a configured box is a series of "already done" skips.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# ---- env ------------------------------------------------------------
# shellcheck source=/dev/null
. "$REPO_ROOT/infra/scripts/lib/env.sh"
load_lab_env "$REPO_ROOT"
: "${SIP_EXTENSIONS:?SIP_EXTENSIONS not set; create /etc/asterisk-lab/env or repo .env and fill it in}"
: "${ASTERISK_VERSION:=22.9.0}"
: "${MAKE_JOBS:=$(nproc)}"
for ext in $SIP_EXTENSIONS; do
  pw_var="SIP_EXT_${ext}_PASSWORD"
  : "${!pw_var:?$pw_var not set; add it to the lab env file}"
done

SUDO=$([ "$(id -u)" -eq 0 ] && echo "" || echo "sudo")
$SUDO -v 2>/dev/null || true

# shellcheck source=/dev/null
. /etc/os-release
case "${ID:-}" in debian|ubuntu) ;; *) echo "unsupported distro: ${ID:-?}" >&2; exit 1;; esac
echo "==> distro: $PRETTY_NAME"

# ---- 1. apt build prerequisites -------------------------------------
echo "==> apt prerequisites"
$SUDO apt-get update -qq
DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y --no-install-recommends \
  build-essential autoconf libtool pkg-config git wget ca-certificates gettext-base \
  sngrep python3 python3-venv rsync

# ---- 2. build asterisk if not already at the target version ---------
SRC=/usr/local/src/asterisk
if [ -x /usr/sbin/asterisk ] && /usr/sbin/asterisk -V 2>/dev/null | grep -q "$ASTERISK_VERSION"; then
  echo "==> asterisk $ASTERISK_VERSION already installed; skipping build"
else
  echo "==> building asterisk $ASTERISK_VERSION (slow — first run is ~10 min)"
  # shellcheck disable=SC2086 # $SUDO is intentionally unquoted (empty or "sudo")
  [ -d "$SRC/.git" ] || retry $SUDO git clone https://github.com/asterisk/asterisk.git "$SRC"
  # shellcheck disable=SC2086
  retry $SUDO git -C "$SRC" fetch --all --tags
  $SUDO git -C "$SRC" checkout "$ASTERISK_VERSION"
  # Upstream install_prereq has a known rough edge: its internal
  # check_installed_debs pipeline ends in `grep -vF :`, which exits 1 when
  # every required package is already installed (nothing to invert-match),
  # and install_prereq's own `set -e` treats that as fatal even though
  # nothing actually went wrong. This reliably happens on a re-run (the
  # idempotent case this installer must support) once all -dev packages
  # are already present. Don't treat its exit code as authoritative -
  # ./configure right below is the real test of whether prerequisites are
  # satisfied and fails loudly and specifically if something is missing.
  $SUDO "$SRC/contrib/scripts/install_prereq" install || true
  # ./configure downloads the bundled pjproject tarball from
  # raw.githubusercontent.com, and `make install`/`make samples` download
  # sound/MOH archives from downloads.asterisk.org; on a flaky link these
  # can time out or come back truncated even after their own single
  # internal retry. retry each network-touching step (not `make -j` itself
  # - a real compile failure should not be masked by blind retries).
  # shellcheck disable=SC2086
  ( cd "$SRC" && retry $SUDO ./configure && $SUDO make -j"$MAKE_JOBS" && retry $SUDO make install && retry $SUDO make samples )
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
$SUDO install -m 0644 vms/asterisk/lib/systemd/system/asterisk.service /etc/systemd/system/asterisk.service
$SUDO systemctl daemon-reload
$SUDO systemctl enable asterisk

# ---- 5. render configs from templates -------------------------------
echo "==> asterisk configs"
$SUDO install -o asterisk -g asterisk -m 0644 vms/asterisk/etc/asterisk/pjsip.conf.tmpl /etc/asterisk/pjsip.conf
$SUDO install -o asterisk -g asterisk -m 0644 vms/asterisk/etc/asterisk/extensions.conf.tmpl /etc/asterisk/extensions.conf
$SUDO install -o asterisk -g asterisk -m 0644 vms/asterisk/etc/asterisk/rtp.conf /etc/asterisk/rtp.conf
$SUDO install -d -o asterisk -g asterisk -m 0755 /var/spool/asterisk/monitor

# Per-endpoint pjsip.d/<ext>.conf — rendered from pjsip-endpoint.conf.tmpl.
# envsubst whitelist prevents the template's other $-variables (none today,
# but future-proof) from being silently substituted to empty.
$SUDO install -d -o asterisk -g asterisk -m 0750 /etc/asterisk/pjsip.d
for ext in $SIP_EXTENSIONS; do
  pw_var="SIP_EXT_${ext}_PASSWORD"
  out=/etc/asterisk/pjsip.d/${ext}.conf
  # shellcheck disable=SC2016  # envsubst whitelist must be literal, not expanded.
  SIP_EXT="$ext" SIP_EXT_PASSWORD="${!pw_var}" \
    envsubst '${SIP_EXT} ${SIP_EXT_PASSWORD}' \
    < vms/asterisk/etc/asterisk/pjsip-endpoint.conf.tmpl \
    | $SUDO tee "${out}.new" >/dev/null
  $SUDO chown asterisk:asterisk "${out}.new"
  $SUDO chmod 0640 "${out}.new"
  $SUDO mv "${out}.new" "$out"
done

# Drop orphaned endpoint files (in /etc but not in SIP_EXTENSIONS) so
# removing a number from the lab env file removes the endpoint on re-run.
shopt -s nullglob
for f in /etc/asterisk/pjsip.d/*.conf; do
  ext=$(basename "$f" .conf)
  [[ " $SIP_EXTENSIONS " == *" $ext "* ]] || { echo "  pruning orphan endpoint $ext"; $SUDO rm "$f"; }
done
shopt -u nullglob

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
echo "  sudo ./infra/scripts/setup-transcriber.sh     # venv + transcriber systemd unit"
echo "  systemctl status transcriber"
