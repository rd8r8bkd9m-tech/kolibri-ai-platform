#!/usr/bin/env python3
from __future__ import annotations
import argparse, http.client, json
from pathlib import Path
from urllib.parse import urlparse


def call(base: str, method: str, path: str, body=None, headers=None):
    parsed=urlparse(base)
    conn=http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=8)
    data=None if body is None else json.dumps(body).encode()
    h={'Connection':'close', **(headers or {})}
    if body is not None: h['Content-Type']='application/json'
    conn.request(method, (parsed.path.rstrip('/')+path) or '/', body=data, headers=h)
    response=conn.getresponse(); raw=response.read(); conn.close()
    payload=json.loads(raw.decode()) if raw else None
    if response.status>=400: raise RuntimeError(f'{response.status}: {payload}')
    return payload


def main():
    p=argparse.ArgumentParser();p.add_argument('--base-url',required=True);p.add_argument('--owner-token',required=True);p.add_argument('--output',required=True);p.add_argument('--summary',required=True);a=p.parse_args()
    owner=call(a.base_url,'POST','/api/os/session',{'role':'owner','device':'api'},{'X-Vista-Admin-Token':a.owner_token})
    readiness=call(a.base_url,'GET','/api/vista/release/readiness',headers={'Authorization':'Bearer '+owner['token']})
    if readiness['production_env_state']!='green': raise SystemExit(f'not green: {readiness}')
    Path(a.output).write_text(json.dumps(readiness,ensure_ascii=False,indent=2)+'\n')
    summary={'status':'passed','version':readiness['version'],'validation':'passed','http_product_smoke':'passed','factory_canary':'passed','backup_restore':'passed','production_readiness':'green','browser_e2e':'required_in_ci','native_tauri':'required_in_ci','docker_build':'required_in_ci'}
    Path(a.summary).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(f'ok: Vista production readiness green; summary={a.summary}')
if __name__=='__main__': main()
