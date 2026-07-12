import json
import shutil
from pathlib import Path

import pytest

from ops import home_control_plane_strict_compat_bootstrap as module


ROOT = Path(__file__).resolve().parents[1]
COMMIT = "b" * 40


def _fixture(tmp_path: Path, *, current: bytes = b"print('legacy')\n"):
    source = tmp_path / "source"
    fake_root = tmp_path / "root"
    (source / "ops").mkdir(parents=True)
    (fake_root / "var/backups").mkdir(parents=True)
    for relative in [module.TARGET_SOURCE, *module.ANCHORS, *module.CONTRACT_SOURCES]:
        source_path = ROOT / relative
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)

    for relative, logical in module.ANCHORS.items():
        destination = module._rooted(fake_root, logical)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, destination)
    target = module._rooted(fake_root, module.TARGET)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(current)
    target.chmod(0o755)

    manifest = tmp_path / "peers.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "epoch": 9,
                "cluster_id": "test",
                "peers": {
                    "home": {"node_id": "home", "mesh_ip": "10.99.0.1"},
                    "worker": {"node_id": "worker", "mesh_ip": "10.99.0.2"},
                },
            }
        ),
        encoding="utf-8",
    )
    bootstrap = module.StrictCompatBootstrap(
        source_root=source,
        manifest_path=manifest,
        source_commit=COMMIT,
        run_id="unit-test",
        root=fake_root,
        local_addresses=["10.99.0.1"],
    )
    service = module.ServiceState("loaded", "active", "running", 0)
    bootstrap._launcher_selection = lambda: {
        "authority": "home",
        "source": "legacy-split-bootstrap",
        "release_id": "legacy-bootstrap",
    }
    bootstrap._service_state = lambda: service
    bootstrap._baseline = lambda: {
        "state_namespace": "kolibri_factory",
        "redis_projection": {
            "task_total": 6,
            "queue_total": 0,
            "lease_index_total": 0,
        },
    }
    return bootstrap, source, fake_root, target


def test_plan_is_dry_run_and_binds_exact_one_file(tmp_path):
    bootstrap, source, _, target = _fixture(tmp_path)
    before = target.read_bytes()

    plan = bootstrap.build_plan()

    assert plan["status"] == "planned"
    assert plan["mode"] == "dry-run"
    assert plan["target_node"] == "home"
    assert plan["changed_paths"] == [module.TARGET]
    assert plan["restart_units"] == [module.SERVICE]
    assert plan["binding"]["target"]["after_sha256"] == module._sha256(
        (source / module.TARGET_SOURCE).read_bytes()
    )
    assert plan["plan_digest"] == module.plan_digest(plan["binding"])
    assert plan["contract_freeze"]["status"] == "candidate"
    assert plan["binding"]["contract_freeze_digest"] == plan["contract_freeze"][
        "digest"
    ]
    assert target.read_bytes() == before


def test_agent_runner_contract_change_invalidates_freeze_and_plan(tmp_path):
    bootstrap, source, _, _ = _fixture(tmp_path)
    original = bootstrap.build_plan()
    agent_host = source / "ops/agent_host.py"
    agent_host.write_text(
        agent_host.read_text(encoding="utf-8") + "\n# contract revision\n",
        encoding="utf-8",
    )

    revised = bootstrap.build_plan()

    assert revised["contract_freeze"]["digest"] != original["contract_freeze"][
        "digest"
    ]
    assert revised["plan_digest"] != original["plan_digest"]


def test_apply_requires_exact_plan_digest_and_is_idempotent(tmp_path):
    bootstrap, source, _, target = _fixture(tmp_path)
    plan = bootstrap.build_plan()
    bootstrap._candidate = lambda candidate_plan: {
        "health": "strict",
        "membership_digest": candidate_plan["membership_digest"],
        "redis_projection": candidate_plan["redis_before"],
    }
    bootstrap._restart = lambda: None
    bootstrap._strict_contracts = lambda *args, **kwargs: {
        "health": "strict",
        "membership_digest": plan["membership_digest"],
        "redis_projection": plan["redis_before"],
    }

    with pytest.raises(module.BootstrapError, match="strict_compat_plan_digest_mismatch"):
        bootstrap.apply(
            "sha256:" + "0" * 64,
            plan["contract_freeze"]["digest"],
        )

    with pytest.raises(
        module.BootstrapError,
        match="strict_compat_contract_freeze_digest_mismatch",
    ):
        bootstrap.apply(plan["plan_digest"], "sha256:" + "0" * 64)

    result = bootstrap.apply(
        plan["plan_digest"], plan["contract_freeze"]["digest"]
    )
    assert result["status"] == "applied"
    assert result["changed_paths"] == [module.TARGET]
    assert target.read_bytes() == (source / module.TARGET_SOURCE).read_bytes()

    next_plan = bootstrap.build_plan()
    repeated = bootstrap.apply(
        next_plan["plan_digest"], next_plan["contract_freeze"]["digest"]
    )
    assert repeated["status"] == "already_applied"
    assert repeated["restart_units"] == []


def test_failed_post_gate_restores_exact_previous_runtime(tmp_path, monkeypatch):
    bootstrap, _, _, target = _fixture(tmp_path)
    previous = target.read_bytes()
    plan = bootstrap.build_plan()
    bootstrap._candidate = lambda candidate_plan: {
        "health": "strict",
        "membership_digest": candidate_plan["membership_digest"],
        "redis_projection": candidate_plan["redis_before"],
    }
    restart_calls = []
    bootstrap._restart = lambda: restart_calls.append(module.SERVICE)

    def fail_post(*args, **kwargs):
        raise module.BootstrapError("strict_compat_post_health_failed")

    bootstrap._strict_contracts = fail_post
    clock = iter((0.0, 21.0))
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))

    with pytest.raises(module.BootstrapError) as captured:
        bootstrap.apply(
            plan["plan_digest"], plan["contract_freeze"]["digest"]
        )
    assert captured.value.code == "strict_compat_post_health_failed"
    assert captured.value.rollback == "completed"
    assert target.read_bytes() == previous
    assert restart_calls == [module.SERVICE, module.SERVICE]


def test_scope_has_no_backend_frontend_mesh_or_credential_mutation():
    source = (ROOT / "ops/home_control_plane_strict_compat_bootstrap.py").read_text(
        encoding="utf-8"
    )
    assert module.TARGET == "/usr/local/bin/kolibri-factory-control"
    assert "systemctl\", \"restart\", SERVICE" in source
    assert "kolibri-backend.service" not in source
    assert "telegram.env" not in source
    assert "private_key" not in source
    assert "ssh " not in source.lower()


def test_baseline_uses_explicit_legacy_namespace_and_never_guesses(
    tmp_path, monkeypatch
):
    bootstrap, _, _, _ = _fixture(tmp_path)
    del bootstrap._baseline
    responses = {
        "/v1/health": {
            "status": "completed",
            "node": "home",
            "data": {"redis": "PONG"},
        },
        "/v1/tasks/queue/diagnostics": {
            "redis": "PONG",
            "task_total": 1,
            "queue_total": 0,
            "lease_index_total": 0,
            "expired_leases": 0,
            "stuck_heartbeat_tasks": 0,
        },
    }
    monkeypatch.setattr(module, "_http_json", lambda _base, path: responses[path])
    monkeypatch.delenv("FACTORY_NAMESPACE", raising=False)
    with pytest.raises(module.BootstrapError, match="strict_compat_state_namespace_unavailable"):
        bootstrap._baseline()

    monkeypatch.setenv("FACTORY_NAMESPACE", "kolibri_factory_mvp")
    assert bootstrap._baseline()["state_namespace"] == "kolibri_factory_mvp"
