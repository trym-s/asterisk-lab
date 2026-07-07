from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
COMMON_DIR = Path(__file__).resolve().parent.parent.parent / "common"
for path in (APP_DIR, COMMON_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import data  # noqa: E402
import trace_events  # noqa: E402


def _write_events(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            trace_events.validate_event(row)
            import json

            handle.write(json.dumps(row) + "\n")


class DeriveStageLatencyTest(unittest.TestCase):
    def test_derives_deltas_and_prefers_measured_duration(self) -> None:
        events = [
            trace_events.build_event(
                lane="livekit", call_id="c1", turn_id="t1", stage="stt",
                event="final_transcript", ts=0.0, payload={"text": "hi"},
            ),
            trace_events.build_event(
                lane="livekit", call_id="c1", turn_id="t1", stage="llm",
                event="request", ts=0.4, payload={},
            ),
            trace_events.build_event(
                lane="livekit", call_id="c1", turn_id="t1", stage="tool",
                event="lookup_docs.result", ts=0.6, duration_ms=45.0, payload={},
            ),
            trace_events.build_event(
                lane="livekit", call_id="c1", turn_id="t1", stage="tts",
                event="request", ts=1.0, payload={"text": "hi there"},
            ),
        ]
        latency = data.derive_stage_latency(events)
        self.assertEqual(latency["stt"], {"ms": 400.0, "source": "approx"})
        self.assertEqual(latency["tool"], {"ms": 45.0, "source": "measured"})
        self.assertIsNone(latency["tts"]["ms"])

    def test_no_turn_id_events_are_excluded_from_grouping(self) -> None:
        events = [
            trace_events.build_event(
                lane="livekit", call_id="c1", stage="call", event="call.started", ts=0.0,
            ),
        ]
        grouped = data.group_turns(events)
        self.assertEqual(grouped, {})


class ListCallsTest(unittest.TestCase):
    def test_groups_by_lane_and_call_id_with_turn_count(self) -> None:
        events = [
            trace_events.build_event(
                lane="livekit", call_id="c1", turn_id="t1", stage="stt", event="e", ts=1.0,
            ),
            trace_events.build_event(
                lane="livekit", call_id="c1", turn_id="t2", stage="stt", event="e", ts=2.0,
            ),
            trace_events.build_event(
                lane="pipecat", call_id="c2", turn_id="t1", stage="stt", event="e", ts=3.0,
            ),
        ]
        calls = data.list_calls(events)
        by_id = {c["call_id"]: c for c in calls}
        self.assertEqual(by_id["c1"]["turn_count"], 2)
        self.assertEqual(by_id["c2"]["turn_count"], 1)


class CostSummaryTest(unittest.TestCase):
    def test_falls_back_to_price_table_when_no_estimate_present(self) -> None:
        rows = [
            {
                "ts": 1.0, "provider": "openai", "op": "stt", "units": 60.0,
                "unit_type": "seconds", "lane": "livekit", "estimated_usd": None,
            },
        ]
        summary = data.cost_summary(rows)
        self.assertEqual(len(summary["rows"]), 1)
        self.assertAlmostEqual(summary["rows"][0]["estimated_usd"], 0.006)
        self.assertAlmostEqual(summary["total_usd"], 0.006)

    def test_since_ts_filters_older_rows(self) -> None:
        rows = [
            {"ts": 1.0, "provider": "openai", "op": "stt", "units": 60.0, "unit_type": "seconds", "estimated_usd": None},
            {"ts": 100.0, "provider": "openai", "op": "stt", "units": 60.0, "unit_type": "seconds", "estimated_usd": None},
        ]
        summary = data.cost_summary(rows, since_ts=50.0)
        self.assertEqual(len(summary["rows"]), 1)
        self.assertEqual(summary["rows"][0]["events"], 1)


class TranscriberStatusTest(unittest.TestCase):
    def test_pairs_wav_with_sibling_txt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            monitor = Path(tmp)
            (monitor / "a.wav").touch()
            (monitor / "b.wav").touch()
            (monitor / "b.txt").write_text("transcript")
            status = data.transcriber_status(monitor)
            self.assertEqual(status["total"], 2)
            self.assertEqual(status["pending"], 1)
            by_file = {r["file"]: r["transcribed"] for r in status["recordings"]}
            self.assertFalse(by_file["a.wav"])
            self.assertTrue(by_file["b.txt".replace(".txt", ".wav")])


if __name__ == "__main__":
    unittest.main()
