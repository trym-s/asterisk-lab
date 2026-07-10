#!/usr/bin/env bash
# Dial once per conversation_id in conversations.tsv, play every turn's WAV
# in sequence without hanging up between turns, log per-call metrics, and
# print a summary. Drives the currently running baresip via its ctrl_tcp
# module (127.0.0.1:4444 by default) — the operator's baresip must already
# be registered as 1001 (or whichever caller ext) before invoking.
#
# One-time baresip setup: add `module ctrl_tcp.so` to ~/.baresip/config, then
# restart baresip. Verify with `ss -ltnp | grep 4444`.
#
# Usage:
#   ./run-suite.sh                  # Pipecat lane (ext 1098)
#   TARGET=1098 SETTLE=5 ./run-suite.sh
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

TARGET="${1:-${TARGET:-1098}}"
CTRL_HOST="${CTRL_HOST:-127.0.0.1}"
CTRL_PORT="${CTRL_PORT:-4444}"
# Seconds to wait AFTER the WAV ends before hanging up — long enough for the
# agent to answer AND finish speaking. With the streaming Soniox pipeline the
# reply starts ~1s after the utterance ends; 15s still bounds a long
# multi-sentence spoken reply. Lower it once live evidence shows the real
# per-turn ceiling.
SETTLE="${SETTLE:-15}"
# Seconds between /dial firing and the WAV being made the audio source.
# Without this, ausrc is set and dial fires while the bot's greeting is still
# playing back on the caller side; the bot's VAD is holding its own turn and
# doesn't hear the WAV cleanly — Whisper transcribes only the tail. 3 s covers
# the ~1 s SIP setup + a ~2 s "Merhaba, Mavi Kapı..." greeting.
PREROLL="${PREROLL:-3}"
LOG_DIR="$HERE/runs/$(date +%Y%m%d-%H%M%S)-$TARGET"
mkdir -p "$LOG_DIR"

# ---- ctrl_tcp helpers -----------------------------------------------
# Protocol: netstring framing. `<len>:<payload>,` where payload is JSON like
# {"command":"dial","params":"1099","token":"tok1"}.
send_cmd() {
  local cmd="$1" params="$2"
  local payload="{\"command\":\"$cmd\",\"params\":\"$params\",\"token\":\"t$$\"}"
  local frame="${#payload}:${payload},"
  printf '%s' "$frame" | nc -q1 -w2 "$CTRL_HOST" "$CTRL_PORT" || true
}

# ---- preflight ------------------------------------------------------
if ! (echo >/dev/tcp/"$CTRL_HOST"/"$CTRL_PORT") 2>/dev/null; then
  echo "ERROR: baresip ctrl_tcp not reachable at $CTRL_HOST:$CTRL_PORT"
  echo "Fix: add 'module ctrl_tcp.so' to ~/.baresip/config and restart baresip"
  exit 1
fi
command -v nc >/dev/null || { echo "nc (netcat) required"; exit 1; }

SILENCE="$HERE/audio/00-silence.wav"
[ -f "$SILENCE" ] || {
  echo "==> generating 2 s silence WAV at $SILENCE (used as pre-source)";
  ffmpeg -y -loglevel error -f lavfi -i "anullsrc=r=16000:cl=mono" -t 2 \
    -c:a pcm_s16le "$SILENCE";
}

shopt -s nullglob
# One row per turn: conversation_id, turn_index, utterance_id, text.
mapfile -t rows < <(tail -n +2 "$HERE/conversations.tsv")
[ ${#rows[@]} -gt 0 ] || { echo "no rows in $HERE/conversations.tsv"; exit 1; }

# Group rows into ordered turn lists per conversation_id, preserving file order.
conv_ids=()
declare -A conv_turns=()
for row in "${rows[@]}"; do
  IFS=$'\t' read -r conv_id _turn_index utterance_id _text <<<"$row"
  [ -z "$conv_id" ] && continue
  if [ -z "${conv_turns[$conv_id]:-}" ]; then
    conv_ids+=("$conv_id")
  fi
  conv_turns[$conv_id]="${conv_turns[$conv_id]:-}${conv_turns[$conv_id]:+ }$utterance_id"
done

echo "==> target ext: $TARGET  |  conversations: ${#conv_ids[@]}  |  log dir: $LOG_DIR"
echo

# Make sure the aufile ausrc/auplay module is loaded. Baresip drops it on
# restart if the config doesn't include `module aufile.so`, and without it
# every `/ausrc aufile,...` silently no-ops → the caller side stays on
# ALSA, the bot's own TTS loops back through the host speakers, and Whisper
# transcribes hallucinations from the feedback. Idempotent: baresip returns
# "already loaded" the second time.
send_cmd insmod "aufile"
sleep 0.2

# ---- run loop -------------------------------------------------------
# One dial per conversation_id: all of that conversation's turn WAVs play in
# sequence, back to back, so the agent can carry context turn to turn; we
# hang up only after the last turn's WAV plus its settle window.
for conv_id in "${conv_ids[@]}"; do
  read -ra turn_ids <<<"${conv_turns[$conv_id]}"
  echo "==> conversation: $conv_id  |  turns: ${#turn_ids[@]}"

  # Set source to a 2 s silence WAV first, THEN dial. This prevents the host
  # ALSA mic (default source at boot) from feeding speaker echo of the bot's
  # greeting back through Whisper — the exact feedback loop that produced
  # bogus "Merhaba, sizi duyabiliyorum" transcriptions before we caught it.
  # After PREROLL (bot greeting done), switch to the first turn's utterance.
  send_cmd ausrc "aufile,$SILENCE"
  sleep 0.2
  send_cmd dial "$TARGET"
  sleep "$PREROLL"

  turn_n=0
  for utterance_id in "${turn_ids[@]}"; do
    turn_n=$((turn_n + 1))
    wav="$HERE/audio/${utterance_id}.wav"
    [ -f "$wav" ] || { echo "  ERROR: missing $wav"; exit 1; }
    # Duration used to time the next turn (or the final hangup); falls back
    # to 5s if ffprobe missing.
    dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$wav" 2>/dev/null || echo 5)
    dur_int=${dur%.*}

    printf "  [%d/%d] %-25s dur=%.1fs  settle=%ds\n" "$turn_n" "${#turn_ids[@]}" "$utterance_id" "$dur" "$SETTLE"

    send_cmd ausrc "aufile,$wav"
    sleep "$dur_int"

    # Park the source back on the silence primer while the agent replies.
    # (The old LiveKit SIP gateway needed this re-armed every second to
    # defeat its RTP-inactivity watchdog; AudioSocket has no such watchdog,
    # so a single re-arm plus a plain wait is enough.)
    send_cmd ausrc "aufile,$SILENCE"
    sleep "$SETTLE"
  done

  send_cmd hangup ""
  sleep 2  # tail-end teardown + settle before next conversation's dial
done

# ---- summary --------------------------------------------------------
echo
echo "==> local usage delta (${#rows[@]} turns across ${#conv_ids[@]} conversations gen'd earlier)"
python3 "$REPO_ROOT/vms/asterisk/services/common/usage_summary.py" \
  --log "$HOME/.local/state/voicebot/usage.jsonl" --since 1h 2>&1 || true

echo
echo "==> remote usage delta (Pipecat agent lane)"
ssh deb@192.168.122.247 \
  "python3 /opt/asterisk-lab/current/vms/asterisk/services/common/usage_summary.py --since 5m" 2>&1 || \
  echo "  (couldn't reach VM — run manually: make usage-summary)"

echo
echo "done. VM-side agent logs since suite:"
echo "  ssh deb@192.168.122.247 'sudo docker logs pc-agent --since 5m'"
