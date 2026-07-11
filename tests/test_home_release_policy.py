from pathlib import Path

from ops.release_installer import load_release_policy


ROOT = Path(__file__).resolve().parents[1]


def test_home_release_policy_is_strict_unified_home_runtime():
    policy = load_release_policy(ROOT / "ops" / "release-policy.home.json")

    assert policy.services == frozenset({
        "kolibri-backend.service",
        "kolibri-factory-control.service",
    })
    assert policy.default_services == (
        "kolibri-factory-control.service",
        "kolibri-backend.service",
    )
    assert "ops/factory_control.py" in policy.required_payload_paths
    assert "ops/agent_host.py" in policy.required_payload_paths
    assert "ops/release_helper.py" in policy.required_payload_paths
    assert "ops/release_installer.py" in policy.required_payload_paths
    assert "ops/runner_access.py" in policy.required_payload_paths
    assert "ops/immutable_release_preflight.py" in policy.required_payload_paths
    assert "ops/mimo/kolibri-response-only.md" in policy.required_payload_paths
    assert "frontend/dist/index.html" in policy.required_payload_paths
    assert [check.name for check in policy.pre_health] == [
        "pre:immutable-current-exact-file-set",
        "pre:backend-baseline",
        "pre:control-plane-baseline",
    ]
    assert [check.name for check in policy.pre_activate] == [
        "candidate:control-plane-side-by-side",
    ]
    assert [check.name for check in policy.post_health] == [
        "post:backend-activated",
        "post:control-plane-activated",
    ]
    for check in (*policy.pre_health, *policy.pre_activate, *policy.post_health):
        assert check.argv[0] in {"/usr/bin/curl", "/usr/bin/python3"}
        assert "sh" not in Path(check.argv[0]).name
    assert "{release_dir}" in policy.pre_activate[0].argv
    assert "{release_dir}" in policy.post_health[1].argv
    assert "{release_kind}" in policy.pre_activate[0].argv
    assert "{release_kind}" in policy.post_health[1].argv
    assert "--allow-legacy-baseline" in policy.pre_health[2].argv
    assert "--allow-legacy-baseline" not in policy.pre_activate[0].argv
    assert "--allow-legacy-baseline" not in policy.post_health[1].argv
