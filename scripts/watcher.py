#!/usr/bin/env python3
"""Watch a directory for new WAV files and transcribe each with Whisper."""

import os
import sys
import time
from pathlib import Path

import whisper

WATCH_DIR = Path(os.environ.get("WATCH_DIR", "/var/spool/asterisk/monitor"))
MODEL_NAME = os.environ.get("WHISPER_MODEL", "base")
LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "tr")
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "2"))

# Stability gate: a WAV is only considered "done" once its size has stayed
# unchanged across STABLE_SAMPLES consecutive checks at STABLE_INTERVAL apart
# AND it is at least STABLE_MIN_SIZE bytes. Reason: MixMonitor opens the WAV
# at call start (44-byte header) and only appends audio frames as the call
# progresses. A naive single-sample size==size check can race-trip on the
# header-only window right after the file appears — the watcher then writes
# an empty/near-empty transcript while the call is still ongoing.
STABLE_SAMPLES = int(os.environ.get("STABLE_SAMPLES", "3"))
STABLE_INTERVAL = float(os.environ.get("STABLE_INTERVAL", "2"))
STABLE_MIN_SIZE = int(os.environ.get("STABLE_MIN_SIZE", "1024"))
# Cap the time spent waiting for one file to settle, so a stuck WAV (failed
# call, truncated capture) does not block the watcher forever.
STABLE_MAX_WAIT = float(os.environ.get("STABLE_MAX_WAIT", "600"))


def already_done(wav_path: Path) -> bool:
    return wav_path.with_suffix(".txt").exists()


def is_file_stable(wav_path: Path) -> bool:
    deadline = time.monotonic() + STABLE_MAX_WAIT
    last_size = -1
    stable_count = 0
    while time.monotonic() < deadline:
        try:
            size = wav_path.stat().st_size
        except FileNotFoundError:
            return False
        if size < STABLE_MIN_SIZE:
            stable_count = 0
        elif size == last_size:
            stable_count += 1
            if stable_count >= STABLE_SAMPLES:
                return True
        else:
            stable_count = 0
        last_size = size
        time.sleep(STABLE_INTERVAL)
    return False


def transcribe(model, wav_path: Path) -> None:
    print(f"transcribing {wav_path}", flush=True)
    result = model.transcribe(str(wav_path), language=LANGUAGE)
    text = result["text"].strip()
    out_path = wav_path.with_suffix(".txt")
    out_path.write_text(text, encoding="utf-8")
    print(f"wrote {out_path}", flush=True)


def main() -> None:
    print(f"loading whisper model: {MODEL_NAME}", flush=True)
    model = whisper.load_model(MODEL_NAME)
    print(f"watching {WATCH_DIR}", flush=True)

    seen: set[Path] = set()

    while True:
        try:
            for wav_path in WATCH_DIR.glob("*.wav"):
                if wav_path in seen or already_done(wav_path):
                    continue
                try:
                    if is_file_stable(wav_path):
                        transcribe(model, wav_path)
                        seen.add(wav_path)
                except Exception as e:
                    print(f"error processing {wav_path}: {e}", file=sys.stderr, flush=True)
        except FileNotFoundError:
            print(f"watch dir missing: {WATCH_DIR}", file=sys.stderr, flush=True)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
