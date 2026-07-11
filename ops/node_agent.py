#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import platform
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def read_memory_percent() -> float:
    try:
        values = {}
        with open('/proc/meminfo', 'r', encoding='utf-8') as fh:
            for line in fh:
                key, rest = line.split(':', 1)
                values[key] = int(rest.strip().split()[0])
        total = values.get('MemTotal', 1)
        available = values.get('MemAvailable', 0)
        return round((1 - available / total) * 100, 1)
    except Exception:
        return 0.0


def read_disk_percent(path: str = '/') -> float:
    try:
        usage = os.statvfs(path)
        total = usage.f_blocks * usage.f_frsize
        available = usage.f_bavail * usage.f_frsize
        return round((1 - available / total) * 100, 1) if total else 0.0
    except Exception:
        return 0.0


def read_cpu_percent() -> float:
    try:
        load, _, _ = os.getloadavg()
        return round(min(100.0, load / max(1, os.cpu_count() or 1) * 100), 1)
    except Exception:
        return 0.0


class VistaClient:
    def __init__(self, control_url: str, node_id: str, join_token: str | None = None, signing_secret: str | None = None) -> None:
        self.api = control_url.rstrip('/') + '/api'
        self.node_id = node_id
        self.join_token = join_token
        self.signing_secret = signing_secret

    def _headers(self, method: str, path: str, body: bytes) -> dict[str, str]:
        headers = {'Content-Type': 'application/json', 'X-Vista-Node-Id': self.node_id}
        if self.join_token:
            headers['X-Vista-Node-Token'] = self.join_token
        if self.signing_secret:
            message = method.upper().encode('utf-8') + b'\n' + ('/api' + path).encode('utf-8') + b'\n' + body
            headers['X-Vista-Node-Signature'] = hmac.new(self.signing_secret.encode('utf-8'), message, hashlib.sha256).hexdigest()
        return headers

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 10) -> Any:
        data = b'' if payload is None else json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        req = urllib.request.Request(
            self.api + path,
            data=None if payload is None else data,
            method=method,
            headers=self._headers(method, path, data),
        )
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = res.read()
        return json.loads(body.decode('utf-8')) if body else None


def build_heartbeat(args: argparse.Namespace, busy: int = 0) -> dict[str, Any]:
    return {
        'node_id': args.node_id,
        'hostname': platform.node() or args.node_id,
        'role': args.role,
        'status': 'online',
        'mode': args.mode,
        'capabilities': args.capabilities,
        'workers_total': args.workers,
        'workers_busy': busy,
        'metrics': {'cpu': read_cpu_percent(), 'ram': read_memory_percent(), 'disk': read_disk_percent(args.workdir)},
        'metadata': {'runtime': 'vista-node-agent', 'python': sys.version.split()[0], 'platform': platform.platform()},
    }


def execute_known_task(task: dict[str, Any], args: argparse.Namespace) -> list[dict[str, str]]:
    kind = task.get('kind')
    payload = task.get('payload') or {}
    workdir = Path(args.workdir) / task['id']
    workdir.mkdir(parents=True, exist_ok=True)
    if kind == 'health_probe':
        text = (
            '# Vista Node Health Probe\n\n'
            f"node_id: {args.node_id}\n"
            f"hostname: {platform.node()}\n"
            f"cpu: {read_cpu_percent()}\n"
            f"ram: {read_memory_percent()}\n"
            f"disk: {read_disk_percent(args.workdir)}\n"
            f"task_id: {task['id']}\n"
            f"payload: {json.dumps(payload, ensure_ascii=False)}\n"
        )
    elif kind == 'estimate_artifact':
        text = (
            '# Vista Estimate Worker Result\n\n'
            f"task_id: {task['id']}\n"
            f"estimate_id: {payload.get('estimate_id', 'not-provided')}\n"
            'status: artifact prepared by node-agent\n'
        )
    else:
        text = (
            '# Vista Worker Result\n\n'
            f"task_id: {task['id']}\n"
            f"kind: {kind}\n"
            'status: unsupported kind handled as safe no-op result\n'
        )
    result_path = workdir / 'RESULT.md'
    result_path.write_text(text, encoding='utf-8')
    return [{'name': 'RESULT.md', 'content_type': 'text/markdown', 'payload': text}]


def run_once(client: VistaClient, args: argparse.Namespace) -> bool:
    client.request('POST', '/nodes/register', build_heartbeat(args, busy=0))
    lease = client.request('POST', '/factory/tasks/lease', {'node_id': args.node_id, 'lease_seconds': args.lease_seconds})
    if not lease or not lease.get('task'):
        return False
    task = lease['task']
    lease_id = lease['lease']['id']
    client.request('POST', f"/nodes/{args.node_id}/heartbeat", build_heartbeat(args, busy=1))
    try:
        client.request('POST', f"/factory/tasks/{task['id']}/lease-heartbeat", {'lease_id': lease_id})
        artifacts = execute_known_task(task, args)
        client.request('POST', f"/factory/tasks/{task['id']}/complete", {'lease_id': lease_id, 'node_id': args.node_id, 'artifacts': artifacts})
        print(f"completed {task['id']} kind={task.get('kind')}")
        return True
    except Exception as exc:
        client.request('POST', f"/factory/tasks/{task['id']}/fail", {'lease_id': lease_id, 'node_id': args.node_id, 'error': str(exc), 'traceback': traceback.format_exc()})
        raise
    finally:
        client.request('POST', f"/nodes/{args.node_id}/heartbeat", build_heartbeat(args, busy=0))


def main() -> int:
    parser = argparse.ArgumentParser(description='Vista OS node-agent')
    parser.add_argument('--node-id', default=os.environ.get('NODE_ID', 'local-worker'))
    parser.add_argument('--control-url', default=os.environ.get('CONTROL_URL', 'http://127.0.0.1:8000'))
    parser.add_argument('--role', default=os.environ.get('NODE_ROLE', 'worker'))
    parser.add_argument('--mode', default=os.environ.get('MODE', 'CONTROLLED_WRITE'))
    parser.add_argument('--workers', type=int, default=int(os.environ.get('WORKERS_TOTAL', '1')))
    parser.add_argument('--workdir', default=os.environ.get('VISTA_NODE_WORKDIR', '/tmp/vista-node'))
    parser.add_argument('--poll-seconds', type=float, default=float(os.environ.get('POLL_SECONDS', '5')))
    parser.add_argument('--lease-seconds', type=int, default=int(os.environ.get('LEASE_SECONDS', '120')))
    parser.add_argument('--join-token', default=os.environ.get('VISTA_NODE_JOIN_TOKEN'))
    parser.add_argument('--signing-secret', default=os.environ.get('VISTA_NODE_SIGNING_SECRET'))
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--capability', action='append', dest='capabilities')
    args = parser.parse_args()
    if not args.capabilities:
        args.capabilities = ['health.probe', 'estimate.artifacts', 'factory.local']
    Path(args.workdir).mkdir(parents=True, exist_ok=True)
    client = VistaClient(args.control_url, args.node_id, args.join_token, args.signing_secret)
    print(f"Vista node-agent node_id={args.node_id} control={args.control_url} mode={args.mode} capabilities={args.capabilities}")
    while True:
        try:
            did_work = run_once(client, args)
            if args.once:
                return 0 if did_work else 2
            if not did_work:
                client.request('POST', f"/nodes/{args.node_id}/heartbeat", build_heartbeat(args, busy=0))
        except urllib.error.URLError as exc:
            print(f"control unreachable: {exc}", file=sys.stderr)
        except Exception as exc:
            print(f"node-agent error: {exc}", file=sys.stderr)
            traceback.print_exc()
            if args.once:
                return 1
        time.sleep(args.poll_seconds)


if __name__ == '__main__':
    raise SystemExit(main())
