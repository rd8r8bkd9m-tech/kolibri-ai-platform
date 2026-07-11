#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def sign(secret: str, method: str, path: str, body: bytes) -> str:
    message = method.upper().encode('utf-8') + b'\n' + ('/api' + path).encode('utf-8') + b'\n' + body
    return hmac.new(secret.encode('utf-8'), message, hashlib.sha256).hexdigest()


class Api:
    def __init__(self, control_url: str, node_token: str | None = None, signing_secret: str | None = None) -> None:
        self.base = control_url.rstrip('/') + '/api'
        self.node_token = node_token
        self.signing_secret = signing_secret
        self.owner_bearer: str | None = None

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        auth: str = 'owner',
        timeout: int = 20,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        body = b'' if payload is None else json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        headers = {'Content-Type': 'application/json', **(extra_headers or {})}
        if auth == 'owner':
            if not self.owner_bearer:
                raise RuntimeError('owner session is not initialized')
            headers['Authorization'] = f'Bearer {self.owner_bearer}'
        elif auth == 'node':
            if self.node_token:
                headers['X-Vista-Node-Token'] = self.node_token
            if self.signing_secret:
                headers['X-Vista-Node-Signature'] = sign(self.signing_secret, method, path, body)
        req = urllib.request.Request(self.base + path, data=None if payload is None else body, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = res.read()
        return json.loads(data.decode('utf-8')) if data else None

    def login_owner(self, owner_access_token: str) -> dict[str, Any]:
        result = self.request(
            'POST',
            '/os/session',
            {'role': 'owner', 'device': 'api'},
            auth='none',
            extra_headers={'X-Vista-Admin-Token': owner_access_token},
        )
        self.owner_bearer = result['token']
        return result['session']


def run_agent(control_url: str, node_id: str, capability: str, token: str | None, signing_secret: str | None) -> None:
    cmd = [
        sys.executable,
        str(ROOT / 'ops' / 'node_agent.py'),
        '--control-url', control_url,
        '--node-id', node_id,
        '--mode', 'CONTROLLED_WRITE',
        '--once',
        '--capability', capability,
    ]
    env = os.environ.copy()
    if token:
        env['VISTA_NODE_JOIN_TOKEN'] = token
    if signing_secret:
        env['VISTA_NODE_SIGNING_SECRET'] = signing_secret
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description='Vista authenticated factory canary')
    parser.add_argument('--control-url', default=os.environ.get('VISTA_CONTROL_URL', 'http://127.0.0.1:8000'))
    parser.add_argument('--owner-access-token', default=os.environ.get('VISTA_OWNER_ACCESS_TOKEN') or os.environ.get('VISTA_ADMIN_TOKEN') or 'vista-local-owner')
    parser.add_argument('--join-token', default=os.environ.get('VISTA_NODE_JOIN_TOKEN'))
    parser.add_argument('--signing-secret', default=os.environ.get('VISTA_NODE_SIGNING_SECRET'))
    parser.add_argument('--report', default=str(ROOT / 'var' / 'canary' / 'FACTORY_CANARY_REPORT.md'))
    args = parser.parse_args()

    api = Api(args.control_url, args.join_token, args.signing_secret)
    health = api.request('GET', '/health', auth='none')
    assert health['status'] == 'ok', health
    owner = api.login_owner(args.owner_access_token)

    tasks = [
        api.request('POST', '/factory/tasks', {
            'title': 'Vista canary health probe',
            'kind': 'health_probe',
            'required_capabilities': ['health.probe'],
            'required_artifacts': ['RESULT.md'],
            'priority': 1,
        }),
        api.request('POST', '/factory/tasks', {
            'title': 'Vista canary estimate artifact',
            'kind': 'estimate_artifact',
            'required_capabilities': ['estimate.artifacts'],
            'required_artifacts': ['RESULT.md'],
            'payload': {'estimate_id': 'canary-estimate'},
            'priority': 2,
        }),
    ]

    run_agent(args.control_url, 'canary-worker-health', 'health.probe', args.join_token, args.signing_secret)
    run_agent(args.control_url, 'canary-worker-estimate', 'estimate.artifacts', args.join_token, args.signing_secret)

    completed = []
    for task in tasks:
        fetched = api.request('GET', f"/factory/tasks/{task['id']}")
        if fetched['state'] != 'completed':
            raise AssertionError(f"task {task['id']} is {fetched['state']}")
        events = [event['event'] for event in fetched['events']]
        required_events = ['task.created', 'lease.granted', 'lease.heartbeat', 'worker.executed', 'artifact.written', 'verifier.checked', 'task.completed']
        missing = [event for event in required_events if event not in events]
        if missing:
            raise AssertionError(f"task {task['id']} missing events {missing}")
        artifacts = fetched['artifacts']
        if not artifacts or not artifacts[0].get('sha256'):
            raise AssertionError(f"task {task['id']} missing sha256 artifact")
        completed.append(fetched)

    fleet = api.request('GET', '/fleet/health')
    stats = api.request('GET', '/factory/stats')
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '# Vista Factory Canary Report',
        '',
        f"control_url: {args.control_url}",
        f"owner_session: {owner['id']}",
        f"health: {health['status']}",
        f"completed_tasks: {len(completed)}",
        f"fleet_registered_nodes: {fleet['summary']['registered']}",
        f"factory_states: `{json.dumps(stats['states'], ensure_ascii=False)}`",
        '',
        '## Completed tasks',
    ]
    for task in completed:
        lines.append(f"- `{task['id']}` — {task['title']} — artifact `{task['artifacts'][0]['id']}` sha256 `{task['artifacts'][0]['sha256']}`")
    report_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f"ok: Vista authenticated factory canary passed; report={report_path}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
