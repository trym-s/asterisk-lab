#!/usr/bin/env bash
# Smoke-check the voicebot observability dashboard on this host. Non-zero
# exit on first failure; prints a one-line pass/fail per check. Run via
# `make verify-voicebot-dashboard` or directly.
set -u
set -o pipefail

SUDO=$([ "$(id -u)" -eq 0 ] && echo "" || echo "sudo")

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../../.." && pwd)"
# shellcheck source=/dev/null
. "$REPO_ROOT/infra/scripts/lib/env.sh"
load_lab_env "$REPO_ROOT" >/dev/null 2>&1 || true
BIND="${VOICEBOT_DASHBOARD_BIND:-127.0.0.1}"
PORT="${VOICEBOT_DASHBOARD_PORT:-8099}"
BASE="http://${BIND}:${PORT}"

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

echo "== voicebot-dashboard =="
check "voicebot-dashboard.service active" "active" "$SUDO systemctl is-active voicebot-dashboard"
check "venv python runnable"              "Python 3" "/opt/voicebot-dashboard/venv/bin/python --version"
check "/api/healthz returns ok"           '"status":\s*"ok"' "curl -sf $BASE/api/healthz"
check "/api/calls returns JSON"           '"calls"'         "curl -sf $BASE/api/calls"
check "/api/parity returns JSON"          '"lanes"'         "curl -sf $BASE/api/parity"
check "/api/cost returns JSON"            '"rows"'          "curl -sf $BASE/api/cost"
check "/api/transcriber returns JSON"     '"recordings"'    "curl -sf $BASE/api/transcriber"
check "/ renders 200"                     "^200$"           "curl -s -o /dev/null -w '%{http_code}' $BASE/"
check "/parity renders 200"               "^200$"           "curl -s -o /dev/null -w '%{http_code}' $BASE/parity"
check "/cost renders 200"                 "^200$"           "curl -s -o /dev/null -w '%{http_code}' $BASE/cost"
check "/transcript renders 200"           "^200$"           "curl -s -o /dev/null -w '%{http_code}' $BASE/transcript"
check "/transcriber renders 200"          "^200$"           "curl -s -o /dev/null -w '%{http_code}' $BASE/transcriber"

echo
total=$((pass + fail))
if [ "$fail" -eq 0 ]; then
  echo "$pass/$total OK"
  exit 0
else
  echo "$fail/$total FAILED"
  exit 1
fi
