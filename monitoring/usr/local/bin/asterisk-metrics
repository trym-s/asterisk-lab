#!/usr/bin/env python3
"""Small Asterisk CLI wrapper for Zabbix UserParameters.

Runs ``sudo -n /usr/sbin/asterisk -rx <cmd>`` and parses the output. The
``zabbix`` OS user is granted NOPASSWD access to these specific commands via
/etc/sudoers.d/zabbix-asterisk (installed by setup-zabbix-agent.sh).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


ASTERISK = "/usr/sbin/asterisk"
RECORDINGS_DIR = Path(os.environ.get("ASTERISK_RECORDINGS_DIR", "/var/spool/asterisk/monitor"))


def rx(command: str) -> str:
    result = subprocess.run(
        ["sudo", "-n", ASTERISK, "-rx", command],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"asterisk -rx {command!r} failed")
    return result.stdout


def channels_count() -> tuple[int, int, int]:
    """Return (active_channels, active_calls, calls_processed)."""
    out = rx("core show channels count")
    active = calls = processed = 0
    for line in out.splitlines():
        line = line.strip()
        if match := re.match(r"(\d+)\s+active channels?", line):
            active = int(match.group(1))
        elif match := re.match(r"(\d+)\s+active calls?", line):
            calls = int(match.group(1))
        elif match := re.match(r"(\d+)\s+calls? processed", line):
            processed = int(match.group(1))
    return active, calls, processed


def contacts_status() -> tuple[int, int]:
    """Return (total_contacts, available_contacts) from ``pjsip show contacts``."""
    out = rx("pjsip show contacts")
    total = avail = 0
    for line in out.splitlines():
        if "Contact:" not in line or "<Aor" in line:
            continue
        # Contact:  1001/sip:1001@... hash Avail  1.201
        total += 1
        if re.search(r"\bAvail\b", line):
            avail += 1
    return total, avail


def recordings() -> tuple[int, int]:
    """Return (wav_count, total_bytes) under RECORDINGS_DIR."""
    if not RECORDINGS_DIR.is_dir():
        return 0, 0
    count = 0
    total = 0
    for entry in RECORDINGS_DIR.iterdir():
        if entry.is_file():
            total += entry.stat().st_size
            if entry.suffix == ".wav":
                count += 1
    return count, total


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: asterisk-metrics.py <metric>", file=sys.stderr)
        raise SystemExit(2)
    metric = sys.argv[1]
    try:
        if metric == "channels":
            print(channels_count()[0])
        elif metric == "calls_active":
            print(channels_count()[1])
        elif metric == "calls_processed":
            print(channels_count()[2])
        elif metric == "endpoints_total":
            print(contacts_status()[0])
        elif metric == "endpoints_available":
            print(contacts_status()[1])
        elif metric == "recordings_count":
            print(recordings()[0])
        elif metric == "recordings_bytes":
            print(recordings()[1])
        else:
            print(f"unknown metric: {metric}", file=sys.stderr)
            raise SystemExit(2)
    except Exception as err:  # noqa: BLE001 - Zabbix reads exit code + stderr
        print(str(err), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
