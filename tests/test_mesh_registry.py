from __future__ import annotations

import base64
import http.client
import importlib.util
import json
import shutil
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_registry() -> ModuleType:
    name = "kolibri_mesh_registry_contract"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "ops" / "mesh_registry.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def registry() -> ModuleType:
    return load_registry()


def public_key(seed: int) -> str:
    return base64.b64encode(bytes([seed]) * 32).decode("ascii")


def make_ssh_identity(tmp_path: Path, name: str) -> tuple[Path, str]:
    ssh_keygen = shutil.which("ssh-keygen")
    assert ssh_keygen is not None
    private_key = tmp_path / name
    completed = subprocess.run(
        [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert completed.returncode == 0
    private_key.chmod(0o600)
    public = private_key.with_suffix(".pub").read_text(encoding="utf-8").strip()
    return private_key, public


def make_ssh_authenticator(
    registry: ModuleType,
    tmp_path: Path,
    *,
    node_id: str,
    key_id: str,
    role: str,
):
    private_key, public_key = make_ssh_identity(tmp_path, f"{node_id}-{key_id}")
    owners = tmp_path / "owners"
    registrars = tmp_path / "registrars"
    owners.mkdir(exist_ok=True)
    registrars.mkdir(exist_ok=True)
    trust_directory = owners if role == "owner" else registrars
    (trust_directory / f"{node_id}--{key_id}.pub").write_text(
        public_key + "\n", encoding="utf-8"
    )
    signer = registry.OpenSSHSigner(
        private_key,
        node_id=node_id,
        key_id=key_id,
        ssh_keygen=Path(shutil.which("ssh-keygen") or "/usr/bin/ssh-keygen"),
    )
    authenticator = registry.OpenSSHRequestAuthenticator(
        signer,
        registry.OpenSSHTrustStore(owners, registrars),
        cluster_id="kolibri",
    )
    return authenticator, private_key, public_key


def owner_enrollment_payload(
    *,
    node_id: str,
    identity_key_id: str,
    identity_public_key: str,
    wireguard_seed: int,
    mesh_ip: str,
    endpoint: str,
) -> dict:
    return {
        "operation": "enroll",
        "peer": {
            **peer(node_id, wireguard_seed, mesh_ip, endpoint),
            "identity_keys": {identity_key_id: identity_public_key},
        },
        "generation": 1,
        "revision": 1,
        "enrollment_nonce": "test-enrollment-nonce-000000000001",
        "expires_at": int(time.time()) + 300,
    }


def make_config(registry: ModuleType, tmp_path: Path, node_id: str, **overrides):
    values = {
        "state_path": tmp_path / node_id / "peers.json",
        "peer_dir": tmp_path / node_id / "peer-fragments",
        "applied_state": tmp_path / node_id / "applied-keys",
        "trust_file": tmp_path / "cluster.key",
        "apply_helper": tmp_path / "mesh-apply",
        "interface": "wg-test",
        "bind": "10.99.0.1" if node_id == "registrar-a" else "10.99.0.2",
        "port": 9291,
        "node_id": node_id,
        "cluster_id": "kolibri",
        "seeds": (),
        "allocation_cidrs": ("10.99.0.0/29",),
        "allocation_scan_limit": 4096,
        "http_max_workers": 8,
        "http_request_timeout": 2.0,
        "discovery_interval": 2.0,
        "discovery_timeout": 1.0,
        "discovery_max_targets": 64,
        "discovery_workers": 2,
        "backoff_max": 30.0,
    }
    values.update(overrides)
    return registry.RegistryConfig(**values)


def engine_for(registry: ModuleType, config):
    return registry.RegistryEngine(config, apply_runner=lambda: None)


def peer(node_id: str, seed: int, mesh_ip: str, endpoint: str = "198.51.100.10:51820"):
    return {
        "node_id": node_id,
        "public_key": public_key(seed),
        "mesh_ip": mesh_ip,
        "endpoint": endpoint,
    }


def test_legacy_manifest_is_migrated_without_a_static_inventory(registry, tmp_path):
    config = make_config(registry, tmp_path, "registrar-a")
    config.state_path.parent.mkdir(parents=True)
    config.state_path.write_text(
        json.dumps(
            {
                "peers": {
                    "10.99.0.1": peer("home", 1, "10.99.0.1"),
                    "10.99.0.21": peer("agent-21", 21, "10.99.0.21"),
                }
            }
        ),
        encoding="utf-8",
    )
    mesh = engine_for(registry, config)

    loaded = mesh.snapshot()

    assert loaded["schema_version"] == registry.SCHEMA_VERSION == 3
    assert loaded["cluster_id"] == "kolibri"
    assert set(loaded["records"]) == {"home", "agent-21"}
    assert all(record["legacy"] is True for record in loaded["records"].values())
    assert set(loaded["peers"]) == {"10.99.0.1", "10.99.0.21"}
    assert "10.99.0.22" not in loaded["peers"]


def test_upsert_is_atomic_private_and_idempotent(registry, tmp_path):
    config = make_config(registry, tmp_path, "registrar-a")
    mesh = engine_for(registry, config)

    first = mesh.upsert(peer("home", 1, "10.99.0.1"))
    second = mesh.upsert(peer("home", 1, "10.99.0.1"))

    assert first.changed is True
    assert second.changed is False
    assert second.manifest["epoch"] == first.manifest["epoch"] == 1
    assert stat.S_IMODE(config.state_path.stat().st_mode) == 0o600
    fragment = config.peer_dir / "10.99.0.1.conf"
    assert stat.S_IMODE(fragment.stat().st_mode) == 0o600
    assert "AllowedIPs = 10.99.0.1/32" in fragment.read_text(encoding="utf-8")


def test_tombstone_wins_over_a_stale_live_record_and_removes_fragment(
    registry, tmp_path
):
    config = make_config(registry, tmp_path, "registrar-a")
    mesh = engine_for(registry, config)
    mesh.upsert(peer("agent-03", 3, "10.99.0.3"))
    stale = mesh.snapshot()

    removed = mesh.remove("agent-03")
    replay = mesh.merge(stale)

    assert removed.peer["tombstone"] is True
    assert replay.manifest["records"]["agent-03"]["tombstone"] is True
    assert "10.99.0.3" not in replay.manifest["peers"]
    assert not (config.peer_dir / "10.99.0.3.conf").exists()


def test_node_address_rotation_removes_the_superseded_fragment(registry, tmp_path):
    config = make_config(registry, tmp_path, "registrar-a")
    mesh = engine_for(registry, config)
    mesh.upsert(peer("agent-03", 3, "10.99.0.3"))

    rotated = mesh.upsert(peer("agent-03", 3, "10.99.0.4"))

    assert rotated.manifest["peers"]["10.99.0.4"]["node_id"] == "agent-03"
    assert not (config.peer_dir / "10.99.0.3.conf").exists()
    assert (config.peer_dir / "10.99.0.4.conf").exists()


def test_recovery_removes_only_marked_orphan_fragments(registry, tmp_path):
    config = make_config(registry, tmp_path, "registrar-a")
    config.peer_dir.mkdir(parents=True)
    managed = config.peer_dir / "10.99.0.3.conf"
    unmanaged = config.peer_dir / "10.99.0.4.conf"
    managed.write_text(
        "# Managed by Kolibri mesh registry\n"
        "[Peer]\n"
        f"PublicKey = {public_key(3)}\n"
        "AllowedIPs = 10.99.0.3/32\n"
        "PersistentKeepalive = 25\n",
        encoding="utf-8",
    )
    unmanaged.write_text(
        "# pre-existing operator fragment\n"
        "[Peer]\n"
        f"PublicKey = {public_key(4)}\n"
        "AllowedIPs = 10.99.0.4/32\n"
        "PersistentKeepalive = 25\n",
        encoding="utf-8",
    )
    managed.chmod(0o600)
    unmanaged.chmod(0o600)

    engine_for(registry, config).recover()

    assert not managed.exists()
    assert unmanaged.exists()


def test_concurrent_identity_conflict_converges_deterministically(registry, tmp_path):
    config_a = make_config(registry, tmp_path, "registrar-a")
    config_b = make_config(registry, tmp_path, "registrar-b")
    mesh_a = engine_for(registry, config_a)
    mesh_b = engine_for(registry, config_b)
    mesh_a.upsert(peer("agent-a", 11, "10.99.0.6"))
    mesh_b.upsert(peer("agent-b", 12, "10.99.0.6"))
    snapshot_a = mesh_a.snapshot()
    snapshot_b = mesh_b.snapshot()

    mesh_a.merge(snapshot_b)
    mesh_b.merge(snapshot_a)
    mesh_a.merge(mesh_b.snapshot())
    mesh_b.merge(mesh_a.snapshot())

    assert registry.manifest_bytes(mesh_a.snapshot()) == registry.manifest_bytes(
        mesh_b.snapshot()
    )
    final = mesh_a.snapshot()
    assert list(final["peers"]) == ["10.99.0.6"]
    assert final["peers"]["10.99.0.6"]["node_id"] == "agent-b"
    assert final["records"]["agent-a"]["tombstone"] is True
    assert final["records"]["agent-a"]["reason"] == "conflict"


def test_duplicate_public_key_converges_to_one_live_peer(registry):
    payload = {
        "schema_version": 2,
        "cluster_id": "kolibri",
        "epoch": 8,
        "records": {
            "agent-a": {
                **peer("agent-a", 7, "10.99.0.7"),
                "epoch": 7,
                "revision": 1,
                "origin": "registrar-a",
                "tombstone": False,
            },
            "agent-b": {
                **peer("agent-b", 7, "10.99.0.8"),
                "epoch": 8,
                "revision": 1,
                "origin": "registrar-b",
                "tombstone": False,
            },
        },
        "peers": {},
    }

    normalized = registry.normalize_manifest(payload, cluster_id="kolibri")

    assert list(normalized["peers"]) == ["10.99.0.8"]
    assert normalized["records"]["agent-a"]["tombstone"] is True


def test_manifest_ignores_untrusted_global_epoch_and_rejects_bad_tombstone(registry):
    malformed = {
        "schema_version": 2,
        "cluster_id": "kolibri",
        "epoch": 2**63 - 1,
        "records": {},
        "peers": {},
    }
    normalized = registry.normalize_manifest(malformed, cluster_id="kolibri")
    assert normalized["epoch"] == 0
    assert normalized["vector"] == {}

    malformed["records"] = {
        "agent-a": {
            **peer("agent-a", 1, "10.99.0.2"),
            "epoch": 1,
            "revision": 1,
            "origin": "registrar-a",
            "tombstone": "false",
        }
    }
    with pytest.raises(registry.RegistryError, match="tombstone_invalid"):
        registry.normalize_manifest(malformed, cluster_id="kolibri")


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("node_id", "../../root", "node_id_invalid"),
        ("public_key", "not-a-wireguard-key", "public_key_invalid"),
        ("mesh_ip", "127.0.0.1", "mesh_ip_invalid"),
        ("endpoint", "host:51820\nInjected = yes", "endpoint_invalid"),
    ],
)
def test_invalid_peer_fields_fail_closed(registry, tmp_path, field, value, code):
    config = make_config(registry, tmp_path, "registrar-a")
    mesh = engine_for(registry, config)
    candidate = peer("agent-04", 4, "10.99.0.4")
    candidate[field] = value

    with pytest.raises(registry.RegistryError, match=code):
        mesh.upsert(candidate)

    assert mesh.snapshot()["peers"] == {}


def test_fragment_symlink_is_never_followed(registry, tmp_path):
    config = make_config(registry, tmp_path, "registrar-a")
    config.peer_dir.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_text("unchanged", encoding="utf-8")
    (config.peer_dir / "10.99.0.4.conf").symlink_to(outside)
    mesh = engine_for(registry, config)

    with pytest.raises(registry.RegistryError, match="symlink_forbidden"):
        mesh.upsert(peer("agent-04", 4, "10.99.0.4"))

    assert outside.read_text(encoding="utf-8") == "unchanged"
    assert mesh.snapshot()["peers"] == {}


def test_state_survives_apply_failure_and_recovery_is_retryable(registry, tmp_path):
    config = make_config(registry, tmp_path, "registrar-a")

    def unavailable():
        raise registry.ApplyPending()

    failing = registry.RegistryEngine(config, apply_runner=unavailable)
    result = failing.upsert(peer("agent-05", 5, "10.99.0.5"))
    degraded = failing.health()
    recovered = engine_for(registry, config).recover()

    assert result.apply_pending is True
    assert degraded["status"] == "degraded"
    assert degraded["apply_pending"] is True
    assert config.state_path.exists()
    assert recovered.apply_pending is False
    assert recovered.manifest["peers"]["10.99.0.5"]["node_id"] == "agent-05"


def test_unchanged_gossip_does_not_reapply_wireguard_for_every_peer(registry, tmp_path):
    config = make_config(registry, tmp_path, "registrar-a")
    applies = 0

    def applied():
        nonlocal applies
        applies += 1

    mesh = registry.RegistryEngine(config, apply_runner=applied)
    mesh.recover()
    mesh.upsert(peer("agent-05", 5, "10.99.0.5"))
    snapshot = mesh.snapshot()

    mesh.merge(snapshot)
    mesh.merge(snapshot)

    assert applies == 2


def test_malformed_existing_state_is_not_silently_replaced(registry, tmp_path):
    config = make_config(registry, tmp_path, "registrar-a")
    config.state_path.parent.mkdir(parents=True)
    config.state_path.write_text("{not-json", encoding="utf-8")
    mesh = engine_for(registry, config)

    with pytest.raises(registry.RegistryError, match="manifest_unreadable"):
        mesh.snapshot()

    assert config.state_path.read_text(encoding="utf-8") == "{not-json"


def test_cluster_trust_requires_private_regular_file(registry, tmp_path):
    secret = tmp_path / "cluster.key"
    secret.write_bytes(b"x" * 32)
    secret.chmod(0o644)

    with pytest.raises(registry.RegistryError, match="permissions_invalid"):
        registry.read_cluster_secret(secret)

    secret.chmod(0o600)
    assert registry.read_cluster_secret(secret) == b"x" * 32
    link = tmp_path / "cluster-link"
    link.symlink_to(secret)
    with pytest.raises(registry.RegistryError, match="symlink_forbidden"):
        registry.read_cluster_secret(link)


def test_hmac_replay_and_wrong_cluster_are_rejected(registry):
    def now():
        return 2_000_000_000.0

    sender = registry.RequestAuthenticator(
        b"s" * 32,
        cluster_id="kolibri",
        node_id="registrar-a",
        clock=now,
    )
    receiver = registry.RequestAuthenticator(
        b"s" * 32,
        cluster_id="kolibri",
        node_id="registrar-b",
        clock=now,
    )
    body = b'{"operation":"remove","node_id":"agent-07"}'
    headers = sender.headers("POST", "/v1/mesh/peers", body)

    assert receiver.verify("POST", "/v1/mesh/peers", body, headers) == "registrar-a"
    with pytest.raises(registry.RegistryError, match="authentication_failed"):
        receiver.verify("POST", "/v1/mesh/peers", body, headers)
    wrong = dict(sender.headers("POST", "/v1/mesh/peers", body))
    wrong["X-Kolibri-Cluster"] = "other"
    with pytest.raises(registry.RegistryError, match="authentication_failed"):
        receiver.verify("POST", "/v1/mesh/peers", body, wrong)
    spoofed = dict(sender.headers("POST", "/v1/mesh/peers", body))
    spoofed["X-Kolibri-Node"] = "registrar-b"
    spoofed["X-Kolibri-Key-Id"] = "registrar-b-key"
    with pytest.raises(registry.RegistryError, match="authentication_failed"):
        receiver.verify("POST", "/v1/mesh/peers", body, spoofed)


def test_ed25519_signature_binds_node_key_id_and_body(registry, tmp_path):
    ssh_keygen = Path(shutil.which("ssh-keygen") or "")
    private_key, public = make_ssh_identity(tmp_path, "registrar-a-key")
    owners = tmp_path / "owners"
    registrars = tmp_path / "registrars"
    owners.mkdir()
    registrars.mkdir()
    (registrars / "registrar-a--key-a.pub").write_text(public + "\n", encoding="utf-8")
    signer = registry.OpenSSHSigner(
        private_key,
        node_id="registrar-a",
        key_id="key-a",
        ssh_keygen=ssh_keygen,
    )
    authenticator = registry.OpenSSHRequestAuthenticator(
        signer,
        registry.OpenSSHTrustStore(owners, registrars),
        cluster_id="kolibri",
    )
    body = b'{"operation":"upsert"}'
    headers = authenticator.headers("POST", "/v1/mesh/peers", body)

    context = authenticator.verify("POST", "/v1/mesh/peers", body, headers)

    assert context.node_id == "registrar-a"
    assert context.key_id == "key-a"
    assert context.role == "registrar"
    for header, replacement in (
        ("X-Kolibri-Node", "registrar-b"),
        ("X-Kolibri-Key-Id", "key-b"),
    ):
        tampered = dict(authenticator.headers("POST", "/v1/mesh/peers", body))
        tampered[header] = replacement
        with pytest.raises(registry.RegistryError):
            authenticator.verify("POST", "/v1/mesh/peers", body, tampered)
    fresh = authenticator.headers("POST", "/v1/mesh/peers", body)
    with pytest.raises(registry.RegistryError, match="authentication_failed"):
        authenticator.verify("POST", "/v1/mesh/peers", body + b" ", fresh)


def test_ed25519_rotation_accepts_overlap_then_retires_old_key(registry, tmp_path):
    ssh_keygen = Path(shutil.which("ssh-keygen") or "")
    old_private, old_public = make_ssh_identity(tmp_path, "old")
    new_private, new_public = make_ssh_identity(tmp_path, "new")
    owners = tmp_path / "owners"
    registrars = tmp_path / "registrars"
    owners.mkdir()
    registrars.mkdir()
    old_trust = registrars / "registrar-a--old-key.pub"
    new_trust = registrars / "registrar-a--new-key.pub"
    old_trust.write_text(old_public + "\n", encoding="utf-8")
    new_trust.write_text(new_public + "\n", encoding="utf-8")
    trust = registry.OpenSSHTrustStore(owners, registrars)
    old_auth = registry.OpenSSHRequestAuthenticator(
        registry.OpenSSHSigner(
            old_private,
            node_id="registrar-a",
            key_id="old-key",
            ssh_keygen=ssh_keygen,
        ),
        trust,
        cluster_id="kolibri",
    )
    new_auth = registry.OpenSSHRequestAuthenticator(
        registry.OpenSSHSigner(
            new_private,
            node_id="registrar-a",
            key_id="new-key",
            ssh_keygen=ssh_keygen,
        ),
        trust,
        cluster_id="kolibri",
    )
    body = b"{}"

    old_headers = old_auth.headers("POST", "/v1/mesh/sync", body)
    new_headers = new_auth.headers("POST", "/v1/mesh/sync", body)
    assert (
        old_auth.verify("POST", "/v1/mesh/sync", body, old_headers).key_id == "old-key"
    )
    assert (
        old_auth.verify("POST", "/v1/mesh/sync", body, new_headers).key_id == "new-key"
    )

    old_trust.unlink()
    retired_headers = old_auth.headers("POST", "/v1/mesh/sync", body)
    with pytest.raises(registry.RegistryError, match="signer_unknown"):
        old_auth.verify("POST", "/v1/mesh/sync", body, retired_headers)
    still_valid = new_auth.headers("POST", "/v1/mesh/sync", body)
    assert (
        new_auth.verify("POST", "/v1/mesh/sync", body, still_valid).key_id == "new-key"
    )


def test_http_post_requires_authentication_and_never_echoes_secret(registry, tmp_path):
    config = make_config(registry, tmp_path, "registrar-a", bind="10.99.0.1")
    authenticator, owner_private_key, _owner_public_key = make_ssh_authenticator(
        registry,
        tmp_path,
        node_id="owner",
        key_id="owner-key",
        role="owner",
    )
    _agent_private_key, agent_public_key = make_ssh_identity(tmp_path, "agent-06-key")
    engine = registry.RegistryEngine(
        config,
        apply_runner=lambda: None,
        record_authorizer=registry.RecordAuthorizer(authenticator),
    )
    server = registry.RegistryHTTPServer(("127.0.0.1", 0), engine, authenticator)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    body = json.dumps(
        owner_enrollment_payload(
            node_id="agent-06",
            identity_key_id="agent-key",
            identity_public_key=agent_public_key,
            wireguard_seed=6,
            mesh_ip="10.99.0.6",
            endpoint="203.0.113.6:51820",
        )
    ).encode()
    private_material = owner_private_key.read_bytes()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.request(
            "POST", "/v1/mesh/enroll", body, {"Content-Type": "application/json"}
        )
        response = connection.getresponse()
        error_payload = response.read()
        assert response.status == 401
        assert b"authentication_failed" in error_payload
        assert private_material not in error_payload

        headers = authenticator.headers("POST", "/v1/mesh/enroll", body)
        headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.request("POST", "/v1/mesh/enroll", body, headers)
        response = connection.getresponse()
        response_payload = response.read()
        payload = json.loads(response_payload)
        assert response.status == 200
        assert payload["changed"] is True
        assert private_material not in response_payload

        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.request("GET", "/v1/mesh/peers")
        response = connection.getresponse()
        assert response.status == 200
        assert (
            json.loads(response.read())["peers"]["10.99.0.6"]["node_id"] == "agent-06"
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_enroll_client_does_not_report_success_while_apply_is_pending(
    registry, tmp_path, monkeypatch
):
    config = make_config(registry, tmp_path, "registrar-a")
    owner_authenticator, _owner_private_key, _owner_public_key = make_ssh_authenticator(
        registry,
        tmp_path,
        node_id="owner",
        key_id="owner-key",
        role="owner",
    )
    authenticator, _node_private_key, node_public_key = make_ssh_authenticator(
        registry,
        tmp_path,
        node_id="agent-06",
        key_id="agent-key",
        role="registrar",
    )
    engine = registry.RegistryEngine(
        config,
        apply_runner=lambda: None,
        record_authorizer=registry.RecordAuthorizer(owner_authenticator),
    )
    enrollment = owner_enrollment_payload(
        node_id="agent-06",
        identity_key_id="agent-key",
        identity_public_key=node_public_key,
        wireguard_seed=6,
        mesh_ip="10.99.0.6",
        endpoint="203.0.113.6:51820",
    )
    enrollment_body = json.dumps(enrollment).encode()
    owner_context = owner_authenticator.verify(
        "POST",
        "/v1/mesh/enroll",
        enrollment_body,
        owner_authenticator.headers("POST", "/v1/mesh/enroll", enrollment_body),
    )
    enrolled = engine.enroll_owner(
        enrollment["peer"],
        authority=owner_context,
        generation=enrollment["generation"],
        revision=enrollment["revision"],
        enrollment_nonce=enrollment["enrollment_nonce"],
        expires_at=enrollment["expires_at"],
    )
    calls: list[tuple[str, str]] = []

    def fake_signed_request(_authenticator, method, url, **_kwargs):
        calls.append((method, url))
        if method == "GET":
            return enrolled.manifest
        return {"status": "accepted", "apply_pending": True}

    monkeypatch.setattr(registry, "signed_request", fake_signed_request)
    args = SimpleNamespace(
        client_action="enroll",
        node_id="agent-06",
        public_key=public_key(6),
        mesh_ip="10.99.0.6",
        endpoint="203.0.113.6:51820",
    )

    with pytest.raises(registry.RegistryError, match="wireguard_apply_pending"):
        registry._run_client(args, config, authenticator)
    assert [method for method, _url in calls] == ["GET", "POST"]
    assert calls[-1][1].endswith("/v1/mesh/peers")


def test_authenticated_sync_rejects_cross_cluster_manifest(registry, tmp_path):
    config = make_config(registry, tmp_path, "registrar-a")
    mesh = engine_for(registry, config)
    foreign = registry.empty_manifest("other")

    with pytest.raises(registry.RegistryError, match="cluster_or_schema_mismatch"):
        mesh.merge(foreign)


def test_authenticated_sync_rejects_address_outside_discovered_pool(registry, tmp_path):
    config = make_config(registry, tmp_path, "registrar-a")
    mesh = engine_for(registry, config)
    remote = registry.normalize_manifest(
        {
            "schema_version": 2,
            "cluster_id": "kolibri",
            "epoch": 1,
            "records": {
                "foreign-node": {
                    **peer("foreign-node", 8, "10.100.0.8"),
                    "epoch": 1,
                    "revision": 1,
                    "origin": "registrar-b",
                    "tombstone": False,
                }
            },
            "peers": {},
        },
        cluster_id="kolibri",
    )

    with pytest.raises(registry.RegistryError, match="outside_address_pool"):
        mesh.merge(remote)


def test_legacy_remote_is_accepted_only_on_explicit_migration_pull(registry, tmp_path):
    config = make_config(registry, tmp_path, "registrar-a")
    mesh = engine_for(registry, config)
    legacy = {"peers": {"10.99.0.7": peer("agent-07", 7, "10.99.0.7")}}

    with pytest.raises(registry.RegistryError, match="cluster_or_schema_mismatch"):
        mesh.merge(legacy)
    migrated = mesh.merge(legacy, allow_legacy_remote=True)

    assert migrated.manifest["peers"]["10.99.0.7"]["node_id"] == "agent-07"


def test_discovery_is_membership_driven_bounded_and_backed_off(registry, tmp_path):
    config = make_config(
        registry,
        tmp_path,
        "registrar-a",
        seeds=("10.99.0.9:9291",),
        discovery_max_targets=2,
        discovery_interval=2.0,
    )
    mesh = engine_for(registry, config)
    mesh.upsert(peer("registrar-b", 2, "10.99.0.2"))
    mesh.upsert(peer("registrar-c", 3, "10.99.0.3"))
    auth = registry.RequestAuthenticator(
        b"s" * 32, cluster_id="kolibri", node_id="registrar-a"
    )
    loop = registry.DiscoveryLoop(
        config,
        mesh,
        auth,
        clock=lambda: 100.0,
        jitter=lambda low, _high: low,
    )
    calls: list[str] = []

    def fail(target):
        calls.append(target)
        raise registry.RegistryError("offline")

    loop._exchange = fail
    targets = loop.targets()
    first = loop.run_once()
    second = loop.run_once()

    assert len(targets) == 2
    assert all(target.endswith(":9291") for target in targets)
    assert "http://10.99.0.254:9291" not in targets
    assert first == second == 0
    assert len(calls) == len(targets)
    assert all(state.retry_at <= 130.0 for state in loop.backoff.values())


def test_allocator_uses_discovered_network_not_hardcoded_fleet_slots(
    registry, tmp_path
):
    config = make_config(registry, tmp_path, "registrar-a", bind="10.99.0.1")
    mesh = engine_for(registry, config)
    mesh.upsert(peer("home", 1, "10.99.0.1"))

    assert mesh.allocate() == "10.99.0.2"
    enrolled = mesh.enroll_auto(
        {
            "node_id": "new-node",
            "public_key": public_key(9),
            "endpoint": "203.0.113.9:51820",
        }
    )
    assert enrolled.peer["mesh_ip"] == "10.99.0.2"


def test_apply_reconciles_only_previously_tracked_keys(registry, tmp_path):
    config = make_config(registry, tmp_path, "registrar-a")
    fragments = registry.PeerFragments(config.peer_dir)
    manifest = registry.normalize_manifest(
        {
            "schema_version": 2,
            "cluster_id": "kolibri",
            "epoch": 1,
            "records": {
                "agent-02": {
                    **peer("agent-02", 2, "10.99.0.2"),
                    "epoch": 1,
                    "revision": 1,
                    "origin": "registrar-a",
                    "tombstone": False,
                }
            },
            "peers": {},
        },
        cluster_id="kolibri",
    )
    fragments.reconcile(manifest)
    legacy_fragment = config.peer_dir / "10.99.0.2.conf"
    legacy_fragment.chmod(0o644)
    config.applied_state.parent.mkdir(parents=True, exist_ok=True)
    config.applied_state.write_text(public_key(1) + "\n", encoding="utf-8")
    config.applied_state.chmod(0o600)
    commands: list[list[str]] = []

    class Completed:
        returncode = 0

    def runner(command, **_kwargs):
        commands.append(command)
        return Completed()

    registry.apply_fragments(config, runner=runner)

    assert any(
        command[-1] == "remove" and public_key(1) in command for command in commands
    )
    assert any(
        public_key(2) in command and "allowed-ips" in command for command in commands
    )
    assert stat.S_IMODE(legacy_fragment.stat().st_mode) == 0o600
    assert stat.S_IMODE(config.applied_state.stat().st_mode) == 0o600


def test_apply_rejects_unknown_fragment_directives_before_running_wg(
    registry, tmp_path
):
    config = make_config(registry, tmp_path, "registrar-a")
    config.peer_dir.mkdir(parents=True)
    fragment = config.peer_dir / "10.99.0.2.conf"
    fragment.write_text(
        "# Managed by Kolibri mesh registry\n"
        "[Peer]\n"
        f"PublicKey = {public_key(2)}\n"
        "AllowedIPs = 10.99.0.2/32\n"
        "PostUp = touch /tmp/forbidden\n",
        encoding="utf-8",
    )
    fragment.chmod(0o600)
    commands: list[list[str]] = []

    def runner(command, **_kwargs):
        commands.append(command)
        raise AssertionError("wg must not run")

    with pytest.raises(registry.RegistryError, match="directive_invalid"):
        registry.apply_fragments(config, runner=runner)

    assert commands == []


def test_wrappers_and_unit_enforce_single_authenticated_implementation():
    enroll = (ROOT / "ops" / "mesh-enroll").read_text(encoding="utf-8")
    apply = (ROOT / "ops" / "mesh-apply-peers").read_text(encoding="utf-8")
    unit = (ROOT / "ops" / "systemd" / "kolibri-mesh-registry.service").read_text(
        encoding="utf-8"
    )

    assert '"$REGISTRY_IMPL" client' in enroll
    assert '"$REGISTRY_IMPL" apply' in apply
    assert "LoadCredential=mesh-identity:" in unit
    assert "KOLIBRI_MESH_IDENTITY_FILE=%d/mesh-identity" in unit
    assert "KOLIBRI_MESH_OWNER_TRUST_DIR=/etc/kolibri/mesh-trust/owners" in unit
    assert "KOLIBRI_MESH_REGISTRAR_TRUST_DIR=/etc/kolibri/mesh-trust/registrars" in unit
    assert "mesh-registry-hmac" not in unit
    assert "ProtectSystem=strict" in unit
    assert "10.99.0." not in enroll
    assert "StrictHostKeyChecking=no" not in enroll + apply + unit
    assert stat.S_IMODE((ROOT / "ops" / "mesh-enroll").stat().st_mode) & stat.S_IXUSR
    assert (
        stat.S_IMODE((ROOT / "ops" / "mesh-apply-peers").stat().st_mode) & stat.S_IXUSR
    )
    source = (ROOT / "ops" / "mesh_registry.py").read_text(encoding="utf-8")
    assert "range(1, 255)" not in source
    assert "SUBNET_PREFIX" not in source
