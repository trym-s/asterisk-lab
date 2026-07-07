#!/usr/bin/env bash
# Provision the read-only voicebot observability dashboard (FastAPI + Tabler)
# on the Asterisk VM. Idempotent.
#
# Mirrors the transcriber precedent: a Python virtualenv plus a systemd unit
# running uvicorn, not a container. The venv and a copy of the app/common
# code live under /opt/voicebot-dashboard so the service survives repo
# redeploys, which rsync --delete the /opt/asterisk-lab/current payload.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../../.." && pwd)"
cd "$REPO_ROOT"

# shellcheck source=/dev/null
. "$REPO_ROOT/infra/scripts/lib/env.sh"
load_lab_env "$REPO_ROOT"

SUDO=$([ "$(id -u)" -eq 0 ] && echo "" || echo "sudo")

APPDIR=/opt/voicebot-dashboard
VENV="$APPDIR/venv"
UV_BIN=/usr/local/bin/uv

echo "==> shared voicebot log dir (idempotent, mirrors the lane installers)"
$SUDO install -d -o root -g root -m 0755 /var/lib/voicebot

echo "==> uv (Python package manager)"
if [ ! -x "$UV_BIN" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | $SUDO env UV_INSTALL_DIR=/usr/local/bin sh
else
  echo "    uv present: $("$UV_BIN" --version)"
fi

echo "==> app dir $APPDIR"
$SUDO install -d -m 0755 "$APPDIR"
$SUDO rm -rf "$APPDIR/app" "$APPDIR/common"
$SUDO cp -r "$HERE/app" "$APPDIR/app"
$SUDO install -d -m 0755 "$APPDIR/common"
for f in trace_events.py usage.py usage_summary.py voicebot_profile.py; do
  $SUDO install -m 0644 "$HERE/../common/$f" "$APPDIR/common/$f"
done
$SUDO find "$APPDIR/app" -name '__pycache__' -prune -exec rm -rf {} +
$SUDO install -m 0644 "$HERE/pyproject.toml" "$APPDIR/pyproject.toml"
$SUDO install -m 0644 "$HERE/uv.lock" "$APPDIR/uv.lock"

echo "==> venv at $VENV (uv sync --frozen from pyproject.toml/uv.lock)"
$SUDO env UV_PROJECT_ENVIRONMENT="$VENV" "$UV_BIN" sync --frozen --project "$APPDIR"

echo "==> systemd unit"
$SUDO install -m 0644 "$REPO_ROOT/vms/asterisk/lib/systemd/system/voicebot-dashboard.service" \
  /etc/systemd/system/voicebot-dashboard.service
$SUDO systemctl daemon-reload
$SUDO systemctl enable --now voicebot-dashboard.service
$SUDO systemctl restart voicebot-dashboard.service

echo
echo "done. voicebot dashboard running. verify:"
echo "  systemctl status voicebot-dashboard --no-pager"
echo "  curl -s http://\${VOICEBOT_DASHBOARD_BIND:-127.0.0.1}:\${VOICEBOT_DASHBOARD_PORT:-8099}/api/healthz"
echo "  ssh -L 8099:127.0.0.1:8099 <vm>   # then open http://127.0.0.1:8099 on the host"
