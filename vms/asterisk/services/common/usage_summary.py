"""Summarise voicebot usage.jsonl → totals and estimated USD cost per lane.

Run on the VM (where /var/lib/voicebot/usage.jsonl lives):
  python3 services/common/usage_summary.py                  # all providers
  python3 services/common/usage_summary.py --provider openai
  python3 services/common/usage_summary.py --since 1h

Prices are best-effort snapshots (Q3 2026). Update the PRICE table when
a provider revises rates; this file is the single source of truth.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

DEFAULT_LOG = Path("/var/lib/voicebot/usage.jsonl")

# (provider, op, unit_type) -> USD per unit.
# Sources:
#   OpenAI:    https://openai.com/api/pricing/
#   ElevenLabs https://elevenlabs.io/pricing (Turbo v2.5 / Multilingual v2)
PRICE = {
    # OpenAI tts-1: $15 / 1M chars
    ("openai", "tts", "chars"): 15.0 / 1_000_000,
    # OpenAI whisper-1: $0.006 / min = $0.0001 / sec
    ("openai", "stt", "seconds"): 0.006 / 60,
    # OpenAI gpt-4o-mini: $0.15 / 1M input, $0.60 / 1M output
    ("openai", "chat", "tokens_in"): 0.15 / 1_000_000,
    ("openai", "chat", "tokens_out"): 0.60 / 1_000_000,
    # ElevenLabs Flash v2.5 (our default): 0.5 credits/char → ~$0.15 / 1000 chars
    # on the Creator tier. Turbo v2.5 costs 1x (~$0.30/1000), Multilingual v2 is 2x.
    # This estimate assumes Flash; if you switch models, bump this rate.
    ("elevenlabs", "tts", "chars"): 0.15 / 1_000,
}


def parse_since(spec: str) -> float:
    """Return an epoch cutoff for '1h', '30m', '2d' style suffixes."""
    m = re.match(r"^(\d+)([smhd])$", spec)
    if not m:
        raise ValueError(f"invalid --since: {spec!r} (use 30s, 5m, 1h, 2d)")
    n, unit = int(m.group(1)), m.group(2)
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return time.time() - n * mult


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--log", type=Path, default=DEFAULT_LOG)
    p.add_argument("--provider", help="filter to one provider")
    p.add_argument("--since", help="only rows from the last <N>[smhd]")
    args = p.parse_args()

    if not args.log.exists():
        print(f"no log at {args.log}", file=sys.stderr)
        return 1
    cutoff = parse_since(args.since) if args.since else 0

    # (lane, provider, stage, model, op, unit_type) -> totals
    totals: dict[tuple[str, str, str, str, str, str], float] = defaultdict(float)
    costs: dict[tuple[str, str, str, str, str, str], float] = defaultdict(float)
    counts: dict[tuple[str, str, str, str, str, str], int] = defaultdict(int)

    with args.log.open() as f:
        for line in f:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("ts", 0) < cutoff:
                continue
            if args.provider and row.get("provider") != args.provider:
                continue
            key = (
                row.get("lane") or "unknown",
                row["provider"],
                row.get("stage") or row.get("op") or "unknown",
                row.get("model") or "unknown",
                row["op"],
                row["unit_type"],
            )
            totals[key] += float(row["units"])
            if row.get("estimated_usd") is not None:
                costs[key] += float(row["estimated_usd"])
            counts[key] += 1

    if not totals:
        print("(no matching records)")
        return 0

    header = (
        f"{'lane':<9} {'provider':<12} {'stage':<8} {'model':<18} "
        f"{'op':<8} {'unit_type':<16} {'events':>7} {'units':>14} {'est USD':>10}"
    )
    print(header)
    print("-" * len(header))
    grand = 0.0
    for key in sorted(totals):
        lane, provider, stage, model, op, unit_type = key
        units = totals[key]
        cost = costs[key] if costs[key] else None
        if cost is None:
            rate = PRICE.get((provider, op, unit_type))
            cost = units * rate if rate is not None else None
        cost_s = f"${cost:>9.4f}" if cost is not None else "         ?"
        if cost:
            grand += cost
        model_s = model if len(model) <= 18 else model[:17] + "…"
        print(
            f"{lane:<9} {provider:<12} {stage:<8} {model_s:<18} "
            f"{op:<8} {unit_type:<16} {counts[key]:>7} {units:>14,.2f} {cost_s:>10}"
        )
    print("-" * len(header))
    print(f"{'TOTAL':<{len(header) - 11}} ${grand:>9.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
