#!/usr/bin/env python3
"""Poll servers via SSH (through Home jump host) and send heartbeats to Control Plane."""

import json
import subprocess
import urllib.request

CONTROL = "http://192.168.88.210:9101"

HOSTVDS = [
    ("agent-01", "kolibri-home", "root@31.57.27.128"),
    ("agent-02", "kolibri-home", "root@213.232.204.223"),
    ("agent-03", "kolibri-home", "root@188.130.206.204"),
    ("agent-04", "kolibri-home", "root@31.59.41.146"),
    ("agent-05", "kolibri-home", "root@31.56.196.10"),
    ("agent-06", "kolibri-home", "root@45.39.33.252"),
    ("agent-07", "kolibri-home", "root@46.8.225.34"),
    ("agent-08", "kolibri-home", "root@31.59.105.200"),
    ("agent-09", "kolibri-home", "root@95.182.84.254"),
    ("agent-10", "kolibri-home", "root@217.60.38.191"),
    ("highload", "kolibri-home", "root@45.38.139.182"),
    ("paris", "kolibri-home", "root@95.182.83.60"),
    ("reserve242", "kolibri-home", "root@31.57.26.242"),
    ("server-kfrm", "kolibri-home", "root@217.60.63.31"),
    ("uiap", "kolibri-home", "root@31.57.26.151"),
]

DIRECT = [
    ("qjns", None, "kolibri-qjns"),
    ("9fts", None, "kolibri-9fts"),
    ("new", None, "kolibri-new"),
    ("primary-candidate", None, "kolibri-primary-codex"),
]


def ssh_cmd(jump, host, cmd):
    try:
        args = ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes"]
        if jump:
            args += ["-J", jump]
        args += [host, cmd]
        r = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:
        return ""


def send_heartbeat(node_id, data):
    body = {"node_id": node_id, "health": "online", "agent_id": "ssh-poller", **data}
    req = urllib.request.Request(
        f"{CONTROL}/v1/nodes/{node_id}/heartbeat",
        data=json.dumps(body).encode(), method="POST",
    )
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return "ok"
    except Exception as e:
        return f"err: {e}"


def poll_server(jump, host):
    load_raw = ssh_cmd(jump, host, "cat /proc/loadavg")
    if not load_raw:
        return None
    load_parts = load_raw.split()
    load1 = float(load_parts[0])

    ram_raw = ssh_cmd(jump, host, "free | awk '/Mem:/{print $2,$3}'")
    ram_pct = 0
    if ram_raw:
        total, used = ram_raw.split()
        ram_pct = round(int(used) / int(total) * 100, 1)

    disk_raw = ssh_cmd(jump, host, "df / | awk 'NR==2{print $5}'")
    disk_pct = 0
    if disk_raw:
        disk_pct = int(disk_raw.replace("%", ""))

    hostname = ssh_cmd(jump, host, "hostname")
    cpu_count = int(ssh_cmd(jump, host, "nproc") or "1")

    return {
        "cpu_load": [load1],
        "cpu_count": cpu_count,
        "ram_percent": ram_pct,
        "disk_percent": disk_pct,
        "hostname": hostname,
    }


def main():
    ok = 0
    fail = 0

    for node_id, jump, host in HOSTVDS + DIRECT:
        info = poll_server(jump, host)
        if info:
            result = send_heartbeat(node_id, info)
            load = info["cpu_load"][0]
            ram = info["ram_percent"]
            disk = info["disk_percent"]
            print(f"  {node_id:<22} load={load:<5} ram={ram}% disk={disk}% -> {result}")
            ok += 1
        else:
            print(f"  {node_id:<22} UNREACHABLE")
            fail += 1

    print(f"\nResult: {ok} ok, {fail} failed out of {len(HOSTVDS) + len(DIRECT)}")


if __name__ == "__main__":
    main()
