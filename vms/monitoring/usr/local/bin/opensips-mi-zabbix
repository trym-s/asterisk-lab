#!/usr/bin/env python3
"""Small JSON-RPC client for OpenSIPS mi_fifo, intended for Zabbix items."""
from __future__ import annotations

import json
import os
import select
import shutil
import sys
import tempfile
import time
from pathlib import Path


FIFO = Path(os.environ.get("OPENSIPS_MI_FIFO", "/run/opensips/opensips_fifo"))
REPLY_DIR = Path(os.environ.get("OPENSIPS_MI_REPLY_DIR", "/run/opensips"))


def fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def mi_request(method: str, params: list[object] | None = None) -> object:
    if not FIFO.exists():
        fail(f"missing OpenSIPS MI FIFO: {FIFO}")
    REPLY_DIR.mkdir(parents=True, exist_ok=True)
    reply_path = Path(tempfile.mktemp(prefix="zbx_mi_", dir=str(REPLY_DIR)))
    reply_name = reply_path.name
    os.mkfifo(reply_path, 0o660)
    try:
        shutil.chown(reply_path, group="opensips")
        os.chmod(reply_path, 0o660)
        payload = {"jsonrpc": "2.0", "method": method, "id": str(int(time.time() * 1000))}
        if params is not None:
            payload["params"] = params
        request = f":{reply_name}:{json.dumps(payload, separators=(',', ':'))}\n"
        fd = os.open(FIFO, os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, request.encode())
        finally:
            os.close(fd)

        reply_fd = os.open(reply_path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            ready, _, _ = select.select([reply_fd], [], [], 5)
            if not ready:
                fail("timeout waiting for OpenSIPS MI response")
            chunks = []
            while True:
                try:
                    chunk = os.read(reply_fd, 65536)
                except BlockingIOError:
                    if chunks:
                        break
                    raise
                if not chunk:
                    break
                chunks.append(chunk)
            response = b"".join(chunks).decode()
        finally:
            os.close(reply_fd)
    finally:
        try:
            reply_path.unlink()
        except FileNotFoundError:
            pass

    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        fail(response.strip() or "empty OpenSIPS MI response")
    if "error" in data:
        fail(json.dumps(data["error"], separators=(",", ":")))
    return data.get("result")


def stat_value(name: str) -> int:
    result = mi_request("get_statistics", [[name]])
    if isinstance(result, dict):
        if name in result:
            return int(result[name])
        for key, value in result.items():
            if key.endswith(f":{name}") or key == name:
                return int(value)
    if isinstance(result, list):
        for item in result:
            if isinstance(item, str) and item.startswith(f"{name} ="):
                return int(item.split("=", 1)[1].strip())
            if isinstance(item, str) and f":{name} =" in item:
                return int(item.split("=", 1)[1].strip())
    return 0


def main() -> None:
    if len(sys.argv) < 2:
        fail("usage: opensips-mi.py ping|raw <method> [params-json]|stat <name>")
    command = sys.argv[1]
    if command == "ping":
        result = mi_request("which")
        print(1 if result is not None else 0)
    elif command == "raw":
        if len(sys.argv) < 3:
            fail("usage: opensips-mi.py raw <method> [params-json]")
        if len(sys.argv) > 3:
            params = json.loads(sys.argv[3])
        elif sys.argv[2] == "get_statistics":
            params = [["all"]]
        else:
            params = None
        print(json.dumps(mi_request(sys.argv[2], params), separators=(",", ":")))
    elif command == "stat":
        if len(sys.argv) != 3:
            fail("usage: opensips-mi.py stat <name>")
        print(stat_value(sys.argv[2]))
    else:
        fail(f"unknown command: {command}")


if __name__ == "__main__":
    main()
