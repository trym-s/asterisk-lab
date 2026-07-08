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
import unicodedata
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
# Both agents tag the bot's opening line with this sentinel turn_id (it is
# synthesized before any caller audio arrives, not a scored conversational
# turn) - exclude it from turn_count so it cannot be mistaken for a real turn.
GREETING_TURN_ID = "greeting"
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


def _uuid_lookup_keys(value: str | None) -> set[str]:
    if not value:
        return set()
    raw = value.strip()
    keys = {raw}
    compact = raw.replace("-", "").lower()
    if len(compact) == 32 and all(char in "0123456789abcdef" for char in compact):
        keys.add(compact)
        keys.add(f"{compact[0:8]}-{compact[8:12]}-{compact[12:16]}-{compact[16:20]}-{compact[20:32]}")
    return keys


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
    by_audiosocket_uuid = {}
    for row in recordings:
        for key in _uuid_lookup_keys(row["audiosocket_uuid"]):
            by_audiosocket_uuid[key] = row
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
        for key in _uuid_lookup_keys(value) or ({value} if value else set()):
            if key in lookup:
                return lookup[key], status
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
        if row.get("turn_id") and row["turn_id"] != GREETING_TURN_ID:
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


LANES = ("livekit", "pipecat")
COMPARISON_ECHO_EVENTS = {"echo_filtered", "barge_in.stop_bot_audio"}


# ---- LiveKit vs Pipecat fair comparison ----------------------------


def _filter_run(events: list[dict[str, Any]], run_id: str | None) -> list[dict[str, Any]]:
    """Scope events to a comparison run.

    `run_id` is only stamped on `call.started`/`profile.loaded` (additive
    field, per this spec's Architecture Contract) -- not on every STT/LLM/
    TTS/tool/turn event a call emits. Scoping must therefore go through
    call_id membership: find which call_ids belong to the run, then keep
    every event for those call_ids, not just the rows that carry run_id
    themselves.
    """
    if run_id is None:
        return events
    call_ids = {row["call_id"] for row in events if row.get("run_id") == run_id}
    return [row for row in events if row["call_id"] in call_ids]


def _dig(payload: dict[str, Any], path: list[str]) -> Any:
    cur: Any = payload
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in normalized if not unicodedata.combining(c))


_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(_fold(text or "")))


def _token_overlap(a: str, b: str) -> float:
    left, right = _tokens(a), _tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _fact_present(text: str, fact: str) -> bool:
    return bool(fact) and _fold(fact) in _fold(text or "")


def load_expected_corpus(path: Path | None) -> dict[str, dict[str, Any]]:
    """Read the read-only expected-answer fixture (Paired Quality panel)."""
    if not path or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = payload.get("utterances", [])
    return {row["utterance_id"]: row for row in rows if row.get("utterance_id")}


def expected_turns_for_corpus(expected_corpus: dict[str, dict[str, Any]]) -> int:
    """Turns a fully-covered scripted call should reach, derived from the corpus.

    conversations.tsv/expected-answers.json turns are grouped by
    conversation_id; a call that plays one whole conversation should reach
    that conversation's turn count. Falls back to 1 for a corpus with no
    conversation_id (a corpus predating multi-turn conversations).
    """
    counts: dict[str, int] = {}
    for row in expected_corpus.values():
        conv_id = row.get("conversation_id")
        if conv_id is None:
            continue
        counts[conv_id] = counts.get(conv_id, 0) + 1
    return max(counts.values(), default=1)


def match_utterance(
    stt_text: str,
    expected_corpus: dict[str, dict[str, Any]],
    min_overlap: float = 0.34,
) -> tuple[str | None, float]:
    """Best-effort correlation of a turn's STT text to a scripted utterance.

    The agents don't stamp turns with utterance_id today (the governing spec's
    Architecture Contract only mandates run_id on call/profile.loaded), so
    this matches the transcribed text against the fixture's scripted text
    by token overlap. Below `min_overlap` the turn is "unmatched" rather
    than force-mapped, so a bad transcript reads as missing evidence, not a
    silently wrong pairing.
    """
    if not stt_text or not expected_corpus:
        return None, 0.0
    best_id, best_score = None, 0.0
    for utterance_id, row in expected_corpus.items():
        score = _token_overlap(stt_text, row.get("text", ""))
        if score > best_score:
            best_id, best_score = utterance_id, score
    if best_score < min_overlap:
        return None, best_score
    return best_id, best_score


def _latest_profile_event(
    events: list[dict[str, Any]], lane: str, run_id: str | None
) -> dict[str, Any] | None:
    candidates = [
        row
        for row in events
        if row["lane"] == lane
        and row["stage"] == "call"
        and row["event"] == "profile.loaded"
        and (run_id is None or row.get("run_id") == run_id)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda row: row["ts"])


def _usage_evidence_kind(usage_rows: list[dict[str, Any]]) -> str | None:
    """'measured' | 'estimated' | 'mixed' | None (no usage rows)."""
    if not usage_rows:
        return None
    flags = {
        "estimated" if ("estimated" in str(row.get("unit_type", "")) or row.get("estimated")) else "measured"
        for row in usage_rows
    }
    return "mixed" if len(flags) > 1 else flags.pop()


def fairness_gate(
    events: list[dict[str, Any]],
    usage_rows: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Per-run pass/warn/not_enforced/not_comparable status rows.

    No headline "winner" ever renders from this data: `framework_isolated`
    only turns true once every row passes, and the media-path/VAD/
    framework-version rows are pinned to `not_enforced` by this spec's
    Non-Goals, so it always reads as an "as-deployed" observational
    comparison today.
    """
    profiles = {lane: _latest_profile_event(events, lane, run_id) for lane in LANES}
    present = [lane for lane in LANES if profiles[lane] is not None]
    rows: list[dict[str, Any]] = []

    def add(check: str, status: str, detail: str) -> None:
        rows.append({"check": check, "status": status, "detail": detail})

    if len(present) < 2:
        missing = [lane for lane in LANES if lane not in present]
        add(
            "run_pairing",
            "not_comparable",
            f"missing profile.loaded for: {', '.join(missing)}"
            + (f" (run_id={run_id})" if run_id else " (no run_id filter)"),
        )
        return {"run_id": run_id, "lanes_present": present, "rows": rows, "framework_isolated": False}

    lk_payload = profiles["livekit"]["payload"]
    pc_payload = profiles["pipecat"]["payload"]

    def hash_check(check: str, path: list[str], label: str) -> None:
        lk_val = _dig(lk_payload, path)
        pc_val = _dig(pc_payload, path)
        if lk_val is None or pc_val is None:
            add(check, "warn", f"{label}: missing on one or both lanes")
        elif lk_val == pc_val:
            add(check, "pass", f"{label} matches")
        else:
            add(check, "fail", f"{label} differs between lanes")

    hash_check("model_profile", ["model_profile"], "model profile")
    hash_check("prompt_hash", ["prompt_hash"], "prompt hash")
    hash_check("tool_schema_hash", ["tool_schema_hash"], "tool schema hash")
    hash_check("corpus_hash", ["corpus", "hash"], "corpus hash")
    hash_check("repo_revision", ["repo_revision"], "repo revision")

    add(
        "run_pairing",
        "pass",
        "both lanes present" + (f" for run_id={run_id}" if run_id else " (latest per lane, no run_id filter)"),
    )
    add(
        "audio_media_path",
        "not_enforced",
        "livekit: SIP GW -> SFU (opus/g722/ulaw negotiable); pipecat: AudioSocket TCP fixed 8 kHz "
        "slin16. Not forced to parity by this spec; see Follow-Ups.",
    )
    add(
        "vad_endpointing_config",
        "not_enforced",
        "VAD/endpointing tuning is not captured in profile.loaded; not compared.",
    )

    pipecat_echo_events = {
        row["event"]
        for row in events
        if row["lane"] == "pipecat" and row["event"] in COMPARISON_ECHO_EVENTS
    }
    add(
        "interruption_echo_instrumentation",
        "warn",
        (
            f"pipecat emits {sorted(pipecat_echo_events)} discrete echo/barge-in events; "
            "livekit has no equivalent (see Reliability panel's lane-specific row)."
            if pipecat_echo_events
            else "neither lane has emitted echo/barge-in events yet."
        ),
    )
    add(
        "framework_dependency_version",
        "not_enforced",
        "framework/runtime version is not captured in profile.loaded; not compared.",
    )

    lk_kind = _usage_evidence_kind([r for r in (usage_rows or []) if r.get("lane") == "livekit"])
    pc_kind = _usage_evidence_kind([r for r in (usage_rows or []) if r.get("lane") == "pipecat"])
    if lk_kind is None or pc_kind is None:
        add("usage_evidence_parity", "warn", "usage rows missing for one or both lanes")
    elif lk_kind == pc_kind and lk_kind != "mixed":
        add("usage_evidence_parity", "warn" if lk_kind == "estimated" else "pass", f"both lanes report {lk_kind} usage")
    else:
        add(
            "usage_evidence_parity",
            "warn",
            f"livekit={lk_kind}, pipecat={pc_kind} - not blended into one number (see Cost panel).",
        )

    framework_isolated = all(row["status"] == "pass" for row in rows)
    return {"run_id": run_id, "lanes_present": present, "rows": rows, "framework_isolated": framework_isolated}


def paired_quality(
    events: list[dict[str, Any]],
    expected_corpus: dict[str, dict[str, Any]],
    run_id: str | None = None,
) -> dict[str, Any]:
    """Deterministic/rubric scoring per utterance, both lanes side by side."""
    scoped = _filter_run(events, run_id)
    grouped = group_turns(scoped)

    best_by_lane: dict[str, dict[str, dict[str, Any]]] = {lane: {} for lane in LANES}
    for (lane, call_id, turn_id), turn_events in grouped.items():
        if lane not in LANES:
            continue
        stt_text = _first_text(turn_events, "stt", "final_transcript")
        if not stt_text:
            continue
        utterance_id, score = match_utterance(stt_text, expected_corpus)
        key = utterance_id or "unmatched"
        expected = expected_corpus.get(key, {})

        tool_called = _event_present(turn_events, "tool", "lookup_docs.request")
        tool_result_text = " ".join(
            str(row.get("payload", {}).get("result", ""))
            for row in turn_events
            if row["stage"] == "tool" and row["event"] == "lookup_docs.result"
        )
        llm_text = _first_text(turn_events, "llm", "response") or ""

        expected_docs = expected.get("expected_source_docs") or []
        source_hit = any(doc in tool_result_text for doc in expected_docs) if expected_docs else None

        required_facts = expected.get("required_facts") or []
        required_present = (
            any(_fact_present(llm_text, fact) for fact in required_facts) if required_facts else None
        )
        forbidden_facts = expected.get("forbidden_facts") or []
        forbidden_absent = (
            not any(_fact_present(llm_text, fact) for fact in forbidden_facts) if forbidden_facts else None
        )
        tool_required = expected.get("tool_required")
        tool_call_correct = (tool_called == tool_required) if tool_required is not None else None

        row_result = {
            "lane": lane,
            "call_id": call_id,
            "turn_id": turn_id,
            "utterance_id": key,
            "match_score": round(score, 2),
            "stt_text": stt_text,
            "llm_text": llm_text or None,
            "tool_called": tool_called,
            "tool_required": tool_required,
            "tool_call_correct": tool_call_correct,
            "source_hit": source_hit,
            "required_facts_present": required_present,
            "forbidden_facts_absent": forbidden_absent,
            "echo_or_extra_turn": _event_present(turn_events, "stt", "echo_filtered"),
            "needs_review": key == "unmatched" or not expected,
        }
        existing = best_by_lane[lane].get(key)
        if existing is None or score > existing["match_score"]:
            best_by_lane[lane][key] = row_result

    all_ids = sorted(set(expected_corpus) | set(best_by_lane["livekit"]) | set(best_by_lane["pipecat"]))
    rows = []
    for utterance_id in all_ids:
        expected = expected_corpus.get(utterance_id, {})
        rows.append(
            {
                "utterance_id": utterance_id,
                "expected_text": expected.get("text"),
                "expected_intent": expected.get("expected_intent"),
                "livekit": best_by_lane["livekit"].get(utterance_id),
                "pipecat": best_by_lane["pipecat"].get(utterance_id),
            }
        )
    return {"run_id": run_id, "rows": rows}


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * pct
    lower = int(k)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return sorted_values[lower]
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (k - lower)


def latency_decision(
    events: list[dict[str, Any]],
    run_id: str | None = None,
    min_n: int = 20,
) -> dict[str, Any]:
    """Per-stage p50 (always) / p95 (gated by min_n) with N and source label."""
    scoped = _filter_run(events, run_id)
    grouped = group_turns(scoped)

    samples: dict[tuple[str, str], list[tuple[float, str]]] = {}
    for (lane, _call_id, _turn_id), turn_events in grouped.items():
        if lane not in LANES:
            continue
        for stage, info in derive_stage_latency(turn_events).items():
            if info["ms"] is None:
                continue
            samples.setdefault((lane, stage), []).append((info["ms"], info["source"]))

    stages_present = sorted(
        {stage for _lane, stage in samples},
        key=lambda s: STAGE_ORDER.index(s) if s in STAGE_ORDER else len(STAGE_ORDER),
    )
    result: dict[str, Any] = {"run_id": run_id, "min_n": min_n, "lanes": {}}
    for lane in LANES:
        stage_rows = []
        for stage in stages_present:
            pairs = samples.get((lane, stage), [])
            if not pairs:
                continue
            values = sorted(v for v, _source in pairs)
            sources = {source for _v, source in pairs}
            source_label = "measured" if sources == {"measured"} else ("approx" if sources == {"approx"} else "mixed")
            n = len(values)
            stage_rows.append(
                {
                    "stage": stage,
                    "n": n,
                    "p50_ms": round(_percentile(values, 0.5), 1),
                    "p95_ms": round(_percentile(values, 0.95), 1) if n >= min_n else None,
                    "source": source_label,
                }
            )
        result["lanes"][lane] = stage_rows
    return result


def reliability_summary(
    events: list[dict[str, Any]],
    run_id: str | None = None,
    *,
    expected_turns_per_call: int = 1,
    now: float | None = None,
    active_stale_s: int = ACTIVE_CALL_STALE_S,
) -> dict[str, Any]:
    """Two-row payload: comparable neutral outcomes vs lane-specific diagnostics.

    `expected_turns_per_call` defaults to 1 (a corpus predating multi-turn
    conversations) but callers should pass `expected_turns_for_corpus()`'s
    result for the active expected-answer corpus: run-suite.sh now dials
    once per conversation_id and plays every turn before hanging up, so a
    call "reaching its expected turns" means completing the whole scripted
    conversation, not just its first turn.
    """
    scoped = _filter_run(events, run_id)
    calls = list_calls(scoped, now=now, active_stale_s=active_stale_s)

    events_by_call: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in scoped:
        events_by_call.setdefault((row["lane"], row["call_id"]), []).append(row)

    turns_by_call: dict[tuple[str, str], list[list[dict[str, Any]]]] = {}
    for (lane, call_id, turn_id), turn_events in group_turns(scoped).items():
        if turn_id == GREETING_TURN_ID:
            continue
        turns_by_call.setdefault((lane, call_id), []).append(turn_events)

    comparable = {
        lane: {
            "calls": 0,
            "call_completed": 0,
            "expected_turns_reached": 0,
            "no_missing_stage": 0,
            "no_error_event": 0,
            "no_stale_call": 0,
            "no_empty_final_transcript": 0,
            "no_duplicate_extra_turn": 0,
        }
        for lane in LANES
    }
    lane_specific: dict[str, dict[str, int]] = {lane: {} for lane in LANES}

    for call in calls:
        lane = call["lane"]
        if lane not in comparable:
            continue
        counts = comparable[lane]
        counts["calls"] += 1
        key = (lane, call["call_id"])
        call_events = events_by_call.get(key, [])
        turn_groups = turns_by_call.get(key, [])

        if call["call_ended"]:
            counts["call_completed"] += 1
        if call["turn_count"] >= expected_turns_per_call:
            counts["expected_turns_reached"] += 1
        missing_stage = (
            any(not {"stt", "llm", "tts"} <= {row["stage"] for row in te} for te in turn_groups)
            if turn_groups
            else True
        )
        if not missing_stage:
            counts["no_missing_stage"] += 1
        if not any(row["stage"] == "error" for row in call_events):
            counts["no_error_event"] += 1
        if not call["stale_without_end"]:
            counts["no_stale_call"] += 1
        empty_transcript = any(
            not (_first_text(te, "stt", "final_transcript") or "").strip() for te in turn_groups
        )
        if not empty_transcript:
            counts["no_empty_final_transcript"] += 1
        duplicate_extra = call["turn_count"] > expected_turns_per_call
        if not duplicate_extra:
            counts["no_duplicate_extra_turn"] += 1

        for row in call_events:
            if row["event"] in COMPARISON_ECHO_EVENTS:
                lane_specific[lane][row["event"]] = lane_specific[lane].get(row["event"], 0) + 1

    return {"run_id": run_id, "comparable_outcomes": comparable, "lane_specific_diagnostics": lane_specific}


def cost_normalized(
    usage_rows: list[dict[str, Any]],
    events: list[dict[str, Any]],
    run_id: str | None = None,
) -> dict[str, Any]:
    """Cost per successful turn and per corpus run, measured vs estimated kept separate.

    usage.jsonl rows don't carry run_id (only events.jsonl does, per this
    spec's Architecture Contract); a run is instead scoped through the
    call_ids that appear in the run-scoped events, then usage rows are
    filtered by call_id.
    """
    scoped_events = _filter_run(events, run_id)
    call_ids = {row["call_id"] for row in scoped_events} if run_id is not None else None
    scoped_usage = usage_rows if call_ids is None else [row for row in usage_rows if row.get("call_id") in call_ids]

    calls = list_calls(scoped_events)
    # cost_summary groups finer than lane; re-aggregate to one total per lane.
    lane_totals: dict[str, float] = {}
    for row in cost_summary(scoped_usage)["rows"]:
        if row["estimated_usd"] is None:
            continue
        lane_totals[row["lane"]] = lane_totals.get(row["lane"], 0.0) + row["estimated_usd"]

    rows = []
    for lane in LANES:
        lane_usage = [row for row in scoped_usage if row.get("lane") == lane]
        lane_calls = [call for call in calls if call["lane"] == lane]
        turns = sum(call["turn_count"] for call in lane_calls)
        total_cost = round(lane_totals.get(lane, 0.0), 6)
        rows.append(
            {
                "lane": lane,
                "evidence": _usage_evidence_kind(lane_usage) or "unknown",
                "total_usd": total_cost,
                "calls": len(lane_calls),
                "turns": turns,
                "cost_per_turn_usd": round(total_cost / turns, 6) if turns else None,
                "cost_per_corpus_run_usd": total_cost if lane_calls else None,
            }
        )
    return {"run_id": run_id, "rows": rows}


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
