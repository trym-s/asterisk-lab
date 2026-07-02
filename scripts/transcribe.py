#!/usr/bin/env python3
"""Transcribe a single WAV recording using a local Whisper model."""

import sys
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print("usage: transcribe.py <wav_path>")
        sys.exit(1)

    wav_path = Path(sys.argv[1])
    if not wav_path.exists():
        print(f"error: file not found: {wav_path}")
        sys.exit(1)

    import whisper
    model = whisper.load_model("small")

    result = model.transcribe(str(wav_path))
    text = result["text"].strip()

    output_path = wav_path.with_suffix(".txt")
    output_path.write_text(text, encoding="utf-8")

    print(text)
    print(f"wrote {output_path}")


if __name__ == "__main__":
    main()
