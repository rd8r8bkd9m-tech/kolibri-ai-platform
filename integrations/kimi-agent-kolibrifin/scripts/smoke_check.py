#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
required = [
    ROOT / "source" / "kolibri-backend" / "app" / "main.py",
    ROOT / "source" / "kolibri-backend" / "requirements.txt",
    ROOT / "source" / "kolibri-v2" / "package.json",
    ROOT / "source" / "kolibri-v2" / "src" / "main.tsx",
    ROOT / "source" / "kolibri-web" / "index.html",
]
missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
assert manifest["id"] == "kimi-agent-kolibrifin"
assert not missing, f"missing required package files: {missing}"
print("Kimi Agent КолибриФин smoke OK")
