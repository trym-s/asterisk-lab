"""Canonical JSONL trace events for the voicebot lanes.

The acceptance specs use /var/lib/voicebot/events.jsonl as the source of
truth. This module is intentionally dependency-free so both containers and
local tests can use the same writer.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

EVENTS_VERSION = "voicebot-events-v1"

REQUIRED_KEYS = {
    "ts",
    "lane",
    "call_id",
    "turn_id",
    "stage",
    "event",
    "provider",
    "model",
    "duration_ms",
    "payload",
}

SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|authorization|bearer|livekit.*secret|password|secret|sip[_-]?password|token)",
    re.IGNORECASE,
)

SECRET_VALUE_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9._~-]{12,}|LK_[A-Za-z0-9_-]{12,})",
    re.IGNORECASE,
)

VALID_STAGES = {"call", "audio", "stt", "llm", "tool", "tts", "error"}


def default_events_path() -> Path:
    override = os.environ.get("VOICEBOT_EVENTS_LOG")
    if override:
        return Path(override)

    canonical = Path("/var/lib/voicebot/events.jsonl")
    if canonical.parent.exists() and os.access(canonical.parent, os.W_OK):
        return canonical

    state = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
    return state / "voicebot" / "events.jsonl"


def _redact_string(value: str) -> str:
    return SECRET_VALUE_RE.sub("[REDACTED]", value)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            key_s = str(key)
            if SECRET_KEY_RE.search(key_s):
                clean[key_s] = "[REDACTED]"
            else:
                clean[key_s] = redact(item)
        return clean
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _redact_string(str(value))


def new_turn_id(index: int) -> str:
    return f"turn-{index:04d}"


def current_run_id() -> str | None:
    """The operator-supplied comparison run id, if set.

    The operator sets VOICEBOT_RUN_ID identically before invoking
    run-suite.sh against each lane in turn, so both lanes' events carry the
    same value and the dashboard can pair them. Unset by default: a call
    without a run_id simply falls outside any paired comparison view.
    """
    return os.environ.get("VOICEBOT_RUN_ID") or None


class CallContext:
    """Small per-call turn id allocator shared by agent callbacks."""

    def __init__(self, lane: str, call_id: str):
        self.lane = lane
        self.call_id = call_id
        self.turn_index = 0
        self.current_turn_id: str | None = None

    def next_turn(self) -> str:
        self.turn_index += 1
        self.current_turn_id = new_turn_id(self.turn_index)
        return self.current_turn_id


def build_event(
    *,
    lane: str,
    call_id: str,
    stage: str,
    event: str,
    turn_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    duration_ms: float | int | None = None,
    payload: dict[str, Any] | None = None,
    ts: float | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    if stage not in VALID_STAGES:
        raise ValueError(f"invalid voicebot trace stage: {stage!r}")
    row = {
        "ts": time.time() if ts is None else ts,
        "lane": lane,
        "call_id": str(call_id),
        "turn_id": turn_id,
        "stage": stage,
        "event": event,
        "provider": provider,
        "model": model,
        "duration_ms": duration_ms,
        "payload": redact(payload or {}),
    }
    # Additive grouping key: only attached when the caller supplies
    # one, so existing rows/tests that don't pass run_id are unaffected.
    if run_id is not None:
        row["run_id"] = run_id
    missing = REQUIRED_KEYS - row.keys()
    if missing:
        raise ValueError(f"trace event missing required keys: {sorted(missing)}")
    return row


def record_event(
    *,
    lane: str,
    call_id: str,
    stage: str,
    event: str,
    turn_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    duration_ms: float | int | None = None,
    payload: dict[str, Any] | None = None,
    path: Path | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    row = build_event(
        lane=lane,
        call_id=call_id,
        turn_id=turn_id,
        stage=stage,
        event=event,
        provider=provider,
        model=model,
        duration_ms=duration_ms,
        payload=payload,
        run_id=run_id,
    )
    target = path or default_events_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return row


def record_error(
    *,
    lane: str,
    call_id: str,
    event: str,
    error: BaseException | str,
    turn_id: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    if isinstance(error, BaseException):
        payload = {"type": error.__class__.__name__, "message": str(error)}
    else:
        payload = {"message": error}
    return record_event(
        lane=lane,
        call_id=call_id,
        turn_id=turn_id,
        stage="error",
        event=event,
        provider=provider,
        model=model,
        payload=payload,
    )


def validate_event(row: dict[str, Any]) -> None:
    missing = REQUIRED_KEYS - row.keys()
    if missing:
        raise ValueError(f"trace event missing required keys: {sorted(missing)}")
    if row["stage"] not in VALID_STAGES:
        raise ValueError(f"invalid trace stage: {row['stage']!r}")
    if not isinstance(row["payload"], dict):
        raise ValueError("trace event payload must be an object")


def read_events(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            validate_event(row)
            rows.append(row)
    return rows
