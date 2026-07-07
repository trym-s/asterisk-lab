#!/usr/bin/env bash
# Set up the OpenSIPS + rtpengine SBC on a fresh Debian 13 / Ubuntu 26.04 host.
# Reading order: env → apt prereqs → opensips repo → install → render configs →
#                env toggles → enable → restart → verify.
# Idempotent: re-running on a configured box becomes a series of skips.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ---- env ------------------------------------------------------------
# shellcheck source=/dev/null
. "$REPO_ROOT/scripts/lib/env.sh"
load_lab_env "$REPO_ROOT"
: "${SBC_IP:?SBC_IP not set; add it to /etc/asterisk-lab/env or repo .env (virsh net-dhcp-leases default)}"
: "${ASTERISK_IP:?ASTERISK_IP not set; add it to the lab env file (the Asterisk VM IP that opensips will relay to)}"

SUDO=$([ "$(id -u)" -eq 0 ] && echo "" || echo "sudo")
$SUDO -v 2>/dev/null || true

# shellcheck source=/dev/null
. /etc/os-release
case "${ID:-}" in debian|ubuntu) ;; *) echo "unsupported distro: ${ID:-?}" >&2; exit 1;; esac
CODENAME="${VERSION_CODENAME:-trixie}"
echo "==> distro: $PRETTY_NAME (codename $CODENAME)"

# ---- 1. base apt prereqs --------------------------------------------
# rsyslog so /var/log/syslog exists (the design's "tail -f /var/log/syslog"
# pivot only works if rsyslog is present; Debian 13 cloud images ship without it).
# sngrep for live SIP capture, gettext-base for envsubst, rsync for `make deploy-sbc`.
echo "==> apt prerequisites"
$SUDO apt-get update -qq
DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y --no-install-recommends \
  ca-certificates curl rsync rsyslog sngrep gettext-base

# ---- 2. OpenSIPS 3.6 LTS apt repo -----------------------------------
KEYRING=/usr/share/keyrings/opensips-org.gpg
LIST=/etc/apt/sources.list.d/opensips.list
EXPECTED_LIST_LINE="deb [signed-by=${KEYRING}] https://apt.opensips.org ${CODENAME} 3.6-releases"

if [ ! -s "$KEYRING" ]; then
  echo "==> apt.opensips.org signing key"
  $SUDO install -d -m 0755 /usr/share/keyrings
  $SUDO curl -fsSL https://apt.opensips.org/opensips-org.gpg -o "$KEYRING"
fi

if [ ! -f "$LIST" ] || ! grep -qxF "$EXPECTED_LIST_LINE" "$LIST"; then
  echo "==> apt.opensips.org repo entry (3.6-releases for $CODENAME)"
  echo "$EXPECTED_LIST_LINE" | $SUDO tee "$LIST" >/dev/null
  $SUDO apt-get update -qq
fi

# ---- 3. opensips + rtpengine packages -------------------------------
# rtpengine.so module is built into the core opensips package — there is NO
# separate opensips-rtpengine-module apt package. rtpengine-daemon ships
# under the bare Sipwise name in Debian 13 (not ngcp-rtpengine-daemon).
echo "==> opensips + rtpengine-daemon"
DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y --no-install-recommends \
  opensips rtpengine-daemon

# ---- 4. render opensips.cfg from template ---------------------------
# envsubst whitelist is load-bearing: the template uses $du, $rs, $ru, $var(...)
# pseudo-variables that OpenSIPS expands at runtime. Without the whitelist envsubst
# would replace those with empty strings and the parser would reject the config.
echo "==> /etc/opensips/opensips.cfg from sbc/etc/opensips/opensips.cfg.tmpl"
# shellcheck disable=SC2016  # envsubst whitelist must be literal, not expanded.
SBC_IP="$SBC_IP" ASTERISK_IP="$ASTERISK_IP" \
  envsubst '${SBC_IP} ${ASTERISK_IP}' \
  < sbc/etc/opensips/opensips.cfg.tmpl \
  | $SUDO tee /etc/opensips/opensips.cfg.new >/dev/null
$SUDO /usr/sbin/opensips -C -f /etc/opensips/opensips.cfg.new >/dev/null
$SUDO chmod 0644 /etc/opensips/opensips.cfg.new
$SUDO mv /etc/opensips/opensips.cfg.new /etc/opensips/opensips.cfg

# ---- 5. flip RUN_OPENSIPS=yes ---------------------------------------
# Debian convention: /etc/default/opensips ships with RUN_OPENSIPS=no so an
# unconfigured server does not auto-start. The systemd unit sources this file
# and refuses to start until it is `yes`.
if grep -q '^RUN_OPENSIPS=no$' /etc/default/opensips; then
  echo "==> /etc/default/opensips: RUN_OPENSIPS=yes"
  $SUDO sed -i 's/^RUN_OPENSIPS=no$/RUN_OPENSIPS=yes/' /etc/default/opensips
fi

# ---- 6. render rtpengine.conf from template -------------------------
echo "==> /etc/rtpengine/rtpengine.conf from sbc/etc/rtpengine/rtpengine.conf.tmpl"
# shellcheck disable=SC2016  # envsubst whitelist must be literal, not expanded.
SBC_IP="$SBC_IP" \
  envsubst '${SBC_IP}' \
  < sbc/etc/rtpengine/rtpengine.conf.tmpl \
  | $SUDO tee /etc/rtpengine/rtpengine.conf.new >/dev/null
$SUDO chmod 0644 /etc/rtpengine/rtpengine.conf.new
$SUDO mv /etc/rtpengine/rtpengine.conf.new /etc/rtpengine/rtpengine.conf

# ---- 7. quiet rtpengine kernel-mode attempts ------------------------
# MANAGE_IPTABLES=yes makes the daemon try to install nftables forwarding
# rules at startup. With table=-1 (userspace) and no kernel module, those
# attempts fail and log two ERR lines per restart. Flip to `no` to stay
# silent.
if grep -q '^MANAGE_IPTABLES=yes$' /etc/default/rtpengine-daemon; then
  echo "==> /etc/default/rtpengine-daemon: MANAGE_IPTABLES=no"
  $SUDO sed -i 's/^MANAGE_IPTABLES=yes$/MANAGE_IPTABLES=no/' /etc/default/rtpengine-daemon
fi

# ---- 8. enable + restart --------------------------------------------
echo "==> enable + restart services"
$SUDO systemctl daemon-reload
$SUDO systemctl enable opensips rtpengine-daemon >/dev/null 2>&1 || true
$SUDO systemctl restart rtpengine-daemon
$SUDO systemctl restart opensips

sleep 1
$SUDO systemctl is-active --quiet opensips \
  || { echo "opensips failed to start; see: journalctl -u opensips -n 50" >&2; exit 1; }
$SUDO systemctl is-active --quiet rtpengine-daemon \
  || { echo "rtpengine-daemon failed to start; see: journalctl -u rtpengine-daemon -n 50" >&2; exit 1; }

echo
echo "done. SBC up. verify:"
echo "  ./sbc/verify.sh"
echo "  sudo ss -ulnp | grep -E ':5060|:2223'"
echo "  sudo tail -f /var/log/syslog"
echo "  sudo sngrep -d any port 5060"
