"""Environment-driven settings for the voicebot observability dashboard.

Reuses the existing VOICEBOT_EVENTS_LOG / VOICEBOT_USAGE_LOG overrides from
services/common so the dashboard reads the same files the lanes write.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import trace_events
import usage

DEFAULT_TURNS_LOG = Path("/var/lib/voicebot/turns.jsonl")
DEFAULT_MONITOR_DIR = Path("/var/spool/asterisk/monitor")


@dataclass(frozen=True)
class Settings:
    bind: str
    port: int
    refresh_s: int
    events_path: Path
    usage_path: Path
    turns_path: Path
    monitor_dir: Path
    basic_auth_user: str | None
    basic_auth_password: str | None


def load_settings() -> Settings:
    basic_auth_user = os.environ.get("VOICEBOT_DASHBOARD_BASIC_AUTH_USER") or None
    basic_auth_password = os.environ.get("VOICEBOT_DASHBOARD_BASIC_AUTH_PASSWORD") or None
    return Settings(
        bind=os.environ.get("VOICEBOT_DASHBOARD_BIND", "127.0.0.1"),
        port=int(os.environ.get("VOICEBOT_DASHBOARD_PORT", "8099")),
        refresh_s=int(os.environ.get("VOICEBOT_DASHBOARD_REFRESH_S", "5")),
        events_path=trace_events.default_events_path(),
        usage_path=usage.LOG_PATH,
        turns_path=Path(os.environ.get("VOICEBOT_TURNS_LOG", str(DEFAULT_TURNS_LOG))),
        monitor_dir=Path(
            os.environ.get("VOICEBOT_MONITOR_DIR", str(DEFAULT_MONITOR_DIR))
        ),
        basic_auth_user=basic_auth_user,
        basic_auth_password=basic_auth_password,
    )
