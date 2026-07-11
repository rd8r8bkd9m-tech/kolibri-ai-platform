#!/usr/bin/env python3
"""Select a deterministic reachable registrar candidate from replicated state."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
from pathlib import Path


SAFE_NODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def endpoint_host(value: object) -> str:
    endpoint = str(value or "").strip()
    if not endpoint or any(char.isspace() for char in endpoint) or "@" in endpoint or "/" in endpoint:
        raise ValueError("registrar_endpoint_invalid")
    if endpoint.startswith("["):
        closing = endpoint.find("]")
        if closing < 2 or closing + 1 >= len(endpoint) or endpoint[closing + 1] != ":":
            raise ValueError("registrar_endpoint_invalid")
        host, port = endpoint[1:closing], endpoint[closing + 2 :]
    else:
        if endpoint.count(":") != 1:
            raise ValueError("registrar_endpoint_invalid")
        host, port = endpoint.rsplit(":", 1)
    if not host or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError("registrar_endpoint_invalid")
    return host


def load_candidates(path: Path) -> list[tuple[str, str]]:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 4 * 1024 * 1024:
            raise ValueError("mesh_manifest_invalid")
        payload = json.loads(handle.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("mesh_manifest_invalid")
    records = payload.get("records")
    if isinstance(records, dict):
        values = records.values()
    elif isinstance(payload.get("peers"), dict):
        values = payload["peers"].values()
    else:
        raise ValueError("mesh_manifest_invalid")
    candidates: list[tuple[str, str]] = []
    for record in values:
        if not isinstance(record, dict) or record.get("tombstone") is True:
            continue
        node_id = str(record.get("node_id") or "")
        if not SAFE_NODE.fullmatch(node_id) or not record.get("endpoint"):
            continue
        candidates.append((node_id, endpoint_host(record["endpoint"])))
    if not candidates:
        raise ValueError("mesh_registrar_not_found")
    return sorted(set(candidates))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    node_id, host = load_candidates(Path(args.manifest))[0]
    print(json.dumps({"node_id": node_id, "ssh_host": host}, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
