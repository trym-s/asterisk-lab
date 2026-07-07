"""Append-only usage log for voicebot LLM/TTS/STT API calls.

Both agent stacks (LiveKit, Pipecat) and the test-caller share this so a
single `usage_summary` run can compute totals across the whole lab. Each
record is one JSON line — no schema migrations, easy to `jq`.

Write path is fixed to /var/lib/voicebot/usage.jsonl inside the container;
the host mounts /var/lib/voicebot on the VM as a bind volume so records
survive container recreations.

Cost fields are row metadata. The first trace foundation records the pricing
version even when estimated_usd is null; final provider pricing decisions are
handled by the later model/cost goal.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import voicebot_profile

def _default_log_path() -> Path:
    """Pick a writable log path.

    /var/lib/voicebot/usage.jsonl is the canonical VM path (created by
    services/livekit/install.sh, owned by root — writable by root-run
    containers). When record() is called from an unprivileged host process
    (e.g. `./gen-utterances.sh` on a developer laptop) that dir doesn't
    exist and can't be created without sudo, so we fall back to a per-user
    file under $XDG_STATE_HOME.
    """
    env_override = os.environ.get("VOICEBOT_USAGE_LOG")
    if env_override:
        return Path(env_override)
    canonical = Path("/var/lib/voicebot/usage.jsonl")
    if canonical.parent.exists() and os.access(canonical.parent, os.W_OK):
        return canonical
    state = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
    return state / "voicebot" / "usage.jsonl"


LOG_PATH = _default_log_path()


def record(
    *,
    provider: str,
    op: str,
    units: float,
    unit_type: str,
    ref: str | None = None,
    extra: dict[str, Any] | None = None,
    lane: str | None = None,
    call_id: str | None = None,
    turn_id: str | None = None,
    stage: str | None = None,
    model: str | None = None,
    pricing_version: str | None = None,
    estimated_usd: float | None = None,
) -> None:
    """Append one usage event.

    provider   e.g. "openai", "elevenlabs"
    op         e.g. "tts", "stt", "chat"
    units      how many units consumed (chars, tokens, seconds)
    unit_type  units of `units` — "chars" | "seconds" | "tokens_in" | "tokens_out"
    ref        optional caller-supplied tag (call id, utterance id)
    extra      free-form dict, merged in
    """
    row: dict[str, Any] = {
        "ts": time.time(),
        "provider": provider,
        "op": op,
        "units": units,
        "unit_type": unit_type,
        "lane": lane,
        "call_id": call_id,
        "turn_id": turn_id,
        "stage": stage,
        "model": model,
        "estimated_usd": estimated_usd,
        "pricing_version": pricing_version or voicebot_profile.PRICING_VERSION,
    }
    if ref is not None:
        row["ref"] = ref
    if extra:
        row.update(extra)

    log_path = _default_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
