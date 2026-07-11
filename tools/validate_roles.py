
#!/usr/bin/env python3
from pathlib import Path
import json, sys
root = Path(__file__).resolve().parents[1]
jsonl = root / 'agents/roles/catalog.jsonl'
if not jsonl.exists():
    print('roles catalog.jsonl missing'); sys.exit(1)
count = 0
for line in jsonl.read_text(encoding='utf-8').splitlines():
    if not line.strip(): continue
    item = json.loads(line); count += 1
    for key in ['role_id','name_ru','name_en','department','capabilities','allowed_actions','forbidden_actions','required_artifacts']:
        if key not in item:
            print(f'role {count} missing {key}'); sys.exit(1)
if count < 1000:
    print(f'expected >=1000 roles, got {count}'); sys.exit(1)
print(f'ok: validated {count} machine-readable agent roles')
