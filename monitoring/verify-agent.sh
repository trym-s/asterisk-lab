#!/usr/bin/env bash
# Smoke-check zabbix-agent2 on a monitored lab node.
set -u
set -o pipefail

SUDO=sudo

pass=0
fail=0

check() {
  local name="$1" pattern="$2" cmd="$3"
  printf '  %-42s ' "$name"
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

echo "== zabbix agent =="
check "zabbix-agent2.service active" "active" "$SUDO systemctl is-active zabbix-agent2"
check "zabbix agent listening 10050" "10050"  "$SUDO ss -ltnp 'sport = :10050'"
check "lab UserParameter file present" "lab.systemd.active" "grep '^UserParameter=lab.systemd.active' /etc/zabbix/zabbix_agent2.d/lab.conf"
check "agent config has Server"      "^Server=" "grep '^Server=' /etc/zabbix/zabbix_agent2.conf"
check "agent config has Hostname"    "^Hostname=" "grep '^Hostname=' /etc/zabbix/zabbix_agent2.conf"
if [ -S /run/opensips/opensips_fifo ] || [ -p /run/opensips/opensips_fifo ]; then
  check "opensips MI helper installed" "opensips-mi-zabbix" "ls /usr/local/bin/opensips-mi-zabbix"
  check "opensips MI ping works"      "1" "sudo -u zabbix /usr/local/bin/opensips-mi-zabbix ping"
fi

echo
total=$((pass + fail))
if [ "$fail" -eq 0 ]; then
  echo "$pass/$total OK"
  exit 0
else
  echo "$fail/$total FAILED"
  exit 1
fi
