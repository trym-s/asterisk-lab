#!/usr/bin/env bash
# Set up the monitoring VM: Zabbix 7.0 LTS + PostgreSQL + Apache frontend
# plus Grafana and the Grafana Zabbix plugin.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# shellcheck source=/dev/null
[ -f .env ] && { set -a; . .env; set +a; }
: "${ZABBIX_DB_PASSWORD:?ZABBIX_DB_PASSWORD not set; add it to the monitoring VM .env}"
: "${MONITORING_IP:=$(hostname -I | awk '{print $1}')}"
: "${ZABBIX_VERSION:=7.0}"

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
echo "==> distro: $PRETTY_NAME"

sql_quote() {
  printf "%s" "$1" | sed "s/'/''/g"
}

sed_replacement_quote() {
  printf "%s" "$1" | sed 's/[\/&]/\\&/g'
}

postgres_exec() {
  $SUDO -u postgres psql -v ON_ERROR_STOP=1 "$@"
}

echo "==> apt prerequisites"
$SUDO apt-get update -qq
DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y --no-install-recommends \
  ca-certificates curl wget gnupg2 apt-transport-https rsync gettext-base \
  locales postgresql apache2

echo "==> locale en_US.UTF-8"
if ! locale -a | grep -qi '^en_US\.utf8$'; then
  $SUDO sed -i 's/^# *\(en_US.UTF-8 UTF-8\)/\1/' /etc/locale.gen
  if ! grep -q '^en_US.UTF-8 UTF-8' /etc/locale.gen; then
    echo 'en_US.UTF-8 UTF-8' | $SUDO tee -a /etc/locale.gen >/dev/null
  fi
  $SUDO locale-gen en_US.UTF-8
fi

echo "==> Zabbix ${ZABBIX_VERSION} apt repository"
ZABBIX_RELEASE="zabbix-release_latest_${ZABBIX_VERSION}+debian${ZABBIX_DEBIAN_MAJOR}_all.deb"
ZABBIX_RELEASE_URL="https://repo.zabbix.com/zabbix/${ZABBIX_VERSION}/debian/pool/main/z/zabbix-release/${ZABBIX_RELEASE}"
if [ ! -f /etc/apt/sources.list.d/zabbix.list ] || ! grep -q "repo.zabbix.com/zabbix/${ZABBIX_VERSION}" /etc/apt/sources.list.d/zabbix.list; then
  tmp_deb="/tmp/${ZABBIX_RELEASE}"
  curl -fsSL "$ZABBIX_RELEASE_URL" -o "$tmp_deb"
  $SUDO dpkg -i "$tmp_deb"
  $SUDO apt-get update -qq
fi

echo "==> Grafana apt repository"
$SUDO install -d -m 0755 /etc/apt/keyrings
if [ ! -s /etc/apt/keyrings/grafana.asc ]; then
  $SUDO wget -q -O /etc/apt/keyrings/grafana.asc https://apt.grafana.com/gpg-full.key
  $SUDO chmod 0644 /etc/apt/keyrings/grafana.asc
fi
GRAFANA_LIST=/etc/apt/sources.list.d/grafana.list
GRAFANA_LINE="deb [signed-by=/etc/apt/keyrings/grafana.asc] https://apt.grafana.com stable main"
if [ ! -f "$GRAFANA_LIST" ] || ! grep -qxF "$GRAFANA_LINE" "$GRAFANA_LIST"; then
  echo "$GRAFANA_LINE" | $SUDO tee "$GRAFANA_LIST" >/dev/null
  $SUDO apt-get update -qq
fi

echo "==> monitoring packages"
DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y --no-install-recommends \
  zabbix-server-pgsql zabbix-frontend-php zabbix-apache-conf \
  zabbix-sql-scripts zabbix-agent2 zabbix-get php-pgsql grafana

echo "==> PostgreSQL database"
$SUDO systemctl enable --now postgresql >/dev/null
if ! postgres_exec -tAc "SELECT 1 FROM pg_roles WHERE rolname='zabbix'" | grep -qx 1; then
  postgres_exec -c "CREATE USER zabbix WITH PASSWORD '$(sql_quote "$ZABBIX_DB_PASSWORD")';"
else
  postgres_exec -c "ALTER USER zabbix WITH PASSWORD '$(sql_quote "$ZABBIX_DB_PASSWORD")';"
fi
if ! postgres_exec -tAc "SELECT 1 FROM pg_database WHERE datname='zabbix'" | grep -qx 1; then
  postgres_exec -c "CREATE DATABASE zabbix OWNER zabbix;"
fi

schema_ready=false
if postgres_exec -d zabbix -tAc "SELECT to_regclass('public.users') IS NOT NULL;" 2>/dev/null | grep -qx t; then
  schema_ready=true
fi
if [ "$schema_ready" = false ]; then
  echo "==> importing Zabbix schema"
  zcat /usr/share/zabbix-sql-scripts/postgresql/server.sql.gz \
    | $SUDO -u zabbix psql -v ON_ERROR_STOP=1 zabbix >/dev/null
fi

echo "==> Zabbix server config"
$SUDO install -m 0640 -o root -g zabbix /etc/zabbix/zabbix_server.conf /etc/zabbix/zabbix_server.conf.bak
db_password_escaped=$(sed_replacement_quote "$ZABBIX_DB_PASSWORD")
$SUDO sed -i \
  -e "s/^# DBPassword=.*/DBPassword=${db_password_escaped}/" \
  -e "s/^DBPassword=.*/DBPassword=${db_password_escaped}/" \
  /etc/zabbix/zabbix_server.conf
if ! grep -q '^DBPassword=' /etc/zabbix/zabbix_server.conf; then
  printf '\nDBPassword=%s\n' "$ZABBIX_DB_PASSWORD" | $SUDO tee -a /etc/zabbix/zabbix_server.conf >/dev/null
fi

echo "==> Zabbix web config"
$SUDO install -d -m 0750 -o www-data -g www-data /etc/zabbix/web
# shellcheck disable=SC2016
ZABBIX_DB_PASSWORD="$ZABBIX_DB_PASSWORD" \
  envsubst '${ZABBIX_DB_PASSWORD}' \
  < monitoring/zabbix-web.conf.php.tmpl \
  | $SUDO tee /etc/zabbix/web/zabbix.conf.php >/dev/null
$SUDO chown www-data:www-data /etc/zabbix/web/zabbix.conf.php
$SUDO chmod 0640 /etc/zabbix/web/zabbix.conf.php

echo "==> Zabbix lab hosts + items"
SBC_IP="${SBC_IP:-192.168.122.3}" \
  ZABBIX_USER="${ZABBIX_USER:-Admin}" \
  ZABBIX_PASSWORD="${ZABBIX_PASSWORD:-zabbix}" \
  python3 monitoring/provision-observability.py

echo "==> local Zabbix agent config"
$SUDO env MONITORING_IP="$MONITORING_IP" ZABBIX_VERSION="$ZABBIX_VERSION" ./monitoring/setup-zabbix-agent.sh

echo "==> Grafana Zabbix plugin"
GRAFANA_CLI=/usr/sbin/grafana-cli
GRAFANA_HOME=/usr/share/grafana
if ! "$GRAFANA_CLI" --homepath "$GRAFANA_HOME" plugins ls 2>/dev/null | grep -q '^alexanderzobnin-zabbix-app '; then
  $SUDO "$GRAFANA_CLI" --homepath "$GRAFANA_HOME" plugins install alexanderzobnin-zabbix-app
fi

echo "==> Grafana datasource + dashboard provisioning"
$SUDO install -m 0644 monitoring/grafana-datasource-zabbix.yaml /etc/grafana/provisioning/datasources/zabbix.yaml
$SUDO install -m 0644 monitoring/grafana-dashboard-provider.yaml /etc/grafana/provisioning/dashboards/asterisk-lab.yaml
$SUDO install -d -m 0755 -o grafana -g grafana /var/lib/grafana/dashboards/asterisk-lab
$SUDO install -m 0644 -o grafana -g grafana monitoring/grafana-opensips-dashboard.json /var/lib/grafana/dashboards/asterisk-lab/opensips-sbc-overview.json

echo "==> enable + restart services"
$SUDO systemctl daemon-reload
$SUDO systemctl enable apache2 zabbix-server zabbix-agent2 grafana-server >/dev/null 2>&1 || true
$SUDO systemctl restart apache2
$SUDO systemctl restart zabbix-server
$SUDO systemctl restart zabbix-agent2
$SUDO systemctl restart grafana-server

sleep 3
for service in postgresql apache2 zabbix-server zabbix-agent2 grafana-server; do
  $SUDO systemctl is-active --quiet "$service" \
    || { echo "$service failed to start; see: journalctl -u $service -n 80" >&2; exit 1; }
done

cat <<EOF

done. Monitoring services are running.
  Zabbix UI:  http://${MONITORING_IP}/zabbix
  Grafana:    http://${MONITORING_IP}:3000

Grafana package default login is admin/admin; rotate it on first login.
EOF
