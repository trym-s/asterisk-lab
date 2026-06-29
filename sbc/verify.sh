#!/usr/bin/env bash
# Smoke-check the SBC layer on this host. Non-zero exit on first failure;
# prints a one-line pass/fail per check. Run via `make verify-sbc` or directly.
# Some checks need sudo (config parse, raw socket inspection) — invoke with
# sudo or run as a user with passwordless sudo.
set -u
set -o pipefail

SUDO=$([ "$(id -u)" -eq 0 ] && echo "" || echo "sudo")

pass=0
fail=0

check() {
  local name="$1" pattern="$2" cmd="$3"
  printf '  %-44s ' "$name"
  local out
  if ! out=$(eval "$cmd" 2>&1); then
    echo "FAIL"
    echo "      cmd:    $cmd"
    echo "      error:  $(echo "$out" | head -1)"
    fail=$((fail + 1))
    return
  fi
  if [[ "$out" =~ $pattern ]]; then
    echo "OK"
    pass=$((pass + 1))
  else
    echo "FAIL"
    echo "      cmd:    $cmd"
    echo "      want:   $pattern"
    echo "      got:    $(echo "$out" | head -1)"
    fail=$((fail + 1))
  fi
}

echo "== opensips =="
check "opensips.service active"           "active"     "$SUDO systemctl is-active opensips"
check "opensips 3.6.x installed"          "opensips 3" "$SUDO /usr/sbin/opensips -V"
check "opensips.cfg parses"               "config file ok" "$SUDO /usr/sbin/opensips -C -f /etc/opensips/opensips.cfg 2>&1"
check "udp/5060 bound by opensips"        "opensips"   "$SUDO ss -ulnp 'sport = :5060'"
check "mi_fifo present (0666)"            "prw-rw-rw-" "ls -l /run/opensips/opensips_fifo"

echo
echo "== rtpengine =="
check "rtpengine-daemon.service active"   "active"     "$SUDO systemctl is-active rtpengine-daemon"
check "udp/2223 bound by rtpengine"       "rtpengine"  "$SUDO ss -ulnp 'sport = :2223'"
check "userspace mode (table=-1)"         "table = -1" "grep '^table' /etc/rtpengine/rtpengine.conf"
check "log-facility=local1"               "local1"     "grep '^log-facility' /etc/rtpengine/rtpengine.conf"

echo
echo "== shared =="
check "rsyslog active (/var/log/syslog)"  "active"     "$SUDO systemctl is-active rsyslog"
check "sngrep installed"                  "sngrep"     "command -v sngrep"

echo
total=$((pass + fail))
if [ "$fail" -eq 0 ]; then
  echo "$pass/$total OK"
  exit 0
else
  echo "$fail/$total FAILED"
  exit 1
fi
