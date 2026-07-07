#!/usr/bin/env bash
# Smoke-check the monitoring VM. Non-zero exit if any check fails.
set -u
set -o pipefail

SUDO=sudo

pass=0
fail=0

check() {
  local name="$1" pattern="$2" cmd="$3"
  printf '  %-46s ' "$name"
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

echo "== database =="
check "postgresql.service active"       "active" "$SUDO systemctl is-active postgresql"
check "zabbix database exists"          "1"      "$SUDO -u postgres psql -tAc \"SELECT 1 FROM pg_database WHERE datname='zabbix'\""
check "zabbix schema imported"          "t"      "$SUDO -u postgres psql -d zabbix -tAc \"SELECT to_regclass('public.users') IS NOT NULL\""

echo
echo "== zabbix =="
check "en_US.UTF-8 locale generated"    "en_US.utf8" "locale -a"
check "zabbix-server.service active"    "active" "$SUDO systemctl is-active zabbix-server"
check "zabbix-agent2.service active"    "active" "$SUDO systemctl is-active zabbix-agent2"
check "zabbix server listening 10051"   "10051"  "$SUDO ss -ltnp 'sport = :10051'"
check "zabbix agent listening 10050"    "10050"  "$SUDO ss -ltnp 'sport = :10050'"
check "local zabbix agent ping"         "1"      "zabbix_get -s 127.0.0.1 -k agent.ping"
check "php pgsql module loaded"         "pgsql"  "php -m"
check "zabbix web config present"       "POSTGRESQL" "$SUDO grep \"POSTGRESQL\" /etc/zabbix/web/zabbix.conf.php"
check "elasticsearch history disabled"  "\\[\\]" "$SUDO grep \"HISTORY\\['types'\\]\" /etc/zabbix/web/zabbix.conf.php"
check "apache.service active"           "active" "$SUDO systemctl is-active apache2"
check "zabbix web route responds"       "200|302" "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/zabbix/"

echo
echo "== grafana =="
check "grafana-server.service active"   "active" "$SUDO systemctl is-active grafana-server"
check "grafana listening 3000"          "3000"   "$SUDO ss -ltnp 'sport = :3000'"
check "grafana HTTP responds"           "200|302" "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/login"
check "grafana zabbix plugin installed" "alexanderzobnin-zabbix-app" "/usr/sbin/grafana-cli --homepath /usr/share/grafana plugins ls"
check "grafana zabbix datasource provisioned" "alexanderzobnin-zabbix-datasource" "grep 'alexanderzobnin-zabbix-datasource' /etc/grafana/provisioning/datasources/zabbix.yaml"
check "grafana opensips dashboard provisioned" "OpenSIPS SBC Overview" "grep 'OpenSIPS SBC Overview' /var/lib/grafana/dashboards/asterisk-lab/opensips-sbc-overview.json"

echo
total=$((pass + fail))
if [ "$fail" -eq 0 ]; then
  echo "$pass/$total OK"
  exit 0
else
  echo "$fail/$total FAILED"
  exit 1
fi
