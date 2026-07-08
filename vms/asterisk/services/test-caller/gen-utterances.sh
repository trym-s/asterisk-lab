#!/usr/bin/env bash
# Generate WAV files from conversations.tsv via ElevenLabs TTS.
# Output: audio/<utterance_id>.wav (mono, 16 kHz, 16-bit signed little-endian),
# one WAV per turn.
# Each generation is also logged to /var/lib/voicebot/usage.jsonl so the
# cost dashboard sees ElevenLabs character usage alongside the OpenAI
# spend from the agent lanes.
#
# Idempotent: skips ids whose WAV already exists, is non-empty, and passes
# the truncation guard. Force regenerate with FORCE=1.
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
cd "$HERE"

# shellcheck source=/dev/null
. "$REPO_ROOT/infra/scripts/lib/env.sh"
load_lab_env "$REPO_ROOT"
: "${ELEVENLABS_API_KEY:?ELEVENLABS_API_KEY not set in the lab env file}"
: "${ELEVENLABS_VOICE_ID:?ELEVENLABS_VOICE_ID not set in the lab env file (e.g. a Turkish voice)}"
# Multilingual v2 is the highest-fidelity Turkish-capable model; flash v2.5
# is lower latency/cost but produced audible mid-sentence truncation on this
# corpus. Alternatives: eleven_turbo_v2_5 (mid), eleven_flash_v2_5 (fastest).
: "${ELEVENLABS_MODEL_ID:=eleven_multilingual_v2}"

command -v curl >/dev/null   || { echo "curl not installed"; exit 1; }
command -v ffmpeg >/dev/null || { echo "ffmpeg not installed (apt install ffmpeg)"; exit 1; }
command -v python3 >/dev/null || { echo "python3 required for usage logging"; exit 1; }

mkdir -p audio
USAGE_LOG="${VOICEBOT_USAGE_LOG:-/var/lib/voicebot/usage.jsonl}"
sudo mkdir -p "$(dirname "$USAGE_LOG")" 2>/dev/null || mkdir -p "$(dirname "$USAGE_LOG")" 2>/dev/null || true

# Truncation guard: ElevenLabs synthesis (or the raw-PCM-to-WAV conversion
# below) occasionally cuts a sentence off mid-word instead of ending in
# natural trailing silence. silencedetect finds every silence_start in the
# clip; if the last one isn't within 1.5s of the clip's end, the audio is
# still "talking" when it stops - treat that as truncated.
check_trailing_silence() {
  local wav="$1"
  local dur last_start
  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$wav" 2>/dev/null || echo 0)
  last_start=$(ffmpeg -nostdin -i "$wav" -af silencedetect=noise=-35dB:d=0.3 -f null - 2>&1 \
    | grep -oP 'silence_start: \K[0-9.]+' | tail -n1 || true)
  [ -z "$last_start" ] && return 1
  python3 -c "import sys; sys.exit(0 if float('$dur') - float('$last_start') <= 1.5 else 1)"
}

# Skip header row; iterate <conversation_id>\t<turn_index>\t<utterance_id>\t<text> lines.
tail -n +2 conversations.tsv | while IFS=$'\t' read -r conversation_id turn_index utterance_id text; do
  [ -z "$utterance_id" ] && continue
  out="audio/${utterance_id}.wav"
  if [ "${FORCE:-0}" != "1" ] && [ -s "$out" ] && check_trailing_silence "$out"; then
    echo "  skip  $utterance_id  (audio/$utterance_id.wav exists and passes truncation guard)"
    continue
  fi

  chars=${#text}
  echo "==> $conversation_id#$turn_index $utterance_id  ($chars chars)  \"$text\""

  for attempt in 1 2; do
    # ElevenLabs returns MP3 by default; ask for pcm_16000 to skip a transcode.
    # output_format=pcm_16000 → raw 16-bit LE PCM, 16 kHz, mono.
    raw=$(mktemp --suffix=.raw)
    http_code=$(curl -sS -o "$raw" -w "%{http_code}" \
      -X POST "https://api.elevenlabs.io/v1/text-to-speech/${ELEVENLABS_VOICE_ID}?output_format=pcm_16000" \
      -H "xi-api-key: ${ELEVENLABS_API_KEY}" \
      -H "Content-Type: application/json" \
      --data "$(python3 -c 'import json,sys; print(json.dumps({"text":sys.argv[1],"model_id":sys.argv[2]}))' "$text" "$ELEVENLABS_MODEL_ID")")

    if [ "$http_code" != "200" ]; then
      echo "  ERROR: HTTP $http_code"
      head -c 400 "$raw"; echo
      rm -f "$raw"
      break
    fi

    # Wrap the raw PCM in a WAV header (ffmpeg is the cheapest way).
    ffmpeg -nostdin -y -loglevel error -f s16le -ar 16000 -ac 1 -i "$raw" -c:a pcm_s16le "$out"
    rm -f "$raw"

    if check_trailing_silence "$out"; then
      break
    fi
    if [ "$attempt" -eq 2 ]; then
      echo "  ERROR: $utterance_id still looks truncated after $attempt attempts (no trailing silence before end of clip)" >&2
      rm -f "$out"
      exit 1
    fi
    echo "  WARN: $utterance_id looks truncated (no trailing silence) - regenerating (attempt 2/2)"
  done

  # Log the character spend so usage_summary.py picks it up.
  python3 -c "
import sys; sys.path.insert(0, '$REPO_ROOT/vms/asterisk/services/common')
import usage
usage.record(provider='elevenlabs', op='tts', units=$chars, unit_type='chars',
             ref='$utterance_id', extra={'model': '$ELEVENLABS_MODEL_ID', 'conversation_id': '$conversation_id'})
" || echo "  (usage log write failed — file permissions?)"
done

echo
echo "done. files in $HERE/audio/"
ls -la audio/
