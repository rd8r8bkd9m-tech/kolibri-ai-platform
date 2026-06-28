#!/usr/bin/env python3
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MESH_CHAT = os.environ.get('KOLIBRI_MESH_CHAT_URL', 'http://10.99.0.1:8082')
MESH_COORD = os.environ.get('KOLIBRI_MESH_COORD_URL', 'http://10.99.0.1:8080')
CONTROL = os.environ.get('KOLIBRI_FACTORY_CONTROL_URL', 'http://10.99.0.2:9101')
AGENT_ID = os.environ.get('KOLIBRI_MESH_BRIDGE_AGENT_ID', 'orchestrator')
STATE_PATH = Path(os.environ.get('KOLIBRI_MESH_BRIDGE_STATE', '/var/lib/kolibri-mesh-bridge/state.json'))
LOG_PATH = Path(os.environ.get('KOLIBRI_MESH_BRIDGE_LOG', '/var/log/kolibri/mesh-control-bridge.jsonl'))
DEFAULT_EXECUTOR = os.environ.get('KOLIBRI_MESH_DEFAULT_EXECUTOR', 'home-live')
POLL_SECONDS = float(os.environ.get('KOLIBRI_MESH_BRIDGE_POLL_SECONDS', '5'))

STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def now():
    return datetime.now(timezone.utc).isoformat()


def log(event, **fields):
    rec = {'time': now(), 'event': event, **fields}
    with LOG_PATH.open('a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')


def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {'seen_messages': [], 'created_tasks': {}, 'mesh_nodes': {}}


def save_state(state):
    tmp = STATE_PATH.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(STATE_PATH)


def request_json(method, url, payload=None, timeout=8):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode('utf-8')
        return json.loads(body) if body else None


def post_control(path, payload):
    return request_json('POST', CONTROL + path, payload, timeout=12)


def sync_mesh_nodes(state):
    nodes = request_json('GET', MESH_COORD + '/api/nodes', timeout=8) or []
    active = {}
    for node in nodes:
        node_id = str(node.get('id') or '').strip()
        if not node_id:
            continue
        shadow_id = 'mesh-' + node_id
        active[node_id] = {
            'node_id': node_id,
            'ip': node.get('ip'),
            'status': node.get('status'),
            'last_seen': node.get('last_seen'),
            'role': node.get('role'),
        }
        payload = {
            'node_id': shadow_id,
            'agent_id': f'mesh-{node_id}',
            'hostname': node.get('name') or node_id,
            'capabilities': ['mesh', 'mesh_node'],
            'health': 'online' if node.get('status') == 'online' else 'degraded',
            'mesh': True,
            'mesh_source_node_id': node_id,
            'mesh_ip': node.get('ip'),
            'mesh_last_seen': node.get('last_seen'),
            'mesh_role': node.get('role'),
        }
        try:
            post_control('/v1/nodes/register', payload)
        except Exception as exc:
            log('control_register_failed', node_id=node_id, error=repr(exc))
    state['mesh_nodes'] = active
    return len(active)


def get_messages():
    url = MESH_CHAT + '/api/messages?agent_id=' + urllib.request.quote(AGENT_ID)
    data = request_json('GET', url, timeout=8)
    return data or []


def respond(message_id, result):
    payload = {'message_id': message_id, 'from': AGENT_ID, 'result': result}
    try:
        request_json('POST', MESH_CHAT + '/api/respond', payload, timeout=8)
    except Exception as exc:
        log('mesh_respond_failed', message_id=message_id, error=repr(exc))


def create_task_from_message(msg):
    message_id = msg.get('id') or f'mesh-{int(time.time())}'
    task_text = str(msg.get('task') or '').strip()
    payload = msg.get('payload') if isinstance(msg.get('payload'), dict) else {}
    kind = str(payload.get('kind') or '')
    if kind in {'owner_chat_message', 'orchestrator_chat_response'}:
        return None, {'chat_only': True, 'status': 'ignored'}
    if not task_text:
        task_text = 'Mesh message without task text; inspect payload and answer via mesh.'
    safe_suffix = ''.join(c if c.isalnum() else '-' for c in message_id)[-32:]
    task_id = payload.get('task_id') or f'MESH-{safe_suffix}'
    target = payload.get('target_node') or payload.get('node') or DEFAULT_EXECUTOR
    envelope = {
        'task_id': task_id,
        'kind': payload.get('kind') or 'owner_remote_task',
        'root_goal_id': payload.get('root_goal_id') or 'KOL-MESH-FIRST-001',
        'target_node': target,
        'required_capability': payload.get('required_capability') or 'generic_implementation',
        'priority': payload.get('priority') or 'P0',
        'project_path': payload.get('project_path') or '/home/ladik/kolibri-ai-platform',
        'branch': payload.get('branch') or 'codex/factory-ha-spool-20260627',
        'objective': task_text,
        'mesh_message_id': message_id,
        'mesh_from': msg.get('from'),
        'mesh_to': msg.get('to'),
        'mesh_role': msg.get('role'),
        'mesh_first': True,
        'evidence_required': payload.get('evidence_required') or ['node_id','agent_id','pid','heartbeat','worktree','branch','remote_logs','result_path'],
    }
    created = post_control('/v1/tasks', envelope)
    return task_id, created


def main():
    state = load_state()
    log('bridge_started', mesh_chat=MESH_CHAT, mesh_coord=MESH_COORD, control=CONTROL, agent_id=AGENT_ID)
    while True:
        try:
            node_count = sync_mesh_nodes(state)
            messages = get_messages()
            seen = set(state.get('seen_messages', []))
            for msg in messages:
                mid = msg.get('id')
                if not mid or mid in seen:
                    continue
                try:
                    task_id, created = create_task_from_message(msg)
                    seen.add(mid)
                    state['seen_messages'] = list(seen)[-1000:]
                    if task_id is None:
                        respond(mid, {'status': 'seen', 'transport': 'mesh', 'mode': 'chat'})
                        log('mesh_chat_seen', message_id=mid, node_count=node_count)
                    else:
                        state.setdefault('created_tasks', {})[mid] = task_id
                        respond(mid, {'status': 'accepted', 'task_id': task_id, 'transport': 'mesh', 'executor': created.get('lease_owner') or 'queued'})
                        log('mesh_task_accepted', message_id=mid, task_id=task_id, node_count=node_count)
                except Exception as exc:
                    seen.add(mid)
                    state['seen_messages'] = list(seen)[-1000:]
                    respond(mid, {'status': 'failed', 'error': str(exc), 'transport': 'mesh'})
                    log('mesh_task_failed', message_id=mid, error=repr(exc))
            save_state(state)
        except Exception as exc:
            log('bridge_loop_error', error=repr(exc))
        time.sleep(POLL_SECONDS)

if __name__ == '__main__':
    main()
