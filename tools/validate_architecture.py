#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []

manifest = json.loads((ROOT / "configs/kolibri-os/system-manifest.json").read_text())
if manifest["authority"]["control_plane"] != "home": errors.append("Control Plane authority must be home")
if manifest["public_model"] != "kolibri": errors.append("Only public model kolibri is allowed")
if manifest["ux"]["permanent_vertical_menu"] is not False: errors.append("Permanent vertical menu is forbidden")


compatibility_path = ROOT / "packages/contracts/openai-compatibility.json"
if not compatibility_path.is_file():
    errors.append("OpenAI compatibility matrix is missing")
else:
    compatibility = json.loads(compatibility_path.read_text())
    if compatibility.get("public_model") != "kolibri":
        errors.append("OpenAI compatibility matrix must expose only the public model kolibri")
    auth = compatibility.get("authentication", {})
    if not auth.get("api_keys_stored_as_sha256"):
        errors.append("OpenAI-compatible API keys must be stored as SHA-256 hashes")
    gateway = compatibility.get("provider_gateway", {})
    if gateway.get("mode") != "server_side_fail_closed":
        errors.append("Provider gateway must be server-side and fail-closed")
    if gateway.get("client_project_headers_forwarded") is not False:
        errors.append("Client provider scope headers must not be forwarded upstream")

for forbidden in ["App.jsx", "App.css", "kolibriApi.js"]:
    matches = list(ROOT.rglob(forbidden))
    if matches: errors.append(f"Forbidden legacy monolith present: {matches}")

for path in (ROOT / "apps/shell/src").rglob("*.tsx"):
    text = path.read_text()
    if "fetch(" in text and "src/api/" not in str(path):
        errors.append(f"Transport call outside api client: {path.relative_to(ROOT)}")

for path in ROOT.rglob("*"):
    if path.resolve() in {Path(__file__).resolve(), (ROOT / "tools/security_scan.py").resolve()}:
        continue
    if not path.is_file() or ".git" in path.parts or "node_modules" in path.parts or ("docs" in path.parts and "spec" in path.parts):
        continue
    if path.suffix not in {".py", ".ts", ".tsx", ".js", ".json", ".md", ".yml", ".yaml", ".toml", ".sh"}: continue
    try: text = path.read_text(errors="ignore")
    except OSError: continue
    if "Kolibri could not produce a verified response" in text:
        errors.append(f"Forbidden generic error string: {path.relative_to(ROOT)}")
    if "10.99.0.2" in text or "primary-candidate" in text:
        errors.append(f"Legacy routing identity: {path.relative_to(ROOT)}")

if errors:
    print("\n".join(f"ERROR: {item}" for item in errors), file=sys.stderr)
    raise SystemExit(1)
print("ok: architecture gate passed")
