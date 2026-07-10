#!/usr/bin/env python3
"""Small, dependency-free replicated WireGuard peer registry.

Every node runs the same service.  A peer enrollment is written atomically to
the local manifest and gossiped to configured mesh peers; applying the
manifest is delegated to the local `kolibri-mesh-apply-peers` helper.
"""
from __future__ import annotations
import json, os, subprocess, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

STATE = Path(os.getenv("KOLIBRI_MESH_STATE", "/var/lib/kolibri-mesh/peers.json"))
PEER_DIR = Path(os.getenv("KOLIBRI_MESH_PEER_DIR", "/etc/wireguard/kolibri-peers.d"))
PORT = int(os.getenv("KOLIBRI_MESH_REGISTRY_PORT", "9291"))
SUBNET_PREFIX = os.getenv("KOLIBRI_MESH_PREFIX", "10.99.0.")
LOCK = threading.Lock()

def local_mesh_ip():
    configured = os.getenv("KOLIBRI_MESH_BIND")
    if configured: return configured
    out = subprocess.check_output(["ip", "-4", "-o", "addr", "show", "wg-kolibri"], text=True)
    return out.split()[3].split("/", 1)[0]

def read_state():
    try: return json.loads(STATE.read_text())
    except (FileNotFoundError, json.JSONDecodeError): return {"peers": {}}

def write_state(data):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=STATE.parent, prefix=".peers-")
    with os.fdopen(fd, "w") as f: json.dump(data, f, sort_keys=True, indent=2); f.write("\n")
    os.replace(name, STATE)

def apply_peer(peer):
    PEER_DIR.mkdir(parents=True, exist_ok=True)
    ip = peer["mesh_ip"]
    endpoint = f"Endpoint = {peer['endpoint']}\n" if peer.get("endpoint") else ""
    (PEER_DIR / f"{ip}.conf").write_text(f"# {peer['node_id']}\n[Peer]\nPublicKey = {peer['public_key']}\n{endpoint}AllowedIPs = {ip}/32\nPersistentKeepalive = 25\n")
    subprocess.run(["/usr/local/sbin/kolibri-mesh-apply-peers"], check=True)

def merge(remote):
    changed = False
    with LOCK:
        data = read_state()
        for ip, peer in remote.get("peers", {}).items():
            current = data["peers"].get(ip, {})
            if int(peer.get("revision", 0)) > int(current.get("revision", 0)):
                data["peers"][ip] = peer; apply_peer(peer); changed = True
        if changed: write_state(data)
    return changed

def discover_forever():
    while True:
        for n in range(1, 255):
            try:
                remote = json.loads(urlopen(f"http://{SUBNET_PREFIX}{n}:{PORT}/v1/mesh/peers", timeout=.35).read())
                merge(remote)
            except Exception: pass
        time.sleep(10)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/v1/mesh/peers": self.send_error(404); return
        data = json.dumps(read_state()).encode(); self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(data)
    def do_POST(self):
        if self.path != "/v1/mesh/peers": self.send_error(404); return
        try:
            peer = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            if not {"node_id","public_key","mesh_ip"} <= peer.keys(): raise ValueError("missing peer fields")
            with LOCK:
                data = read_state()
                current = data["peers"].get(peer["mesh_ip"], {})
                peer.setdefault("revision", max(time.time_ns(), int(current.get("revision", 0)) + 1))
                data["peers"][peer["mesh_ip"]] = peer; write_state(data); apply_peer(peer)
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"status":"ok"}')
        except Exception as exc: self.send_error(400, str(exc))
    def log_message(self, *_): pass

if __name__ == "__main__":
    threading.Thread(target=discover_forever, daemon=True).start()
    ThreadingHTTPServer((local_mesh_ip(), PORT), Handler).serve_forever()
