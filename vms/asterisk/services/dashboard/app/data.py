"""Read-only aggregation over the voicebot JSONL sinks.

Data flows one direction: JSONL/spool files on disk -> this module ->
JSON endpoints -> Jinja2 pages. Nothing here writes back to the sinks.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import trace_events
import usage_summary

STAGE_ORDER = ["call", "audio", "stt", "llm", "tool", "tts", "error"]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def load_events(path: Path) -> list[dict[str, Any]]:
    """Read events.jsonl, skipping rows that fail schema validation."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                trace_events.validate_event(row)
            except (json.JSONDecodeError, ValueError):
                continue
            rows.append(row)
    return rows


def load_usage(path: Path) -> list[dict[str, Any]]:
    return _read_jsonl(path)


def load_turns(path: Path) -> list[dict[str, Any]]:
    return _read_jsonl(path)


def group_turns(events: list[dict[str, Any]]) -> dict[tuple[str, str, str], list[dict]]:
    """Group event rows by (lane, call_id, turn_id), each list ts-sorted.

    Rows without a turn_id (call-level events such as call.started) are not
    turns and are excluded.
    """
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for row in events:
        turn_id = row.get("turn_id")
        if not turn_id:
            continue
        key = (row["lane"], row["call_id"], turn_id)
        grouped.setdefault(key, []).append(row)
    for rows in grouped.values():
        rows.sort(key=lambda r: r["ts"])
    return grouped


def derive_stage_latency(turn_events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Approximate per-stage latency in ms from ts deltas.

    Orders the distinct stages by first occurrence, attributes the delta to
    the next distinct stage's first ts to the earlier stage. Prefers a real
    duration_ms already carried on the row (e.g. the `tool` stage) over the
    derived delta. The last stage in a turn has no following stage so its
    derived latency is left as None.
    """
    seen_ts: dict[str, float] = {}
    order: list[str] = []
    for row in turn_events:
        stage = row["stage"]
        if stage not in seen_ts:
            seen_ts[stage] = row["ts"]
            order.append(stage)

    result: dict[str, dict[str, Any]] = {}
    for i, stage in enumerate(order):
        measured = next(
            (
                row["duration_ms"]
                for row in turn_events
                if row["stage"] == stage and row.get("duration_ms") is not None
            ),
            None,
        )
        if measured is not None:
            result[stage] = {"ms": round(float(measured), 1), "source": "measured"}
            continue
        if i + 1 < len(order):
            delta_ms = (seen_ts[order[i + 1]] - seen_ts[stage]) * 1000
            result[stage] = {"ms": round(delta_ms, 1), "source": "approx"}
        else:
            result[stage] = {"ms": None, "source": "approx"}
    return result


def _first_text(turn_events: list[dict[str, Any]], stage: str, event: str) -> str | None:
    for row in turn_events:
        if row["stage"] == stage and row["event"] == event:
            text = row.get("payload", {}).get("text")
            if text:
                return text
    return None


def turn_summary(key: tuple[str, str, str], turn_events: list[dict[str, Any]]) -> dict[str, Any]:
    lane, call_id, turn_id = key
    latency = derive_stage_latency(turn_events)
    stt_text = _first_text(turn_events, "stt", "final_transcript")
    llm_text = _first_text(turn_events, "llm", "response")
    tts_text = _first_text(turn_events, "tts", "request")
    tool_calls = [
        {
            "event": row["event"],
            "payload": row.get("payload", {}),
            "duration_ms": row.get("duration_ms"),
        }
        for row in turn_events
        if row["stage"] == "tool"
    ]
    return {
        "lane": lane,
        "call_id": call_id,
        "turn_id": turn_id,
        "start_ts": turn_events[0]["ts"],
        "end_ts": turn_events[-1]["ts"],
        "stt_text": stt_text,
        "llm_text": llm_text,
        "tts_text": tts_text,
        "tool_calls": tool_calls,
        "latency_ms": latency,
    }


def list_calls(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per (lane, call_id): first/last ts and turn count."""
    calls: dict[tuple[str, str], dict[str, Any]] = {}
    for row in events:
        key = (row["lane"], row["call_id"])
        turn_ids = calls.setdefault(
            key,
            {
                "lane": row["lane"],
                "call_id": row["call_id"],
                "start_ts": row["ts"],
                "end_ts": row["ts"],
                "turn_ids": set(),
            },
        )
        turn_ids["start_ts"] = min(turn_ids["start_ts"], row["ts"])
        turn_ids["end_ts"] = max(turn_ids["end_ts"], row["ts"])
        if row.get("turn_id"):
            turn_ids["turn_ids"].add(row["turn_id"])

    result = []
    for entry in calls.values():
        result.append(
            {
                "lane": entry["lane"],
                "call_id": entry["call_id"],
                "start_ts": entry["start_ts"],
                "end_ts": entry["end_ts"],
                "turn_count": len(entry["turn_ids"]),
            }
        )
    result.sort(key=lambda c: c["start_ts"], reverse=True)
    return result


def turns_for_call(events: list[dict[str, Any]], call_id: str) -> list[dict[str, Any]]:
    call_events = [row for row in events if row["call_id"] == call_id]
    grouped = group_turns(call_events)
    turns = [turn_summary(key, rows) for key, rows in grouped.items()]
    turns.sort(key=lambda t: t["start_ts"])
    return turns


def cost_summary(usage_rows: list[dict[str, Any]], since_ts: float = 0) -> dict[str, Any]:
    """Aggregate cost/usage, mirroring usage_summary.py's grouping."""
    groups: dict[tuple[str, str, str, str, str, str], dict[str, Any]] = {}
    for row in usage_rows:
        if row.get("ts", 0) < since_ts:
            continue
        try:
            key = (
                row.get("lane") or "unknown",
                row["provider"],
                row.get("stage") or row.get("op") or "unknown",
                row.get("model") or "unknown",
                row["op"],
                row["unit_type"],
            )
        except KeyError:
            continue
        group = groups.setdefault(
            key,
            {
                "lane": key[0],
                "provider": key[1],
                "stage": key[2],
                "model": key[3],
                "op": key[4],
                "unit_type": key[5],
                "events": 0,
                "units": 0.0,
                "estimated_usd": 0.0,
                "has_estimate": False,
            },
        )
        group["events"] += 1
        group["units"] += float(row["units"])
        if row.get("estimated_usd") is not None:
            group["estimated_usd"] += float(row["estimated_usd"])
            group["has_estimate"] = True

    rows_out = []
    grand_total = 0.0
    for group in groups.values():
        if group["has_estimate"]:
            cost = group["estimated_usd"]
        else:
            rate = usage_summary.PRICE.get((group["provider"], group["op"], group["unit_type"]))
            cost = group["units"] * rate if rate is not None else None
        group["estimated_usd"] = cost
        del group["has_estimate"]
        if cost:
            grand_total += cost
        rows_out.append(group)

    rows_out.sort(key=lambda g: (g["lane"], g["provider"], g["stage"], g["model"]))
    return {"rows": rows_out, "total_usd": round(grand_total, 4)}


def lane_parity(events: list[dict[str, Any]], usage_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-lane averages so LiveKit and Pipecat can be compared side by side."""
    grouped = group_turns(events)
    per_lane: dict[str, dict[str, Any]] = {}
    for (lane, _call_id, _turn_id), turn_events in grouped.items():
        lane_stats = per_lane.setdefault(
            lane,
            {"lane": lane, "turn_count": 0, "call_ids": set(), "stage_ms_sum": {}, "stage_ms_count": {}},
        )
        lane_stats["turn_count"] += 1
        lane_stats["call_ids"].add(turn_events[0]["call_id"])
        latency = derive_stage_latency(turn_events)
        for stage, info in latency.items():
            if info["ms"] is None:
                continue
            lane_stats["stage_ms_sum"][stage] = lane_stats["stage_ms_sum"].get(stage, 0.0) + info["ms"]
            lane_stats["stage_ms_count"][stage] = lane_stats["stage_ms_count"].get(stage, 0) + 1

    cost = cost_summary(usage_rows)
    cost_by_lane: dict[str, float] = {}
    for row in cost["rows"]:
        if row["estimated_usd"] is None:
            continue
        cost_by_lane[row["lane"]] = cost_by_lane.get(row["lane"], 0.0) + row["estimated_usd"]

    result = []
    for lane, stats in per_lane.items():
        avg_stage_ms = {
            stage: round(stats["stage_ms_sum"][stage] / stats["stage_ms_count"][stage], 1)
            for stage in stats["stage_ms_sum"]
        }
        result.append(
            {
                "lane": lane,
                "call_count": len(stats["call_ids"]),
                "turn_count": stats["turn_count"],
                "avg_stage_ms": avg_stage_ms,
                "estimated_usd": round(cost_by_lane.get(lane, 0.0), 4),
            }
        )
    result.sort(key=lambda r: r["lane"])
    return {"lanes": result}


def transcriber_status(monitor_dir: Path) -> dict[str, Any]:
    try:
        active = (
            subprocess.run(
                ["systemctl", "is-active", "transcriber"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            == "active"
        )
    except (OSError, subprocess.SubprocessError):
        active = False

    recordings: list[dict[str, Any]] = []
    if monitor_dir.is_dir():
        for wav in sorted(monitor_dir.glob("*.wav")):
            txt = wav.with_suffix(".txt")
            recordings.append(
                {
                    "file": wav.name,
                    "transcribed": txt.exists(),
                    "mtime": wav.stat().st_mtime,
                }
            )
    recordings.sort(key=lambda r: r["mtime"], reverse=True)
    pending = sum(1 for r in recordings if not r["transcribed"])
    return {
        "service_active": active,
        "recordings": recordings,
        "pending": pending,
        "total": len(recordings),
    }
