#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {'.git', 'node_modules', 'dist', 'var', '__pycache__', '.pytest_cache', 'docs/archive'}
TEXT_SUFFIXES = {'.py', '.js', '.jsx', '.ts', '.tsx', '.json', '.yaml', '.yml', '.toml', '.md', '.sh', '.html', '.css', '.txt'}
PATTERNS = {
    'private_key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'github_pat': re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b'),
    'aws_access_key': re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    'openai_secret': re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b'),
}

findings: list[dict[str, object]] = []
for path in ROOT.rglob('*'):
    if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
        continue
    relative = path.relative_to(ROOT)
    rendered = relative.as_posix()
    if any(part in SKIP_PARTS for part in relative.parts) or rendered.startswith('docs/archive/'):
        continue
    try:
        content = path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        continue
    for name, pattern in PATTERNS.items():
        for match in pattern.finditer(content):
            findings.append({'rule': name, 'path': rendered, 'offset': match.start()})

for forbidden in ['.env', 'id_rsa', 'id_ed25519']:
    candidate = ROOT / forbidden
    if candidate.exists():
        findings.append({'rule': 'forbidden_secret_file', 'path': forbidden})

frontend = '\n'.join(
    path.read_text(encoding='utf-8')
    for path in (ROOT / 'frontend' / 'src').rglob('*')
    if path.is_file() and path.suffix in {'.js', '.jsx', '.ts', '.tsx'}
)
if 'OPENAI_API_KEY' in frontend:
    findings.append({'rule': 'upstream_secret_in_frontend', 'path': 'frontend/src'})

compose = (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')
backend_docker = (ROOT / 'Dockerfile.backend').read_text(encoding='utf-8')
if 'USER vista' not in backend_docker:
    findings.append({'rule': 'backend_container_not_unprivileged', 'path': 'Dockerfile.backend'})
if 'no-new-privileges:true' not in compose.replace(' ', ''):
    findings.append({'rule': 'compose_missing_no_new_privileges', 'path': 'docker-compose.yml'})

report = {'status': 'passed' if not findings else 'failed', 'findings': findings}
output = ROOT / 'var' / 'security-scan.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
if findings:
    raise SystemExit(json.dumps(report, ensure_ascii=False, indent=2))
print(f'ok: Vista source security scan passed; report={output}')
