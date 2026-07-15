#!/usr/bin/env python3
"""SSH-based heartbeat poller — runs on Home, polls servers via SSH, updates Control Plane.

Alternative to push heartbeats when WireGuard is broken.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

CONTROL_PLANE = "http://127.0.0.1:9101"

SERVERS = [
    ("agent-01", "root@31.57.27.128"),
    ("agent-02", "root@213.232.204.223"),
    ("agent-03", "root@188.130.206.204"),
    ("agent-04", "root@31.59.41.146"),
    ("agent-05", "root@31.56.196.10"),
    ("agent-06", "root@45.39.33.252"),
    ("agent-07", "root@46.8.225.34"),
    ("agent-08", "root@31.59.105.200"),
    ("agent-09", "root@95.182.84.254"),
    ("agent-10", "root@217.60.38.191"),
    ("highload", "root@45.38.139.182"),
    ("paris", "root@95.182.83.60"),
    ("reserve242", "root@31.57.26.242"),
    ("server-kfrm", "root@217.60.63.31"),
    ("uiap", "root@31.57.26.151"),
]


def ssh_cmd(host: str, cmd: str, timeout: int = 10) -> str:
    try:
        r = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", host, cmd],
            capture_output=True, text=True, timeout=timeout
        )
        return r.stdout.strip()
    except Exception:
        return ""


def collect_info(host: str) -> dict:
    info = {}

    load = ssh_cmd(host, "cat /proc/loadavg | awk '{print $1,$2,$3}'")
    if load:
        parts = load.split()
        info["cpu_load"] = [float(x) for x in parts[:3]]
        info["cpu_count"] = int(ssh_cmd(host, "nproc") or "1")

    mem = ssh_cmd(host, "free -b | awk '/Mem:/{print $2,$3}'")
    if mem:
        total, used = mem.split()
        info["ram_total"] = int(total)
        info["ram_used"] = int(used)
        info["ram_percent"] = round(int(used) / int(total) * 100, 1)

    disk = ssh_cmd(host, "df -B1 / | awk 'NR==2{print $5}'")
    if disk:
        info["disk_percent"] = int(disk.replace("%", ""))

    uptime = ssh_cmd(host, "cat /proc/uptime | awk '{print $1}'")
    if uptime:
        info["uptime_sec"] = float(uptime)

    hostname = ssh_cmd(host, "hostname")
    if hostname:
        info["hostname"] = hostname

    load1 = info.get("cpu_load", [0])[0]
    cores = info.get("cpu_count", 1)
    info["health"] = "degraded" if load1 > cores * 2 or info.get("disk_percent", 0) > 95 else "online"

    return info


def send_heartbeat(node_id: str, data: dict) -> dict:
    body = {
        "node_id": node_id,
        "health": data.get("health", "online"),
        "cpu_load": data.get("cpu_load"),
        "cpu_count": data.get("cpu_count"),
        "ram_percent": data.get("ram_percent"),
        "ram_total": data.get("ram_total"),
        "disk_percent": data.get("disk_percent"),
        "hostname": data.get("hostname"),
        "agent_id": f"ssh-poller-{node_id}",
    }
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{CONTROL_PLANE}/v1/nodes/{node_id}/heartbeat",
        data=payload, method="POST",
    )
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def poll_all():
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    results = []
    for node_id, host in SERVERS:
        info = collect_info(host)
        if info:
            resp = send_heartbeat(node_id, info)
            load = info.get("cpu_load", [0])[0]
            ram = info.get("ram_percent", "?")
            disk = info.get("disk_percent", "?")
            status = "ok" if "error" not in resp else f"err: {resp['error']}"
            print(f"[{now}] {node_id:<20} load={load:<5} ram={ram}% disk={disk}% -> {status}")
            results.append({"node_id": node_id, "ok": "error" not in resp})
        else:
            print(f"[{now}] {node_id:<20} UNREACHABLE")
            results.append({"node_id": node_id, "ok": False})
    return results


if __name__ == "__main__":
    import sys
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    print(f"SSH heartbeat poller: interval={interval}s, servers={len(SERVERS)}")
    while True:
        poll_all()
        time.sleep(interval)
