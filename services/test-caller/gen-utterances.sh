#!/usr/bin/env bash
# Generate WAV files from utterances.tsv via ElevenLabs TTS.
# Output: audio/<id>.wav (mono, 16 kHz, 16-bit signed little-endian).
# Each generation is also logged to /var/lib/voicebot/usage.jsonl so the
# cost dashboard sees ElevenLabs character usage alongside the OpenAI
# spend from the agent lanes.
#
# Idempotent: skips ids whose WAV already exists and is non-empty.
# Force regenerate with FORCE=1.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
cd "$HERE"

# shellcheck source=/dev/null
. "$REPO_ROOT/scripts/lib/env.sh"
load_lab_env "$REPO_ROOT"
: "${ELEVENLABS_API_KEY:?ELEVENLABS_API_KEY not set in the lab env file}"
: "${ELEVENLABS_VOICE_ID:?ELEVENLABS_VOICE_ID not set in the lab env file (e.g. a Turkish voice)}"
# Flash v2.5 is the current low-latency / low-cost Turkish-capable model.
# Alternatives: eleven_turbo_v2_5 (mid) or eleven_multilingual_v2 (highest fidelity).
: "${ELEVENLABS_MODEL_ID:=eleven_flash_v2_5}"

command -v curl >/dev/null   || { echo "curl not installed"; exit 1; }
command -v ffmpeg >/dev/null || { echo "ffmpeg not installed (apt install ffmpeg)"; exit 1; }
command -v python3 >/dev/null || { echo "python3 required for usage logging"; exit 1; }

mkdir -p audio
USAGE_LOG="${VOICEBOT_USAGE_LOG:-/var/lib/voicebot/usage.jsonl}"
sudo mkdir -p "$(dirname "$USAGE_LOG")" 2>/dev/null || mkdir -p "$(dirname "$USAGE_LOG")" 2>/dev/null || true

# Skip header row; iterate <id>\t<text> lines.
tail -n +2 utterances.tsv | while IFS=$'\t' read -r id text; do
  [ -z "$id" ] && continue
  out="audio/${id}.wav"
  if [ "${FORCE:-0}" != "1" ] && [ -s "$out" ]; then
    echo "  skip  $id  (audio/$id.wav exists)"
    continue
  fi

  chars=${#text}
  echo "==> $id  ($chars chars)  \"$text\""

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
    continue
  fi

  # Wrap the raw PCM in a WAV header (ffmpeg is the cheapest way).
  ffmpeg -nostdin -y -loglevel error -f s16le -ar 16000 -ac 1 -i "$raw" -c:a pcm_s16le "$out"
  rm -f "$raw"

  # Log the character spend so usage_summary.py picks it up.
  python3 -c "
import sys; sys.path.insert(0, '$REPO_ROOT/services/common')
import usage
usage.record(provider='elevenlabs', op='tts', units=$chars, unit_type='chars',
             ref='$id', extra={'model': '$ELEVENLABS_MODEL_ID'})
" || echo "  (usage log write failed — file permissions?)"
done

echo
echo "done. files in $HERE/audio/"
ls -la audio/
