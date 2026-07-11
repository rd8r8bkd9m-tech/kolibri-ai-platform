import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_endpoint_module():
    spec = importlib.util.spec_from_file_location(
        "control_plane_endpoint_contract",
        ROOT / "ops" / "control_plane_endpoint.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_resolves_home_from_dynamic_mesh_membership(tmp_path, monkeypatch):
    endpoint = load_endpoint_module()
    manifest = tmp_path / "peers.json"
    manifest.write_text(
        json.dumps(
            {
                "peers": {
                    "10.99.0.2": {"node_id": "main", "mesh_ip": "10.99.0.2"},
                    "10.99.0.1": {"node_id": "home", "mesh_ip": "10.99.0.1"},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URL", raising=False)
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URLS", raising=False)

    assert endpoint.resolve_home_control_plane_url(manifest_path=manifest) == "http://10.99.0.1:9101"


def test_rejects_multiple_control_plane_authorities(monkeypatch):
    endpoint = load_endpoint_module()
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URL", raising=False)
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URLS", raising=False)

    with pytest.raises(endpoint.ControlPlaneEndpointError, match="multiple_control_plane_authorities_forbidden"):
        endpoint.resolve_home_control_plane_url(
            "http://10.99.0.1:9101",
            "http://10.99.0.1:9101,http://10.99.0.2:9101",
        )


def test_fails_closed_without_home_membership(tmp_path, monkeypatch):
    endpoint = load_endpoint_module()
    manifest = tmp_path / "peers.json"
    manifest.write_text(json.dumps({"peers": {}}), encoding="utf-8")
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URL", raising=False)
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URLS", raising=False)

    with pytest.raises(endpoint.ControlPlaneEndpointError, match="canonical_home_control_plane_not_registered"):
        endpoint.resolve_home_control_plane_url(manifest_path=manifest)


def test_explicit_single_home_service_url_is_supported(tmp_path, monkeypatch):
    endpoint = load_endpoint_module()
    manifest = tmp_path / "peers.json"
    manifest.write_text(
        json.dumps({"peers": {"home": {"node_id": "home", "mesh_ip": "10.99.0.1"}}}),
        encoding="utf-8",
    )
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URL", raising=False)
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URLS", raising=False)
    monkeypatch.setattr(
        endpoint.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(endpoint.socket.AF_INET, endpoint.socket.SOCK_STREAM, 6, "", ("10.99.0.1", 0))],
    )

    assert endpoint.resolve_home_control_plane_url(
        "https://home-control.kolibri.internal/", manifest_path=manifest
    ) == (
        "https://home-control.kolibri.internal"
    )


@pytest.mark.parametrize(
    "legacy_url",
    [
        "http://10.99.0.2:9101",
        "http://main:9101",
        "https://primary-control.kolibri.internal",
    ],
)
def test_explicit_non_home_control_plane_authorities_are_rejected(tmp_path, legacy_url):
    endpoint = load_endpoint_module()
    manifest = tmp_path / "peers.json"
    manifest.write_text(
        json.dumps({"peers": {"home": {"node_id": "home", "mesh_ip": "10.99.0.1"}}}),
        encoding="utf-8",
    )

    with pytest.raises(endpoint.ControlPlaneEndpointError, match="control_plane_authority_not_home"):
        endpoint.resolve_home_control_plane_url(legacy_url, manifest_path=manifest)


def test_ambiguous_home_membership_fails_closed(tmp_path, monkeypatch):
    endpoint = load_endpoint_module()
    manifest = tmp_path / "peers.json"
    manifest.write_text(
        json.dumps(
            {
                "peers": [
                    {"node_id": "home", "mesh_ip": "10.99.0.1"},
                    {"node_id": "home", "mesh_ip": "10.99.0.7"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URL", raising=False)
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URLS", raising=False)

    with pytest.raises(endpoint.ControlPlaneEndpointError, match="membership_ambiguous"):
        endpoint.resolve_home_control_plane_url(manifest_path=manifest)


def test_server_identity_guard_allows_only_local_home_mesh_address(tmp_path):
    endpoint = load_endpoint_module()
    manifest = tmp_path / "peers.json"
    manifest.write_text(
        json.dumps({"peers": {"home": {"node_id": "home", "mesh_ip": "10.99.0.1"}}}),
        encoding="utf-8",
    )

    assert endpoint.assert_local_home_control_plane(
        manifest_path=manifest,
        local_addresses=["10.99.0.1/24"],
    ) == "10.99.0.1"
    with pytest.raises(endpoint.ControlPlaneEndpointError, match="control_plane_must_run_on_home"):
        endpoint.assert_local_home_control_plane(
            manifest_path=manifest,
            local_addresses=["10.99.0.2/24"],
        )


def test_loopback_endpoint_requires_manifest_bound_local_home_proof(tmp_path):
    endpoint = load_endpoint_module()
    manifest = tmp_path / "peers.json"
    manifest.write_text(
        json.dumps({"peers": {"dynamic-home": {"node_id": "home", "mesh_ip": "10.99.0.1"}}}),
        encoding="utf-8",
    )

    assert endpoint.resolve_home_control_plane_url(
        "http://127.0.0.1:19101",
        manifest_path=manifest,
        local_addresses=["10.99.0.1/24"],
    ) == "http://127.0.0.1:19101"

    with pytest.raises(endpoint.ControlPlaneEndpointError, match="control_plane_must_run_on_home"):
        endpoint.resolve_home_control_plane_url(
            "http://127.0.0.1:19101",
            manifest_path=manifest,
            local_addresses=["10.99.0.44/24"],
        )
