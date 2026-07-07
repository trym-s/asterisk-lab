"""Read-only aggregation over the voicebot observability inputs.

Data flows one direction: JSONL/spool/Asterisk CLI/Zabbix responses -> this
module -> JSON endpoints -> Jinja2 pages. Nothing here writes back to the
sinks.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

import trace_events
import usage_summary

STAGE_ORDER = ["call", "audio", "stt", "llm", "tool", "tts", "error"]
PIPELINE_STEPS = [
    ("stt", "STT output", "final_transcript"),
    ("llm", "LLM response", "response"),
    ("tts", "TTS input", "request"),
]
ACTIVE_CALL_STALE_S = 120
RECORDING_RE = re.compile(
    r"^(?P<stamp>\d{8}-\d{6})-(?P<caller>[^-]+)-(?P<target>[^-]+)-(?P<uniqueid>.+)$"
)
ENDPOINT_RE = re.compile(r"^\s*Endpoint:\s+(?P<id>\S+)\s+(?P<status>.+)$")
CONTACT_RE = re.compile(r"^\s*Contact:\s+\S+\s+(?P<uri>\S+)\s+(?P<status>\S+)")


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


def duration_seconds(value: str | None, default_s: int = 3600) -> int:
    if not value:
        return default_s
    raw = value.strip().lower()
    match = re.fullmatch(r"(\d+)([smhd])", raw)
    if not match:
        return default_s
    amount = int(match.group(1))
    unit = match.group(2)
    factors = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return max(1, amount * factors[unit])


def _estimate_cost(row: dict[str, Any]) -> float | None:
    if row.get("estimated_usd") is not None:
        return float(row["estimated_usd"])
    try:
        provider = row["provider"]
        op = row["op"]
        unit_type = row["unit_type"]
        units = float(row["units"])
    except (KeyError, TypeError, ValueError):
        return None
    rate = usage_summary.PRICE.get((provider, op, unit_type))
    return units * rate if rate is not None else None


def group_turns(events: list[dict[str, Any]]) -> dict[tuple[str, str, str], list[dict]]:
    """Group event rows by (lane, call_id, turn_id), each list ts-sorted."""
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
    duration_ms already carried on the row over the derived delta.
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


def _event_present(turn_events: list[dict[str, Any]], stage: str, event: str) -> bool:
    return any(row["stage"] == stage and row["event"] == event for row in turn_events)


def turn_summary(key: tuple[str, str, str], turn_events: list[dict[str, Any]]) -> dict[str, Any]:
    lane, call_id, turn_id = key
    latency = derive_stage_latency(turn_events)
    texts = {
        "stt": _first_text(turn_events, "stt", "final_transcript"),
        "llm": _first_text(turn_events, "llm", "response"),
        "tts": _first_text(turn_events, "tts", "request"),
    }
    steps = []
    for stage, label, event in PIPELINE_STEPS:
        steps.append(
            {
                "stage": stage,
                "label": label,
                "event": event,
                "text": texts[stage],
                "available": bool(texts[stage]),
                "latency_ms": latency.get(stage, {"ms": None, "source": "approx"}),
            }
        )
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
        "stt_text": texts["stt"],
        "llm_text": texts["llm"],
        "tts_text": texts["tts"],
        "tts_output": _event_present(turn_events, "tts", "output")
        or _event_present(turn_events, "tts", "output_audio.started")
        or _event_present(turn_events, "tts", "speech_committed"),
        "steps": steps,
        "tool_calls": tool_calls,
        "latency_ms": latency,
    }


def audiosocket_uuid_for_uniqueid(uniqueid: str) -> str:
    digest = hashlib.md5(uniqueid.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"{digest[0:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def parse_recording_name(path: Path) -> dict[str, Any] | None:
    match = RECORDING_RE.match(path.stem)
    if not match:
        return None
    uniqueid = match.group("uniqueid")
    return {
        "file": path.name,
        "stamp": match.group("stamp"),
        "caller": match.group("caller"),
        "target": match.group("target"),
        "asterisk_uniqueid": uniqueid,
        "audiosocket_uuid": audiosocket_uuid_for_uniqueid(uniqueid),
        "transcribed": path.with_suffix(".txt").exists(),
        "mtime": path.stat().st_mtime,
    }


def recording_index(monitor_dir: Path | None) -> dict[str, Any]:
    recordings: list[dict[str, Any]] = []
    if monitor_dir and monitor_dir.is_dir():
        for wav in sorted(monitor_dir.glob("*.wav")):
            parsed = parse_recording_name(wav)
            if parsed:
                recordings.append(parsed)
    by_uniqueid = {row["asterisk_uniqueid"]: row for row in recordings}
    by_audiosocket_uuid = {row["audiosocket_uuid"]: row for row in recordings}
    return {
        "recordings": recordings,
        "by_uniqueid": by_uniqueid,
        "by_audiosocket_uuid": by_audiosocket_uuid,
    }


def _payload_value(rows: list[dict[str, Any]], *keys: str) -> str | None:
    for row in rows:
        payload = row.get("payload", {})
        for key in keys:
            value = payload.get(key)
            if value:
                return str(value)
    return None


def _match_recording(entry: dict[str, Any], index: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    rows = entry["events"]
    uniqueid = _payload_value(rows, "asterisk_uniqueid", "uniqueid")
    audiosocket_uuid = _payload_value(rows, "asterisk_audiosocket_uuid", "uuid", "audiosocket_uuid")
    candidates = [
        ("uniqueid", uniqueid, index["by_uniqueid"]),
        ("audiosocket_uuid", audiosocket_uuid, index["by_audiosocket_uuid"]),
        ("call_id_as_uniqueid", entry["call_id"], index["by_uniqueid"]),
        ("call_id_as_audiosocket_uuid", entry["call_id"], index["by_audiosocket_uuid"]),
    ]
    for status, value, lookup in candidates:
        if value and value in lookup:
            return lookup[value], status
    return None, "missing"


def list_calls(
    events: list[dict[str, Any]],
    monitor_dir: Path | None = None,
    *,
    now: float | None = None,
    active_stale_s: int = ACTIVE_CALL_STALE_S,
) -> list[dict[str, Any]]:
    """One row per (lane, call_id) with transcript and live-state badges."""
    current_time = time.time() if now is None else now
    recordings = recording_index(monitor_dir)
    calls: dict[tuple[str, str], dict[str, Any]] = {}
    for row in events:
        key = (row["lane"], row["call_id"])
        entry = calls.setdefault(
            key,
            {
                "lane": row["lane"],
                "call_id": row["call_id"],
                "start_ts": row["ts"],
                "end_ts": row["ts"],
                "turn_ids": set(),
                "events": [],
                "event_names": set(),
            },
        )
        entry["events"].append(row)
        entry["event_names"].add(row["event"])
        entry["start_ts"] = min(entry["start_ts"], row["ts"])
        entry["end_ts"] = max(entry["end_ts"], row["ts"])
        if row.get("turn_id"):
            entry["turn_ids"].add(row["turn_id"])

    result = []
    for entry in calls.values():
        recording, correlation_status = _match_recording(entry, recordings)
        event_names = entry["event_names"]
        has_started = "call.started" in event_names
        has_ended = "call.ended" in event_names
        stale = (current_time - entry["end_ts"]) > active_stale_s
        live_transcript = any(
            row["stage"] == "stt" and row["event"] == "final_transcript"
            for row in entry["events"]
        )
        last_event = max(entry["events"], key=lambda row: row["ts"])
        result.append(
            {
                "lane": entry["lane"],
                "call_id": entry["call_id"],
                "start_ts": entry["start_ts"],
                "end_ts": entry["end_ts"],
                "turn_count": len(entry["turn_ids"]),
                "call_started": has_started,
                "call_ended": has_ended,
                "in_progress": has_started and not has_ended and not stale,
                "stale_without_end": has_started and not has_ended and stale,
                "live_transcript": live_transcript,
                "batch_transcript": bool(recording and recording["transcribed"]),
                "recording_file": recording["file"] if recording else None,
                "asterisk_uniqueid": (recording or {}).get("asterisk_uniqueid")
                or _payload_value(entry["events"], "asterisk_uniqueid", "uniqueid"),
                "asterisk_channel": _payload_value(entry["events"], "asterisk_channel", "channel"),
                "correlation_status": "matched" if recording else correlation_status,
                "last_stage": last_event["stage"],
                "last_event": last_event["event"],
            }
        )
    result.sort(key=lambda c: c["start_ts"], reverse=True)
    return result


def call_summary(
    events: list[dict[str, Any]],
    call_id: str,
    monitor_dir: Path | None = None,
    *,
    now: float | None = None,
    active_stale_s: int = ACTIVE_CALL_STALE_S,
) -> dict[str, Any] | None:
    for call in list_calls(events, monitor_dir, now=now, active_stale_s=active_stale_s):
        if call["call_id"] == call_id:
            return call
    return None


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
        cost = _estimate_cost(row)
        if cost is not None:
            group["estimated_usd"] += cost
            group["has_estimate"] = True

    rows_out = []
    grand_total = 0.0
    for group in groups.values():
        cost = group["estimated_usd"] if group["has_estimate"] else None
        group["estimated_usd"] = round(cost, 6) if cost is not None else None
        del group["has_estimate"]
        if cost:
            grand_total += cost
        rows_out.append(group)

    rows_out.sort(key=lambda g: (g["lane"], g["provider"], g["stage"], g["model"]))
    return {"rows": rows_out, "total_usd": round(grand_total, 4)}


def cost_timeseries(usage_rows: list[dict[str, Any]], since_ts: float, bucket_s: int) -> dict[str, Any]:
    buckets: dict[int, dict[str, Any]] = {}
    for row in usage_rows:
        ts = float(row.get("ts", 0))
        if ts < since_ts:
            continue
        cost = _estimate_cost(row)
        if cost is None:
            continue
        bucket_start = int(ts // bucket_s) * bucket_s
        bucket = buckets.setdefault(
            bucket_start,
            {
                "start_ts": bucket_start,
                "end_ts": bucket_start + bucket_s,
                "total_usd": 0.0,
                "by_lane": {},
            },
        )
        lane = row.get("lane") or "unknown"
        bucket["total_usd"] += cost
        bucket["by_lane"][lane] = bucket["by_lane"].get(lane, 0.0) + cost

    points = []
    for bucket in sorted(buckets.values(), key=lambda item: item["start_ts"]):
        bucket["total_usd"] = round(bucket["total_usd"], 6)
        bucket["by_lane"] = {
            lane: round(total, 6)
            for lane, total in sorted(bucket["by_lane"].items())
        }
        points.append(bucket)

    summary = cost_summary(usage_rows, since_ts)
    by_lane: dict[str, dict[str, Any]] = {}
    for row in summary["rows"]:
        lane = row["lane"]
        group = by_lane.setdefault(
            lane,
            {"lane": lane, "events": 0, "units": 0.0, "estimated_usd": 0.0, "children": []},
        )
        group["events"] += row["events"]
        group["units"] += row["units"]
        if row["estimated_usd"] is not None:
            group["estimated_usd"] += row["estimated_usd"]
        group["children"].append(row)
    drilldown = []
    for group in sorted(by_lane.values(), key=lambda item: item["lane"]):
        group["estimated_usd"] = round(group["estimated_usd"], 6)
        drilldown.append(group)

    return {
        "bucket_s": bucket_s,
        "points": points,
        "drilldown": drilldown,
        "total_usd": summary["total_usd"],
    }


def lane_parity(events: list[dict[str, Any]], usage_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-lane averages so LiveKit and Pipecat can be compared side by side."""
    grouped = group_turns(events)
    per_lane: dict[str, dict[str, Any]] = {}
    for (lane, _call_id, _turn_id), turn_events in grouped.items():
        lane_stats = per_lane.setdefault(
            lane,
            {
                "lane": lane,
                "turn_count": 0,
                "call_ids": set(),
                "stage_ms_sum": {},
                "stage_ms_count": {},
            },
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


def parse_pjsip_endpoints(output: str) -> dict[str, Any]:
    endpoints: dict[str, dict[str, Any]] = {}
    current: str | None = None
    for line in output.splitlines():
        endpoint = ENDPOINT_RE.match(line)
        if endpoint:
            endpoint_id = endpoint.group("id")
            current = endpoint_id if endpoint_id.isdigit() else None
            if current:
                raw_status = " ".join(endpoint.group("status").split())
                endpoints[current] = {
                    "extension": current,
                    "registered": False,
                    "status": "unknown",
                    "raw_status": raw_status,
                    "contact": None,
                }
                if "unavailable" in raw_status.lower():
                    endpoints[current]["status"] = "unavailable"
            continue

        contact = CONTACT_RE.match(line)
        if current and contact:
            contact_status = contact.group("status")
            normalized = contact_status.lower()
            registered = normalized not in {"unavail", "unavailable", "removed", "unknown"}
            endpoints[current]["registered"] = registered
            endpoints[current]["status"] = "registered" if registered else "unavailable"
            endpoints[current]["contact"] = contact.group("uri")
            endpoints[current]["contact_status"] = contact_status

    rows = [endpoints[key] for key in sorted(endpoints)]
    return {
        "available": True,
        "registered": sum(1 for row in rows if row["registered"]),
        "total": len(rows),
        "extensions": rows,
        "error": None,
    }


def extension_status(asterisk_cli: str = "asterisk") -> dict[str, Any]:
    command = shlex.split(asterisk_cli) + ["-rx", "pjsip show endpoints"]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "available": False,
            "registered": 0,
            "total": 0,
            "extensions": [],
            "error": str(exc),
        }
    if proc.returncode != 0:
        return {
            "available": False,
            "registered": 0,
            "total": 0,
            "extensions": [],
            "error": (proc.stderr or proc.stdout).strip(),
        }
    return parse_pjsip_endpoints(proc.stdout)


def transcriber_status(monitor_dir: Path) -> dict[str, Any]:
    try:
        active = (
            subprocess.run(
                ["systemctl", "is-active", "transcriber"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            ).stdout.strip()
            == "active"
        )
    except (OSError, subprocess.SubprocessError):
        active = False

    recordings: list[dict[str, Any]] = []
    if monitor_dir.is_dir():
        for wav in sorted(monitor_dir.glob("*.wav")):
            parsed = parse_recording_name(wav) or {
                "file": wav.name,
                "transcribed": wav.with_suffix(".txt").exists(),
                "mtime": wav.stat().st_mtime,
            }
            recordings.append(parsed)
    recordings.sort(key=lambda r: r["mtime"], reverse=True)
    pending = sum(1 for r in recordings if not r["transcribed"])
    return {
        "service_active": active,
        "recordings": recordings,
        "pending": pending,
        "total": len(recordings),
    }
