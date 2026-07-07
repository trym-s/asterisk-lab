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
import zabbix_client  # noqa: E402


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

    def test_marks_recent_started_call_in_progress_and_stales_legacy_rows(self) -> None:
        events = [
            trace_events.build_event(
                lane="livekit", call_id="live", stage="call", event="call.started", ts=100.0,
            ),
            trace_events.build_event(
                lane="pipecat", call_id="old", stage="call", event="call.started", ts=1.0,
            ),
        ]
        calls = data.list_calls(events, now=130.0, active_stale_s=60)
        by_id = {c["call_id"]: c for c in calls}
        self.assertTrue(by_id["live"]["in_progress"])
        self.assertFalse(by_id["old"]["in_progress"])
        self.assertTrue(by_id["old"]["stale_without_end"])

    def test_correlates_audiosocket_uuid_to_mixmonitor_recording(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            monitor = Path(tmp)
            wav = monitor / "20260707-120000-1001-pc-1751900000.42.wav"
            txt = monitor / "20260707-120000-1001-pc-1751900000.42.txt"
            wav.touch()
            txt.write_text("merhaba", encoding="utf-8")
            call_id = data.audiosocket_uuid_for_uniqueid("1751900000.42")
            compact_call_id = call_id.replace("-", "")
            events = [
                trace_events.build_event(
                    lane="pipecat", call_id=compact_call_id, stage="call", event="call.started",
                    ts=1.0, payload={"uuid": compact_call_id},
                ),
            ]
            calls = data.list_calls(events, monitor, now=2.0)
            self.assertEqual(calls[0]["recording_file"], wav.name)
            self.assertTrue(calls[0]["batch_transcript"])
            self.assertEqual(calls[0]["correlation_status"], "matched")

    def test_live_transcript_badge_detects_stt_final_transcript(self) -> None:
        events = [
            trace_events.build_event(
                lane="livekit", call_id="c1", stage="call", event="call.started", ts=1.0,
            ),
            trace_events.build_event(
                lane="livekit", call_id="c1", turn_id="t1", stage="stt",
                event="final_transcript", ts=2.0, payload={"text": "merhaba"},
            ),
        ]
        self.assertTrue(data.list_calls(events, now=3.0)[0]["live_transcript"])


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

    def test_cost_timeseries_buckets_and_drilldown_by_lane(self) -> None:
        rows = [
            {
                "ts": 10.0, "provider": "openai", "op": "tts", "units": 100.0,
                "unit_type": "chars", "lane": "livekit", "stage": "tts",
                "model": "tts-1", "estimated_usd": 0.001,
            },
            {
                "ts": 65.0, "provider": "openai", "op": "tts", "units": 200.0,
                "unit_type": "chars", "lane": "pipecat", "stage": "tts",
                "model": "tts-1", "estimated_usd": 0.002,
            },
        ]
        series = data.cost_timeseries(rows, since_ts=0, bucket_s=60)
        self.assertEqual([p["start_ts"] for p in series["points"]], [0, 60])
        self.assertAlmostEqual(series["total_usd"], 0.003)
        self.assertEqual([row["lane"] for row in series["drilldown"]], ["livekit", "pipecat"])


class ExtensionStatusTest(unittest.TestCase):
    def test_parse_pjsip_endpoints_lists_registered_extensions(self) -> None:
        output = """
 Endpoint:  1001                                         Not in use    0 of inf
     InAuth:  1001/1001
        Aor:  1001                                       1
      Contact:  1001/sip:1001@192.0.2.10:5555            Avail        13.4
 Endpoint:  1002                                         Unavailable   0 of inf
        Aor:  1002                                       1
 Endpoint:  livekit-trunk                                Not in use    0 of inf
        """
        status = data.parse_pjsip_endpoints(output)
        self.assertEqual(status["total"], 2)
        self.assertEqual(status["registered"], 1)
        by_ext = {row["extension"]: row for row in status["extensions"]}
        self.assertTrue(by_ext["1001"]["registered"])
        self.assertFalse(by_ext["1002"]["registered"])


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


class ZabbixClientTest(unittest.TestCase):
    def test_unavailable_summary_keeps_host_rows(self) -> None:
        summary = zabbix_client.unavailable_summary("missing token")
        self.assertFalse(summary["available"])
        self.assertEqual(len(summary["hosts"]), 3)
        self.assertEqual({row["status"] for row in summary["hosts"]}, {"unavailable"})


if __name__ == "__main__":
    unittest.main()
