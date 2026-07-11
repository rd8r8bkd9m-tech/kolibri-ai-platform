from __future__ import annotations

import json

import pytest


@pytest.fixture
def canonical_home_control_plane(tmp_path, monkeypatch) -> str:
    """Provide the same fail-closed Home membership dependency as production."""

    manifest_path = tmp_path / "mesh" / "peers.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "cluster_id": "kolibri",
                "peers": {
                    "10.99.0.1": {
                        "node_id": "home",
                        "hostname": "home",
                        "mesh_ip": "10.99.0.1",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("KOLIBRI_MESH_MEMBERSHIP_MANIFEST", str(manifest_path))
    return "http://10.99.0.1:9101"
