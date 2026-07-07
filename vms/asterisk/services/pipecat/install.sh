#!/usr/bin/env bash
# Provision the Pipecat voicebot stack on the Asterisk VM.
# Mirrors services/livekit/install.sh in shape so the two lanes deploy
# identically apart from what they run.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
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

echo
echo "done. Pipecat voicebot stack running. verify:"
echo "  docker compose -f $HERE/docker-compose.yml ps"
echo "  docker logs pc-agent --tail=50"
echo "  ss -ltnp | grep 8090       # AudioSocket listener"
echo "  # then dial 1098 from a registered softphone"
