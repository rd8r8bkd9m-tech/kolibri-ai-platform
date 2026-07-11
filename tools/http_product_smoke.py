#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class HttpApi:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip('/') + '/api'

    def request(self, method: str, path: str, payload: Any = None, token: str | None = None, headers: dict[str, str] | None = None) -> tuple[Any, dict[str, str]]:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        request_headers = {'Content-Type': 'application/json', **(headers or {})}
        if token:
            request_headers['Authorization'] = f'Bearer {token}'
        request = urllib.request.Request(self.base + path, data=body, method=method, headers=request_headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
            content_type = response.headers.get('content-type', '')
            parsed = json.loads(data.decode('utf-8')) if 'application/json' in content_type and data else data
            return parsed, dict(response.headers.items())

    def session(self, role: str = 'client_pro', admin_token: str | None = None) -> tuple[dict[str, Any], str]:
        headers = {'X-Vista-Admin-Token': admin_token} if admin_token else None
        result, _ = self.request('POST', '/os/session', {'role': role, 'device': 'api'}, headers=headers)
        return result['session'], result['token']


def main() -> int:
    parser = argparse.ArgumentParser(description='Vista OS real HTTP product smoke')
    parser.add_argument('--base-url', default='http://127.0.0.1:18080')
    parser.add_argument('--report', default='var/release-check/http-product-smoke.json')
    args = parser.parse_args()
    api = HttpApi(args.base_url)

    live, live_headers = api.request('GET', '/live')
    ready, _ = api.request('GET', '/ready')
    first_session, first_token = api.session()
    second_session, second_token = api.session()

    estimate, _ = api.request('POST', '/estimates', {
        'city': 'Москва',
        'client': {'name': 'Клиент Vista', 'phone': '+79990000000', 'email': 'client@example.test'},
        'project': {'name': 'Ремонт квартиры 72 м²', 'area': 72, 'address': 'Москва'},
        'assumptions': ['Цены действительны 14 дней'],
        'items': [
            {'section': 'Демонтаж', 'name': 'Снятие покрытий', 'unit': 'м²', 'qty': 72, 'price': 350, 'coef': 1},
            {'section': 'Стены', 'name': 'Шпатлёвка и грунт', 'unit': 'м²', 'qty': 180, 'price': 420, 'coef': 1},
        ],
    }, first_token)
    assert estimate['summary']['subtotal'] == 100800, estimate['summary']

    first_item = estimate['items'][0]
    estimate, _ = api.request('PATCH', f"/estimates/{estimate['id']}/items/{first_item['id']}", {'qty': 80, 'price': 400}, first_token)
    assert estimate['summary']['subtotal'] == 107600, estimate['summary']

    generated, _ = api.request('POST', f"/estimates/{estimate['id']}/documents", {}, first_token)
    assert generated['task']['state'] == 'completed'
    kinds = {item['kind'] for item in generated['artifacts']}
    required = {'proposal_pdf', 'estimate_xlsx', 'proposal_docx', 'estimate_json', 'assumptions_md'}
    assert required <= kinds, kinds

    signatures = {'proposal_pdf': b'%PDF', 'estimate_xlsx': b'PK', 'proposal_docx': b'PK'}
    downloaded: dict[str, dict[str, Any]] = {}
    for artifact in generated['artifacts']:
        if artifact['kind'] not in signatures:
            continue
        raw, _ = api.request('GET', f"/artifacts/{artifact['id']}/download", token=first_token)
        assert isinstance(raw, bytes)
        assert raw.startswith(signatures[artifact['kind']])
        checksum = hashlib.sha256(raw).hexdigest()
        assert checksum == artifact['sha256']
        downloaded[artifact['kind']] = {'bytes': len(raw), 'sha256': checksum}

    share, _ = api.request('POST', f"/estimates/{estimate['id']}/share", {'ttl_hours': 24}, first_token)
    public, _ = api.request('GET', f"/public/share/{share['token']}")
    assert public['estimate']['id'] == estimate['id']
    public_pdf = next(item for item in public['artifacts'] if item['kind'] == 'proposal_pdf')
    public_raw, _ = api.request('GET', f"/public/share/{share['token']}/artifacts/{public_pdf['id']}/download")
    assert isinstance(public_raw, bytes) and public_raw.startswith(b'%PDF')

    try:
        api.request('GET', f"/estimates/{estimate['id']}", token=second_token)
        raise AssertionError('tenant isolation failed')
    except urllib.error.HTTPError as error:
        assert error.code == 404

    restored, _ = api.request('PATCH', f"/os/session/{first_session['id']}", {
        'active_estimate_id': estimate['id'],
        'windows': [{'component_id': 'estimate'}],
        'chat': [{'id': 'smoke', 'kind': 'user', 'text': 'открой смету'}],
    }, first_token)
    assert restored['active_estimate_id'] == estimate['id']
    restored_again, _ = api.request('GET', f"/os/session/{first_session['id']}", token=first_token)
    assert restored_again['windows'][0]['component_id'] == 'estimate'

    revoked, _ = api.request('DELETE', f"/estimates/{estimate['id']}/shares/{share['token']}", token=first_token)
    assert revoked['status'] == 'revoked'
    try:
        api.request('GET', f"/public/share/{share['token']}")
        raise AssertionError('revoked link still works')
    except urllib.error.HTTPError as error:
        assert error.code == 404

    report = {
        'status': 'passed',
        'live': live,
        'ready': ready,
        'request_id_present': bool(live_headers.get('X-Request-ID') or live_headers.get('x-request-id')),
        'first_session': first_session['id'],
        'second_session': second_session['id'],
        'estimate_id': estimate['id'],
        'estimate_total': estimate['summary']['total'],
        'document_kinds': sorted(kinds),
        'downloads': downloaded,
        'public_share_download_bytes': len(public_raw),
        'tenant_isolation': 'passed',
        'workspace_restore': 'passed',
        'share_revoke': 'passed',
    }
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"ok: Vista HTTP product smoke passed; report={path}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
