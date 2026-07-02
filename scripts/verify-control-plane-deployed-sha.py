#!/usr/bin/env python3
"""Verify deployed Control Plane file hashes before strict canaries.

This script is intentionally read-only: it compares local repository files with
the Control Plane `/v1/filesystem` endpoint and exits non-zero on drift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_PATHS = [
    "ops/factory_control.py",
    "ops/telegram_superfactory.py",
    "scripts/preflight-factory-control-runtime.sh",
    "ops/systemd/kolibri-factory-control.service",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def control_plane_manifest(base_url: str, paths: list[str], timeout: float) -> dict[str, Any]:
    query = urllib.parse.urlencode([("path", path) for path in paths])
    url = f"{base_url.rstrip('/')}/v1/filesystem?{query}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", "replace")
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {"status": "blocked", "error": f"http_{exc.code}", "data": {"files": []}}
    return json.loads(payload)


def envelope_data(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def verify(repo_root: Path, base_url: str, paths: list[str], timeout: float) -> dict[str, Any]:
    manifest = envelope_data(control_plane_manifest(base_url, paths, timeout))
    deployed = {
        entry.get("path"): entry
        for entry in manifest.get("files", [])
        if isinstance(entry, dict)
    }
    results = []
    for rel_path in paths:
        local_path = repo_root / rel_path
        local_exists = local_path.is_file()
        local_sha = sha256_file(local_path) if local_exists else ""
        remote = deployed.get(rel_path, {})
        remote_sha = str(remote.get("sha256") or "")
        remote_exists = bool(remote.get("exists"))
        results.append({
            "path": rel_path,
            "local_exists": local_exists,
            "remote_exists": remote_exists,
            "local_sha256": local_sha,
            "remote_sha256": remote_sha,
            "match": local_exists and remote_exists and local_sha == remote_sha,
        })
    ok = all(item["match"] for item in results)
    return {
        "status": "ok" if ok else "drift",
        "control_plane": base_url.rstrip("/"),
        "repo_root": str(repo_root),
        "files": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate strict canaries on deployed Control Plane file SHA integrity.")
    parser.add_argument("--control-plane-url", required=True, help="Base URL, for example http://10.99.0.10:9101")
    parser.add_argument("--repo-root", default=".", help="Local Git checkout to compare against")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("paths", nargs="*", default=DEFAULT_PATHS)
    args = parser.parse_args()

    result = verify(Path(args.repo_root).resolve(), args.control_plane_url, list(args.paths), args.timeout)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "ok":
        print("control_plane_deployed_sha_drift", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
