#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "release-evidence" / "sbom.cdx.json"
OUT.parent.mkdir(parents=True, exist_ok=True)
components: list[dict] = []

for raw in (ROOT / "services/api-gateway/requirements.txt").read_text().splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or line.startswith("-"):
        continue
    match = re.match(r"([A-Za-z0-9_.-]+)==([^\s;]+)", line)
    if match:
        name, version = match.groups()
        components.append({"type": "library", "name": name, "version": version, "purl": f"pkg:pypi/{name.lower()}@{version}"})

lock = json.loads((ROOT / "apps/shell/package-lock.json").read_text())
for package_path, package in (lock.get("packages") or {}).items():
    if not package_path.startswith("node_modules/") or not package.get("version"):
        continue
    name = package_path.removeprefix("node_modules/")
    version = str(package["version"])
    components.append({"type": "library", "name": name, "version": version, "purl": f"pkg:npm/{name.replace('@', '%40')}@{version}"})

for cargo in ROOT.glob("crates/*/Cargo.toml"):
    text = cargo.read_text()
    name = re.search(r'^name\s*=\s*"([^"]+)"', text, re.MULTILINE)
    version = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if name and version:
        components.append({"type": "library", "name": name.group(1), "version": version.group(1), "purl": f"pkg:cargo/{name.group(1)}@{version.group(1)}"})

seen: set[tuple[str, str]] = set()
deduped = []
for component in sorted(components, key=lambda item: (item["name"].lower(), item["version"])):
    key = (component["name"], component["version"])
    if key in seen:
        continue
    seen.add(key)
    deduped.append(component)

sbom = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.6",
    "serialNumber": f"urn:uuid:{uuid.uuid4()}",
    "version": 1,
    "metadata": {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "component": {"type": "application", "name": "Kolibri AI OS", "version": "2.1.0"},
    },
    "components": deduped,
}
OUT.write_text(json.dumps(sbom, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"ok: wrote CycloneDX SBOM with {len(deduped)} components to {OUT}")
