#!/usr/bin/env python3
"""Heartbeat agent — runs on each fleet node, sends health data to Control Plane.

Usage:
    python3 heartbeat_agent.py --node-id home --interval 30
    python3 heartbeat_agent.py --node-id qjns --once

Collects: CPU load, RAM, disk, uptime, running services.
Sends to Control Plane via POST /v1/nodes/{node_id}/heartbeat.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

CONTROL_PLANE = os.environ.get("FACTORY_CONTROL_URL", "http://192.168.88.210:9101")


def _run(cmd: str, timeout: int = 5) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def collect_system_info() -> dict:
    info: dict = {}

    # CPU load
    try:
        load1, load5, load15 = os.getloadavg()
        info["cpu_load"] = [round(load1, 2), round(load5, 2), round(load15, 2)]
        info["cpu_count"] = os.cpu_count() or 0
    except Exception:
        info["cpu_load"] = [0, 0, 0]
        info["cpu_count"] = 0

    # RAM
    try:
        mem = _run("free -b | awk '/Mem:/{print $2,$3,$4}'")
        if mem:
            total, used, free_ = mem.split()
            info["ram_total"] = int(total)
            info["ram_used"] = int(used)
            info["ram_free"] = int(free_)
            info["ram_percent"] = round(int(used) / int(total) * 100, 1) if int(total) > 0 else 0
        else:
            # macOS fallback
            total = _run("sysctl -n hw.memsize")
            info["ram_total"] = int(total) if total else 0
            info["ram_used"] = 0
            info["ram_free"] = 0
            info["ram_percent"] = 0
    except Exception:
        info["ram_percent"] = 0

    # Disk
    try:
        disk = _run("df -B1 / | awk 'NR==2{print $2,$3,$4,$5}'")
        if disk:
            total, used, free_, pct = disk.split()
            info["disk_total"] = int(total)
            info["disk_used"] = int(used)
            info["disk_free"] = int(free_)
            info["disk_percent"] = int(pct.replace("%", ""))
    except Exception:
        info["disk_percent"] = 0

    # Uptime
    try:
        uptime_s = _run("cat /proc/uptime | awk '{print $1}'")
        if uptime_s:
            info["uptime_sec"] = float(uptime_s)
        else:
            info["uptime_sec"] = 0
    except Exception:
        info["uptime_sec"] = 0

    # Hostname
    info["hostname"] = platform.node()

    # Load average status
    load1 = info.get("cpu_load", [0])[0]
    cores = info.get("cpu_count", 1)
    if load1 > cores * 2:
        info["health"] = "degraded"
    elif load1 > cores:
        info["health"] = "online"
    else:
        info["health"] = "online"

    # Disk critical
    if info.get("disk_percent", 0) > 95:
        info["health"] = "degraded"

    # RAM critical
    if info.get("ram_percent", 0) > 95:
        info["health"] = "degraded"

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
        "disk_total": data.get("disk_total"),
        "uptime_sec": data.get("uptime_sec"),
        "hostname": data.get("hostname"),
        "agent_id": f"heartbeat-{node_id}",
        "pid": os.getpid(),
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
    except urllib.error.HTTPError as e:
        return {"error": f"http_{e.code}"}
    except Exception as e:
        return {"error": str(e)}


def run_heartbeat_loop(node_id: str, interval: int = 30):
    print(f"[heartbeat] {node_id}: starting, interval={interval}s, control_plane={CONTROL_PLANE}")
    while True:
        try:
            info = collect_system_info()
            resp = send_heartbeat(node_id, info)
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            status = "ok" if "error" not in resp else f"error: {resp['error']}"
            load = info.get("cpu_load", [0])[0]
            ram = info.get("ram_percent", 0)
            disk = info.get("disk_percent", 0)
            print(f"[{ts}] {node_id}: load={load} ram={ram}% disk={disk}% -> {status}")
        except Exception as e:
            print(f"[heartbeat] {node_id}: error: {e}")
        time.sleep(interval)


def run_once(node_id: str):
    info = collect_system_info()
    resp = send_heartbeat(node_id, info)
    load = info.get("cpu_load", [0])[0]
    ram = info.get("ram_percent", 0)
    disk = info.get("disk_percent", 0)
    print(f"{node_id}: load={load} ram={ram}% disk={disk}% -> {json.dumps(resp)}")
    return resp


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kolibri Fleet Heartbeat Agent")
    parser.add_argument("--node-id", required=True, help="Node ID (e.g. home, qjns, agent-01)")
    parser.add_argument("--interval", type=int, default=30, help="Heartbeat interval in seconds")
    parser.add_argument("--once", action="store_true", help="Send one heartbeat and exit")
    parser.add_argument("--control-plane", default=CONTROL_PLANE, help="Control Plane URL")
    args = parser.parse_args()
    CONTROL_PLANE = args.control_plane

    if args.once:
        run_once(args.node_id)
    else:
        run_heartbeat_loop(args.node_id, args.interval)
