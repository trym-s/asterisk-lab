#!/usr/bin/env bash
# Provision the LiveKit voicebot stack on the Asterisk VM.
# Reading order: env → docker → render configs → compose up → provision trunk.
# Idempotent: re-running against a running stack is a no-op except for image pulls.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
cd "$REPO_ROOT"

# shellcheck source=/dev/null
. "$REPO_ROOT/scripts/lib/env.sh"
load_lab_env "$REPO_ROOT"
: "${OPENAI_API_KEY:?OPENAI_API_KEY not set in the lab env file}"
: "${LIVEKIT_API_KEY:?LIVEKIT_API_KEY not set in the lab env file (any 12+ char string)}"
: "${LIVEKIT_API_SECRET:?LIVEKIT_API_SECRET not set in the lab env file (any 32+ char random string)}"

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

# ---- 0. shared usage log directory ----------------------------------
# Both agent stacks + test-caller append to /var/lib/voicebot/usage.jsonl.
# Owned by root:root so anything running as root inside a container can write;
# `make usage-summary` reads it back on the VM.
$SUDO install -d -o root -g root -m 0755 /var/lib/voicebot

# ---- 1. docker + compose plugin -------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  echo "==> installing docker"
  $SUDO apt-get update -qq
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y --no-install-recommends \
    docker.io docker-compose-v2 gettext-base
  $SUDO systemctl enable --now docker
else
  echo "==> docker present: $(docker --version)"
fi

# ---- 2. render templated configs ------------------------------------
# livekit.yaml has $LIVEKIT_API_KEY / $LIVEKIT_API_SECRET placeholders that
# must be substituted before the container reads the file. sip.yaml the same.
# We render into services/livekit/.rendered/ and bind-mount from there.
RENDERED="$HERE/.rendered"
mkdir -p "$RENDERED"
for f in livekit.yaml sip.yaml; do
  # shellcheck disable=SC2016
  envsubst '${LIVEKIT_API_KEY} ${LIVEKIT_API_SECRET}' \
    < "$HERE/$f" > "$RENDERED/$f"
done

# Point compose at the rendered files. We do this with a tiny override so the
# committed docker-compose.yml keeps referencing the source templates for
# local dev / IDE navigation, but installs consume the rendered copies.
cat > "$RENDERED/docker-compose.override.yml" <<EOF
services:
  livekit-server:
    volumes:
      - $RENDERED/livekit.yaml:/etc/livekit.yaml:ro
  livekit-sip:
    volumes:
      - $RENDERED/sip.yaml:/etc/sip.yaml:ro
EOF

# ---- 3. compose up --------------------------------------------------
echo "==> starting LiveKit stack"
cd "$HERE"
$SUDO docker compose \
  -f docker-compose.yml \
  -f "$RENDERED/docker-compose.override.yml" \
  --env-file "$LAB_ENV_FILE" \
  up -d --build

# ---- 4. provision SIP inbound trunk + dispatch rule -----------------
# The trunk accepts INVITEs from 127.0.0.1 (Asterisk) with any called-number.
# The dispatch rule creates a fresh room per call and assigns the ivr-agent
# worker to it (matched by agent_name in agent.py).
#
# Uses the livekit-cli image for a one-shot idempotent apply. Names are
# stable ids, so re-running skips creation if they already exist.
echo "==> waiting for livekit-server to accept API calls"
for _ in {1..30}; do
  if curl -sf http://127.0.0.1:7880/ >/dev/null 2>&1; then break; fi
  sleep 1
done

# livekit-cli talks to the server over loopback (127.0.0.1:7880 is exposed by
# livekit-server). --network host so the container reaches the host binding.
LK_CLI() {
  $SUDO docker run --rm --network host \
    -e LIVEKIT_URL="http://127.0.0.1:7880" \
    -e LIVEKIT_API_KEY="$LIVEKIT_API_KEY" \
    -e LIVEKIT_API_SECRET="$LIVEKIT_API_SECRET" \
    livekit/livekit-cli:latest -y "$@"
}

# List existing to keep this idempotent — CLI errors if the name already exists.
existing_trunks=$(LK_CLI sip inbound list 2>/dev/null || true)
if echo "$existing_trunks" | grep -q "asterisk-inbound"; then
  echo "  trunk 'asterisk-inbound' already exists — skip"
else
  LK_CLI sip inbound create --name asterisk-inbound --numbers 1099
fi

# Dispatch rule provisioning via the Python livekit-api SDK (bundled in the
# agent container). We tried `lk sip dispatch create` first — as of CLI 2.16
# the flag form (--individual) and the stdin JSON form both hit
# "twirp error: missing rule", likely because the CLI's request shape drifted
# from the current server proto. Python bindings, being generated from the
# same proto tree the server uses, avoid the guesswork.
$SUDO docker exec \
  -e LIVEKIT_URL="ws://lk-server:7880" \
  -e LIVEKIT_API_KEY="$LIVEKIT_API_KEY" \
  -e LIVEKIT_API_SECRET="$LIVEKIT_API_SECRET" \
  lk-agent python -c '
import asyncio
from livekit import api

async def main():
    lk = api.LiveKitAPI()
    try:
        rules = await lk.sip.list_sip_dispatch_rule(api.ListSIPDispatchRuleRequest())
        if any(r.name == "ivr-per-call" for r in rules.items):
            print("  dispatch rule ivr-per-call already exists — skip")
            return
        req = api.CreateSIPDispatchRuleRequest(
            name="ivr-per-call",
            rule=api.SIPDispatchRule(
                dispatch_rule_individual=api.SIPDispatchRuleIndividual(room_prefix="call-"),
            ),
        )
        rule = await lk.sip.create_sip_dispatch_rule(req)
        print(f"  created dispatch rule {rule.sip_dispatch_rule_id} ({rule.name})")
    finally:
        await lk.aclose()

asyncio.run(main())
'

echo
echo "done. LiveKit voicebot stack running. verify:"
echo "  docker compose -f $HERE/docker-compose.yml ps"
echo "  docker logs lk-agent --tail=50"
echo "  sudo asterisk -rx 'pjsip show endpoint livekit-trunk'"
echo "  # then dial 1099 from a registered softphone"
