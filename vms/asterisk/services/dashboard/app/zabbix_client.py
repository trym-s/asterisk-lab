"""Small read-only Zabbix API client for dashboard uptime tiles."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_HOSTS = [
    {"host": "asterisk-deb13-cloudinit", "label": "Asterisk"},
    {"host": "opensips-sbc-deb13-cloudinit", "label": "SBC"},
    {"host": "monitoring-deb13-cloudinit", "label": "Monitoring"},
]


@dataclass(frozen=True)
class ZabbixConfig:
    api_url: str | None
    api_token: str | None
    timeout_s: int = 5


def unavailable_summary(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "error": reason,
        "hosts": [
            {
                "host": item["host"],
                "label": item["label"],
                "status": "unavailable",
                "available": False,
                "uptime_pct": None,
                "current_uptime_s": None,
                "samples": 0,
            }
            for item in DEFAULT_HOSTS
        ],
    }


class ZabbixClient:
    def __init__(self, config: ZabbixConfig):
        self.config = config

    def _call(self, method: str, params: object) -> object:
        if not self.config.api_url or not self.config.api_token:
            raise RuntimeError("zabbix api url/token not configured")
        payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        request = urllib.request.Request(
            self.config.api_url,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_token}",
            },
        )
        with urllib.request.urlopen(request, timeout=self.config.timeout_s) as response:
            data = json.loads(response.read())
        if "error" in data:
            message = data["error"].get("message") or data["error"]
            raise RuntimeError(f"{method}: {message}")
        return data["result"]

    def uptime_summary(self, since_ts: float) -> dict[str, Any]:
        try:
            return self._uptime_summary(since_ts)
        except (RuntimeError, urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            return unavailable_summary(str(exc))

    def _uptime_summary(self, since_ts: float) -> dict[str, Any]:
        hosts = self._call(
            "host.get",
            {
                "filter": {"host": [item["host"] for item in DEFAULT_HOSTS]},
                "output": ["hostid", "host", "name"],
            },
        )
        hosts_by_name = {host["host"]: host for host in hosts}
        host_ids = [host["hostid"] for host in hosts]
        items = []
        if host_ids:
            items = self._call(
                "item.get",
                {
                    "hostids": host_ids,
                    "filter": {"key_": ["agent.ping", "system.uptime"]},
                    "output": ["itemid", "hostid", "key_", "lastvalue", "lastclock"],
                },
            )
        items_by_host: dict[str, dict[str, dict[str, Any]]] = {}
        for item in items:
            items_by_host.setdefault(item["hostid"], {})[item["key_"]] = item

        rows = []
        now_ts = int(time.time())
        for wanted in DEFAULT_HOSTS:
            host = hosts_by_name.get(wanted["host"])
            if not host:
                rows.append(_host_unavailable(wanted, "host missing"))
                continue
            item_map = items_by_host.get(host["hostid"], {})
            ping_item = item_map.get("agent.ping")
            uptime_item = item_map.get("system.uptime")
            if not ping_item:
                rows.append(_host_unavailable(wanted, "agent.ping missing"))
                continue
            history = self._call(
                "history.get",
                {
                    "history": 3,
                    "itemids": [ping_item["itemid"]],
                    "time_from": int(since_ts),
                    "time_till": now_ts,
                    "output": ["clock", "value"],
                    "sortfield": "clock",
                    "sortorder": "ASC",
                },
            )
            values = [1 if str(row.get("value")) == "1" else 0 for row in history]
            if values:
                uptime_pct = round(sum(values) * 100 / len(values), 1)
                samples = len(values)
            else:
                uptime_pct = 100.0 if str(ping_item.get("lastvalue")) == "1" else 0.0
                samples = 1 if ping_item.get("lastvalue") not in (None, "") else 0
            current_up = str(ping_item.get("lastvalue")) == "1"
            rows.append(
                {
                    "host": wanted["host"],
                    "label": wanted["label"],
                    "status": "up" if current_up else "down",
                    "available": current_up,
                    "uptime_pct": uptime_pct,
                    "current_uptime_s": _int_or_none((uptime_item or {}).get("lastvalue")),
                    "samples": samples,
                }
            )
        return {"available": True, "error": None, "hosts": rows}


def _host_unavailable(wanted: dict[str, str], reason: str) -> dict[str, Any]:
    return {
        "host": wanted["host"],
        "label": wanted["label"],
        "status": "unavailable",
        "available": False,
        "uptime_pct": None,
        "current_uptime_s": None,
        "samples": 0,
        "error": reason,
    }


def _int_or_none(value: object) -> int | None:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None
