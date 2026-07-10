from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import trace_events
import usage
import voicebot_profile


class TraceEventsTest(unittest.TestCase):
    def test_record_event_writes_required_keys_and_redacts_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            row = trace_events.record_event(
                lane="pipecat",
                call_id="call-1",
                turn_id="turn-0001",
                stage="llm",
                event="request",
                provider="openai",
                model="gpt-4o-mini",
                payload={
                    "Authorization": "Bearer very-secret-token-value",
                    "nested": {"OPENAI_API_KEY": "sk-secretsecretsecret"},
                    "text": "Magazaniz Pazar gunu kacta aciliyor?",
                },
                path=path,
            )
            trace_events.validate_event(row)
            loaded = trace_events.read_events(path)
            self.assertEqual(loaded[0]["payload"]["Authorization"], "[REDACTED]")
            self.assertEqual(loaded[0]["payload"]["nested"]["OPENAI_API_KEY"], "[REDACTED]")
            self.assertIn("Pazar", loaded[0]["payload"]["text"])

    def test_invalid_stage_fails_fast(self) -> None:
        with self.assertRaises(ValueError):
            trace_events.build_event(
                lane="livekit",
                call_id="call-1",
                stage="bogus",
                event="bad",
            )

    def test_run_id_is_additive_and_omitted_when_absent(self) -> None:
        with_run = trace_events.build_event(
            lane="livekit", call_id="call-1", stage="call", event="call.started",
            run_id="run-42",
        )
        self.assertEqual(with_run["run_id"], "run-42")
        trace_events.validate_event(with_run)

        without_run = trace_events.build_event(
            lane="livekit", call_id="call-1", stage="call", event="call.started",
        )
        self.assertNotIn("run_id", without_run)

    def test_current_run_id_reads_env_var(self) -> None:
        old = os.environ.get("VOICEBOT_RUN_ID")
        os.environ["VOICEBOT_RUN_ID"] = "run-xyz"
        try:
            self.assertEqual(trace_events.current_run_id(), "run-xyz")
        finally:
            if old is None:
                os.environ.pop("VOICEBOT_RUN_ID", None)
            else:
                os.environ["VOICEBOT_RUN_ID"] = old


class UsageTest(unittest.TestCase):
    def test_canonical_usage_row_keeps_backward_compatible_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "usage.jsonl"
            old = os.environ.get("VOICEBOT_USAGE_LOG")
            os.environ["VOICEBOT_USAGE_LOG"] = str(path)
            try:
                usage.record(
                    provider="openai",
                    op="chat",
                    units=12,
                    unit_type="tokens_in",
                    ref="legacy-ref",
                    lane="livekit",
                    call_id="call-1",
                    turn_id="turn-0001",
                    stage="llm",
                    model="gpt-4o-mini",
                )
            finally:
                if old is None:
                    os.environ.pop("VOICEBOT_USAGE_LOG", None)
                else:
                    os.environ["VOICEBOT_USAGE_LOG"] = old
            row = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(row["ref"], "legacy-ref")
            self.assertEqual(row["lane"], "livekit")
            self.assertEqual(row["call_id"], "call-1")
            self.assertEqual(row["turn_id"], "turn-0001")
            self.assertEqual(row["stage"], "llm")
            self.assertEqual(row["model"], "gpt-4o-mini")
            self.assertIn("pricing_version", row)
            self.assertIn("estimated_usd", row)


class ProfileTest(unittest.TestCase):
    def test_profile_defaults_and_hashes_are_deterministic(self) -> None:
        profile = voicebot_profile.load_model_profile()
        self.assertEqual(profile.stt_provider, "soniox")
        self.assertEqual(profile.stt_model, "stt-rt-v5")
        self.assertEqual(profile.llm_model, "gpt-4o-mini")
        self.assertEqual(profile.tts_provider, "soniox")
        self.assertEqual(profile.tts_model, "tts-rt-v1")
        self.assertEqual(
            voicebot_profile.stable_json_hash({"b": 1, "a": 2}),
            voicebot_profile.stable_json_hash({"a": 2, "b": 1}),
        )


if __name__ == "__main__":
    unittest.main()
