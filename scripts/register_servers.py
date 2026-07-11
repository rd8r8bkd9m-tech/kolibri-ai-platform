#!/usr/bin/env python3
"""Verify automatic fleet registration through canonical Home.

The historical hard-coded 21-node POST loop has been retired.  New servers
self-register when the unified provisioner starts Agent Host, while mesh
membership is replicated independently.  This compatibility command now
proves that every current mesh member has appeared in Home membership and
never manufactures an online heartbeat.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.control_plane_endpoint import DEFAULT_MESH_MANIFEST  # noqa: E402
from ops.factory_registry import load_registered_servers  # noqa: E402


def mesh_node_ids(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    peers = payload.get("peers", {}) if isinstance(payload, dict) else {}
    records = peers.values() if isinstance(peers, dict) else peers if isinstance(peers, list) else []
    return {
        str(peer.get("node_id") or "").strip()
        for peer in records
        if isinstance(peer, dict) and str(peer.get("node_id") or "").strip()
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-url")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MESH_MANIFEST)
    parser.add_argument("--wait-seconds", type=int, default=0)
    args = parser.parse_args(argv)
    if args.wait_seconds < 0 or args.wait_seconds > 600:
        parser.error("--wait-seconds must be between 0 and 600")

    expected = mesh_node_ids(args.manifest)
    deadline = time.monotonic() + args.wait_seconds
    while True:
        registered = load_registered_servers(
            args.control_url,
            manifest_path=args.manifest,
        )
        actual = {record.node_id for record in registered}
        missing = sorted(expected - actual)
        stale = sorted(
            record.node_id
            for record in registered
            if record.node_id in expected and not record.safe_to_schedule
        )
        if not missing and not stale:
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "authority": "home",
                        "mesh_members": len(expected),
                        "registered_fresh": len(expected),
                    },
                    sort_keys=True,
                )
            )
            return 0
        if time.monotonic() >= deadline:
            print(
                json.dumps(
                    {
                        "status": "degraded",
                        "authority": "home",
                        "mesh_members": len(expected),
                        "missing_registration": missing,
                        "stale_registration": stale,
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 1
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
