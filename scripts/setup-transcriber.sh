#!/usr/bin/env bash
# Install the local-Whisper transcriber (venv + watcher systemd service)
# on a Debian 13 / Ubuntu 26.04 host. Idempotent.
#
# Layout produced:
#   /opt/transcriber/venv/                  Python virtualenv with openai-whisper + torch
#   /opt/transcriber/{watcher,transcribe}.py
#   /etc/systemd/system/transcriber.service
#   /var/lib/asterisk/.cache/whisper/       pre-downloaded model
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPDIR=/opt/transcriber
VENV=$APPDIR/venv
# `base` is the watcher.py default and hallucinates on 8 kHz telephony audio;
# override at deploy time (e.g. WHISPER_MODEL=small make deploy) to bake a
# better model into the systemd drop-in written below. Leaving LANGUAGE empty
# means auto-detect; set to "en", "tr", … to force.
MODEL="${WHISPER_MODEL:-base}"
LANGUAGE="${WHISPER_LANGUAGE:-}"

SUDO=$([ "$(id -u)" -eq 0 ] && echo "" || echo "sudo")

as_user() {
  local user="$1"; shift
  if [ "$(id -u)" -eq 0 ]; then
    runuser -u "$user" -- "$@"
  else
    sudo -u "$user" "$@"
  fi
}

echo "==> apt: python venv + ffmpeg (whisper dependency)"
$SUDO apt-get update -qq
DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y --no-install-recommends \
  python3 python3-venv python3-pip ffmpeg

if ! getent passwd asterisk >/dev/null; then
  echo "ERROR: asterisk system user not found. Run install.sh first." >&2
  exit 1
fi

echo "==> app dir $APPDIR"
$SUDO install -d -m 0755 "$APPDIR"
$SUDO install -m 0755 "$REPO_ROOT/scripts/watcher.py"    "$APPDIR/watcher.py"
$SUDO install -m 0755 "$REPO_ROOT/scripts/transcribe.py" "$APPDIR/transcribe.py"

echo "==> venv at $VENV (openai-whisper)"
[ -d "$VENV" ] || $SUDO python3 -m venv "$VENV"
# /tmp is often a small tmpfs; torch wheel + build dir overflows it.
# Point pip's temp/cache at /var/tmp on the real disk.
$SUDO install -d -m 1777 /var/tmp/pip-build /var/tmp/pip-cache
PIP_ENV=(env TMPDIR=/var/tmp PIP_CACHE_DIR=/var/tmp/pip-cache)
$SUDO "${PIP_ENV[@]}" "$VENV/bin/pip" install --upgrade pip
$SUDO "${PIP_ENV[@]}" "$VENV/bin/pip" install -r "$REPO_ROOT/scripts/requirements.txt"

echo "==> pre-download whisper model '$MODEL' into asterisk's cache"
$SUDO install -d -o asterisk -g asterisk -m 0755 /var/lib/asterisk/.cache
as_user asterisk env HOME=/var/lib/asterisk XDG_CACHE_HOME=/var/lib/asterisk/.cache \
  "$VENV/bin/python" -c "import whisper; whisper.load_model('$MODEL')"

echo "==> systemd unit"
$SUDO install -m 0644 "$REPO_ROOT/asterisk/transcriber.service" \
  /etc/systemd/system/transcriber.service

echo "==> systemd drop-in: WHISPER_MODEL=$MODEL WHISPER_LANGUAGE=${LANGUAGE:-<auto-detect>}"
$SUDO install -d -m 0755 /etc/systemd/system/transcriber.service.d
{
  echo "[Service]"
  echo "Environment=WHISPER_MODEL=$MODEL"
  if [ -n "$LANGUAGE" ]; then
    echo "Environment=WHISPER_LANGUAGE=$LANGUAGE"
  fi
} | $SUDO tee /etc/systemd/system/transcriber.service.d/model.conf >/dev/null

$SUDO systemctl daemon-reload
$SUDO systemctl enable --now transcriber.service
$SUDO systemctl restart transcriber.service

echo
echo "done. verify:"
echo "  systemctl status transcriber --no-pager"
echo "  journalctl -u transcriber -n 50 --no-pager"
echo "  ls /var/spool/asterisk/monitor/*.txt"
