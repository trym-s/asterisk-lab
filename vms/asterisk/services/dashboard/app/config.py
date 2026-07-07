"""Environment-driven settings for the voicebot observability dashboard.

Reuses the existing VOICEBOT_EVENTS_LOG / VOICEBOT_USAGE_LOG override names
from services/common, but resolves them independently: the common module's
own default-path helpers fall back to a per-user XDG path when the caller
lacks *write* access to /var/lib/voicebot, which is right for the lanes that
write those files but wrong here — the dashboard only ever reads, and it
typically runs as a user (asterisk) that can read but not write that
root-owned directory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_EVENTS_LOG = Path("/var/lib/voicebot/events.jsonl")
DEFAULT_USAGE_LOG = Path("/var/lib/voicebot/usage.jsonl")
DEFAULT_TURNS_LOG = Path("/var/lib/voicebot/turns.jsonl")
DEFAULT_MONITOR_DIR = Path("/var/spool/asterisk/monitor")


def _resolve_path(env_var: str, default: Path) -> Path:
    override = os.environ.get(env_var)
    return Path(override) if override else default


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
        events_path=_resolve_path("VOICEBOT_EVENTS_LOG", DEFAULT_EVENTS_LOG),
        usage_path=_resolve_path("VOICEBOT_USAGE_LOG", DEFAULT_USAGE_LOG),
        turns_path=_resolve_path("VOICEBOT_TURNS_LOG", DEFAULT_TURNS_LOG),
        monitor_dir=_resolve_path("VOICEBOT_MONITOR_DIR", DEFAULT_MONITOR_DIR),
        basic_auth_user=basic_auth_user,
        basic_auth_password=basic_auth_password,
    )
