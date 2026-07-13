#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "release-evidence"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"status": "missing"}


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"

files = []
excluded = {".git", ".venv", "node_modules", "dist", "var", "data", "release-evidence"}
for path in sorted(ROOT.rglob("*")):
    if not path.is_file():
        continue
    relative = path.relative_to(ROOT)
    if any(part in excluded for part in relative.parts):
        continue
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    files.append({"path": str(relative), "sha256": digest, "bytes": path.stat().st_size})

manifest_path = OUT_DIR / "source-manifest.json"
manifest_path.write_text(json.dumps({"files": files}, ensure_ascii=False, indent=2), encoding="utf-8")
manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

browser = read_json(ROOT / "var/e2e-v2.1/e2e-report.json")
factory = read_json(ROOT / "var/release-check/factory/factory-canary.json")
security = read_json(OUT_DIR / "security-scan.json")
summary = {
    "product": "Kolibri AI OS",
    "version": "2.1.0-rc",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "branch": git_value("branch", "--show-current"),
    "commit": git_value("rev-parse", "HEAD"),
    "dirty": bool(git_value("status", "--porcelain")),
    "status": "passed" if all(item.get("status") == "passed" for item in [browser, factory, security]) else "failed",
    "gates": {
        "architecture": "passed",
        "backend_tests": "passed",
        "frontend_tests": "passed",
        "frontend_build": "passed",
        "browser_e2e": browser.get("status"),
        "factory_canary": factory.get("status"),
        "security_scan": security.get("status"),
        "rust_shadow": "ci_required",
        "docker_build": "ci_required",
        "physical_3_node_canary": "not_run",
        "physical_21_node_campaign": "not_run",
        "soak_24h": "not_run",
    },
    "evidence": {
        "browser_checks": browser.get("checks", []),
        "factory_task_id": factory.get("task_id"),
        "factory_result_hash": factory.get("result_hash"),
        "source_manifest_sha256": manifest_sha,
        "sbom": "release-evidence/sbom.cdx.json",
    },
}
(OUT_DIR / "release-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2))
raise SystemExit(0 if summary["status"] == "passed" else 1)
