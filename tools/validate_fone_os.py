
#!/usr/bin/env python3
from pathlib import Path
import json, sys
manifest = json.loads((Path(__file__).resolve().parents[1] / 'configs/fone-os/manifest.json').read_text(encoding='utf-8'))
errors = []
for key in ['version','roles','components','intents','capabilities']:
    if key not in manifest: errors.append(f'missing {key}')
for cid, comp in manifest.get('components', {}).items():
    for cap in comp.get('required', []):
        if cap not in manifest['capabilities'] and cap != '*': errors.append(f'component {cid} references missing cap {cap}')
    for intent in comp.get('intents', []):
        if intent != '*' and intent not in manifest['intents']: errors.append(f'component {cid} references missing intent {intent}')
for rid, role in manifest.get('roles', {}).items():
    if role.get('plan') not in manifest.get('plans', {}): errors.append(f'role {rid} references missing plan')
if errors:
    print('\n'.join(errors)); sys.exit(1)
print(f"ok: Vista OS manifest {manifest['version']}; roles={len(manifest['roles'])} components={len(manifest['components'])} intents={len(manifest['intents'])}")
