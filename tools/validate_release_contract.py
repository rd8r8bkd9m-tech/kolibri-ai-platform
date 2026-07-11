#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
manifest = json.loads((ROOT / 'configs/fone-os/manifest.json').read_text(encoding='utf-8'))
package = json.loads((ROOT / 'frontend/package.json').read_text(encoding='utf-8'))
backend = (ROOT / 'backend/app/main.py').read_text(encoding='utf-8')

assert package['version'] == version, (package['version'], version)
assert 'vista-os-11.1-product-release' in manifest['version'], manifest['version']
assert manifest['product'] == 'Vista OS 11.1 Product Release'
assert 'vista-os-11.1-product-release' in backend
assert manifest.get('release', {}).get('demo_fallbacks') is False
assert manifest.get('rendering_model', {}).get('type') == 'single_window_workbench'

required = [
    '.env.example', 'docker-compose.yml', 'Dockerfile.backend', 'Dockerfile.frontend',
    'frontend/public/manifest.webmanifest', 'frontend/public/sw.js',
    'frontend/public/icons/vista-192.png', 'frontend/public/icons/vista-512.png',
    'apps/vista-desktop/src-tauri/Cargo.toml',
    'apps/vista-desktop/src-tauri/tauri.conf.json',
    'apps/vista-desktop/src-tauri/capabilities/default.json',
    'crates/vista-core/Cargo.toml', 'crates/vista-core/src/lib.rs',
    'crates/vista-policy/Cargo.toml', 'crates/vista-policy/src/lib.rs',
    'scripts/release-check.sh', 'tools/http_product_smoke.py', 'tools/backup_restore_check.py',
]
missing = [path for path in required if not (ROOT / path).is_file()]
assert not missing, missing

api_client = (ROOT / 'frontend/src/api/client.js').read_text(encoding='utf-8')
assert 'VITE_API_URL' in api_client
assert 'VITE_API_BASE' not in (ROOT / 'scripts/build-desktop-frontend.sh').read_text(encoding='utf-8')
assert 'VITE_API_BASE' not in (ROOT / 'scripts/dev-fone.sh').read_text(encoding='utf-8')
assert 'VITE_API_URL' in (ROOT / 'scripts/dev-fone.sh').read_text(encoding='utf-8')
assert re.search(r'VISTA_OWNER_ACCESS_TOKEN=', (ROOT / '.env.example').read_text(encoding='utf-8'))
print(f'ok: Vista release contract {version}; manifest={manifest["version"]}')

assert not list((ROOT / 'crates').glob('fone-*')), 'legacy Fone Rust crates must not ship'
