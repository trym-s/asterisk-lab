"""Render /var/lib/voicebot/turns.jsonl as a human-readable transcript.

Usage on the VM:
  python3 services/common/tail_turns.py           # last 20 min, all rooms
  python3 services/common/tail_turns.py --since 3m
  python3 services/common/tail_turns.py --room call-_1001_xyz

Groups events by SIP room (one turn cluster per phone call), keeps them in
timestamp order within each room, and prints:
  * USER  — what Whisper heard
  * TOOL  — the function call plus its retrieved snippet
  * LLM   — the raw model output that went to TTS
  * AGENT — the utterance actually committed to the caller's ear

Empty `llm_out` records (the tool-call turn) are collapsed into a marker
`(→ decided to call tool)` so the flow reads left-to-right without noise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DEFAULT_LOG = Path("/var/lib/voicebot/turns.jsonl")


def parse_since(spec: str) -> float:
    m = re.match(r"^(\d+)([smhd])$", spec)
    if not m:
        raise ValueError(f"invalid --since: {spec!r}")
    n, unit = int(m.group(1)), m.group(2)
    return time.time() - n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def _t(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def render_room(room: str, events: list[dict]) -> None:
    print(f"\n\033[1;36m=== {room or '(no room)'} ===\033[0m")
    events.sort(key=lambda e: e["ts"])
    for e in events:
        kind = e["kind"]
        ts = _t(e["ts"])
        if kind == "user_speech":
            print(f"  [{ts}] \033[33mUSER\033[0m   {e.get('text', '')}")
        elif kind == "tool_call":
            q = e.get("query", "?")
            res = (e.get("result") or "").replace("\n", "\n           ")
            print(f"  [{ts}] \033[35mTOOL\033[0m   {e.get('tool', '?')}(query={q!r})")
            print(f"           \033[2m{res}\033[0m")
        elif kind == "llm_in":
            n = len(e.get("messages") or [])
            fns = e.get("functions") or []
            print(f"  [{ts}] \033[2mLLM IN  {n} msgs, fns={fns}\033[0m")
        elif kind == "llm_out":
            txt = e.get("text", "")
            if not txt.strip():
                print(f"  [{ts}] \033[2mLLM OUT (→ tool call, no text)\033[0m")
            else:
                print(f"  [{ts}] \033[34mLLM\033[0m    {txt}")
        elif kind == "agent_speech":
            print(f"  [{ts}] \033[32mAGENT\033[0m  {e.get('text', '')}")
        else:
            print(f"  [{ts}] {kind}  {e}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--log", type=Path, default=DEFAULT_LOG)
    p.add_argument("--since", default="20m",
                   help="only rows from the last <N>[smhd] (default 20m)")
    p.add_argument("--room", help="filter to one room name (substring match)")
    args = p.parse_args()

    if not args.log.exists():
        print(f"no log at {args.log}", file=sys.stderr)
        return 1
    cutoff = parse_since(args.since)

    # tool_call events have room="" because the FunctionContext method
    # doesn't get the ctx bound the same way — pin them to the most recent
    # room seen so they show up in the right transcript.
    grouped: dict[str, list[dict]] = defaultdict(list)
    last_room = ""
    for line in args.log.open():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("ts", 0) < cutoff:
            continue
        room = e.get("room") or last_room
        if e.get("room"):
            last_room = e["room"]
        if args.room and args.room not in room:
            continue
        grouped[room].append(e)

    for room in sorted(grouped, key=lambda r: min(e["ts"] for e in grouped[r])):
        render_room(room, grouped[room])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
