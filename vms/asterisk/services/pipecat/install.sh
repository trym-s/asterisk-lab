#!/usr/bin/env bash
# Provision the Pipecat voicebot stack on the Asterisk VM.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
find_repo_root() {
  local dir="$1"
  while [ "$dir" != "/" ]; do
    if [ -f "$dir/infra/scripts/lib/env.sh" ]; then
      printf '%s\n' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  echo "ERROR: could not find repo root from $1" >&2
  return 1
}
REPO_ROOT="$(find_repo_root "$HERE")"
cd "$REPO_ROOT"

# shellcheck source=/dev/null
. "$REPO_ROOT/infra/scripts/lib/env.sh"
load_lab_env "$REPO_ROOT"
: "${OPENAI_API_KEY:?OPENAI_API_KEY not set in the lab env file}"

if [ -z "${VOICEBOT_REPO_REVISION:-}" ]; then
  if git -C "$REPO_ROOT" rev-parse --short=12 HEAD >/dev/null 2>&1; then
    VOICEBOT_REPO_REVISION="$(git -C "$REPO_ROOT" rev-parse --short=12 HEAD)"
  elif [ -f "$REPO_ROOT/.deploy-revision" ]; then
    VOICEBOT_REPO_REVISION="$(cat "$REPO_ROOT/.deploy-revision")"
  else
    VOICEBOT_REPO_REVISION="unknown"
  fi
fi
export VOICEBOT_REPO_REVISION

SUDO=$([ "$(id -u)" -eq 0 ] && echo "" || echo "sudo")

# ---- 0. shared usage/turns log dir (idempotent, mirrors LK install.sh) --
$SUDO install -d -o root -g root -m 0755 /var/lib/voicebot

# ---- 1. docker (skip if the LK install already put it here) ------------
if ! command -v docker >/dev/null 2>&1; then
  echo "==> installing docker"
  $SUDO apt-get update -qq
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y --no-install-recommends \
    docker.io docker-compose-v2
  $SUDO systemctl enable --now docker
else
  echo "==> docker present: $(docker --version)"
fi

# ---- 2. compose up -----------------------------------------------------
echo "==> starting Pipecat stack"
cd "$HERE"
$SUDO docker compose \
  --env-file "$LAB_ENV_FILE" \
  up -d --build

echo "==> waiting for Pipecat AudioSocket listener"
ready=0
for _ in {1..30}; do
  if ss -ltn "sport = :8090" | grep -q ':8090'; then
    ready=1
    break
  fi
  sleep 1
done
if [ "$ready" != "1" ]; then
  echo "ERROR: pc-agent is not listening on TCP 127.0.0.1:8090" >&2
  $SUDO docker compose ps >&2 || true
  $SUDO docker logs pc-agent --tail=80 >&2 || true
  exit 1
fi

echo
echo "done. Pipecat voicebot stack running. verify:"
echo "  docker compose -f $HERE/docker-compose.yml ps"
echo "  docker logs pc-agent --tail=50"
echo "  ss -ltnp | grep 8090       # AudioSocket listener"
echo "  # then dial 1098 from a registered softphone"
