#!/usr/bin/env python3
"""Provision lab Zabbix hosts and items for SBC + Asterisk observability."""
from __future__ import annotations

import json
import os
import urllib.request


ZABBIX_URL = os.environ.get("ZABBIX_URL", "http://127.0.0.1/zabbix/api_jsonrpc.php")
ZABBIX_USER = os.environ.get("ZABBIX_USER", "Admin")
ZABBIX_PASSWORD = os.environ.get("ZABBIX_PASSWORD", "zabbix")

SBC_HOST = os.environ.get("SBC_ZABBIX_HOST", "opensips-sbc-deb13-cloudinit")
SBC_VISIBLE = "OpenSIPS SBC"
SBC_IP = os.environ.get("SBC_IP", "192.168.122.3")

ASTERISK_HOST = os.environ.get("ASTERISK_ZABBIX_HOST", "asterisk-deb13-cloudinit")
ASTERISK_VISIBLE = "Asterisk PBX"
ASTERISK_IP = os.environ.get("ASTERISK_IP", "192.168.122.247")


def zbx(method: str, params: object, auth: str | None = None) -> object:
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    if auth:
        payload["auth"] = auth
    request = urllib.request.Request(
        ZABBIX_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.loads(response.read())
    if "error" in data:
        raise RuntimeError(f"{method}: {data['error']}")
    return data["result"]


def ensure_group(auth: str, name: str) -> str:
    groups = zbx("hostgroup.get", {"filter": {"name": [name]}}, auth)
    if groups:
        return groups[0]["groupid"]
    return zbx("hostgroup.create", {"name": name}, auth)["groupids"][0]


def ensure_host(auth: str, groupid: str, host: str, visible: str, ip: str) -> tuple[str, str]:
    hosts = zbx("host.get", {"filter": {"host": [host]}, "selectInterfaces": "extend"}, auth)
    if hosts:
        hostid = hosts[0]["hostid"]
        interfaces = hosts[0].get("interfaces", [])
        if interfaces:
            return hostid, interfaces[0]["interfaceid"]
        interfaceid = zbx("hostinterface.create", {
                "hostid": hostid,
                "type": 1,
                "main": 1,
                "useip": 1,
                "ip": ip,
                "dns": "",
                "port": "10050",
            }, auth)["interfaceids"][0]
        return hostid, interfaceid
    result = zbx("host.create", {
        "host": host,
        "name": visible,
        "groups": [{"groupid": groupid}],
        "interfaces": [{
            "type": 1,
            "main": 1,
            "useip": 1,
            "ip": ip,
            "dns": "",
            "port": "10050",
        }],
    }, auth)
    hostid = result["hostids"][0]
    hosts = zbx("host.get", {"hostids": hostid, "selectInterfaces": "extend"}, auth)
    return hostid, hosts[0]["interfaces"][0]["interfaceid"]


def ensure_item(auth: str, hostid: str, interfaceid: str, name: str, key: str, value_type: int = 3) -> None:
    existing = zbx("item.get", {"hostids": hostid, "filter": {"key_": key}}, auth)
    params = {
        "name": name,
        "key_": key,
        "hostid": hostid,
        "interfaceid": interfaceid,
        "type": 0,
        "value_type": value_type,
        "delay": "30s",
        "history": "7d",
        "trends": "30d",
    }
    if existing:
        # item.update rejects hostid; keep only mutable fields.
        update = {k: v for k, v in params.items() if k not in {"hostid", "key_"}}
        zbx("item.update", {"itemid": existing[0]["itemid"], **update}, auth)
    else:
        zbx("item.create", params, auth)


SBC_ITEMS = [
    ("OpenSIPS MI available", "lab.opensips.mi.ping"),
    ("OpenSIPS received requests", "lab.opensips.stat[rcv_requests]"),
    ("OpenSIPS forwarded requests", "lab.opensips.stat[fwd_requests]"),
    ("OpenSIPS dropped requests", "lab.opensips.stat[drop_requests]"),
    ("OpenSIPS error requests", "lab.opensips.stat[err_requests]"),
    ("OpenSIPS 2xx transactions", "lab.opensips.stat[2xx_transactions]"),
    ("OpenSIPS 4xx transactions", "lab.opensips.stat[4xx_transactions]"),
    ("OpenSIPS 5xx transactions", "lab.opensips.stat[5xx_transactions]"),
    ("OpenSIPS in-use transactions", "lab.opensips.stat[tm:inuse_transactions]"),
    ("OpenSIPS UAC transactions", "lab.opensips.stat[tm:UAC_transactions]"),
    ("OpenSIPS UAS transactions", "lab.opensips.stat[tm:UAS_transactions]"),
    ("OpenSIPS INVITE timeouts", "lab.opensips.stat[tm:timeout_finalresponse_inv]"),
    ("OpenSIPS bad URIs received", "lab.opensips.stat[core:bad_URIs_rcvd]"),
    ("OpenSIPS bad message headers", "lab.opensips.stat[core:bad_msg_hdr]"),
    ("OpenSIPS shared memory used", "lab.opensips.stat[used_size]"),
    ("OpenSIPS shared memory free", "lab.opensips.stat[free_size]"),
    ("OpenSIPS service active", "lab.systemd.active[opensips]"),
    ("rtpengine service active", "lab.systemd.active[rtpengine-daemon]"),
    ("rtpengine CLI available", "lab.rtpengine[ping]"),
    ("rtpengine current sessions", "lab.rtpengine[sessions_current]"),
    ("rtpengine total managed sessions", "lab.rtpengine[sessions_total]"),
    ("rtpengine relayed packets", "lab.rtpengine[packets]"),
    ("rtpengine relayed bytes", "lab.rtpengine[bytes]"),
    ("rtpengine relay errors", "lab.rtpengine[errors]"),
    ("rtpengine session timeouts", "lab.rtpengine[timeouts]"),
]

ASTERISK_ITEMS = [
    ("Asterisk service active", "lab.systemd.active[asterisk]"),
    ("Asterisk active channels", "lab.asterisk[channels]"),
    ("Asterisk active calls", "lab.asterisk[calls_active]"),
    ("Asterisk calls processed", "lab.asterisk[calls_processed]"),
    ("Asterisk PJSIP contacts total", "lab.asterisk[endpoints_total]"),
    ("Asterisk PJSIP contacts available", "lab.asterisk[endpoints_available]"),
    ("Asterisk recordings count", "lab.asterisk[recordings_count]"),
    ("Asterisk recordings bytes", "lab.asterisk[recordings_bytes]"),
    ("Transcriber service active", "lab.systemd.active[transcriber]"),
]


def main() -> None:
    auth = zbx("user.login", {"username": ZABBIX_USER, "password": ZABBIX_PASSWORD})
    groupid = ensure_group(auth, "Asterisk Lab")

    sbc_hostid, sbc_iface = ensure_host(auth, groupid, SBC_HOST, SBC_VISIBLE, SBC_IP)
    for name, key in SBC_ITEMS:
        ensure_item(auth, sbc_hostid, sbc_iface, name, key)
    print(f"provisioned {SBC_HOST} ({SBC_IP}) with {len(SBC_ITEMS)} items")

    ast_hostid, ast_iface = ensure_host(auth, groupid, ASTERISK_HOST, ASTERISK_VISIBLE, ASTERISK_IP)
    for name, key in ASTERISK_ITEMS:
        ensure_item(auth, ast_hostid, ast_iface, name, key)
    print(f"provisioned {ASTERISK_HOST} ({ASTERISK_IP}) with {len(ASTERISK_ITEMS)} items")


if __name__ == "__main__":
    main()
