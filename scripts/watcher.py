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


def already_done(wav_path: Path) -> bool:
    return wav_path.with_suffix(".txt").exists()


def is_file_stable(wav_path: Path, wait: float = 1.5) -> bool:
    # Asterisk may still be writing; wait for size to settle.
    size1 = wav_path.stat().st_size
    time.sleep(wait)
    size2 = wav_path.stat().st_size
    return size1 == size2 and size1 > 0


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
