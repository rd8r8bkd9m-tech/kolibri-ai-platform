from pathlib import Path

from ops.release_installer import load_release_policy


ROOT = Path(__file__).resolve().parents[1]


def test_home_release_policy_is_strict_and_backend_only():
    policy = load_release_policy(ROOT / "ops" / "release-policy.home.json")

    assert policy.services == frozenset({"kolibri-backend.service"})
    assert policy.default_services == ("kolibri-backend.service",)
    assert [check.name for check in policy.pre_health] == ["pre:backend-baseline"]
    assert [check.name for check in policy.post_health] == ["post:backend-activated"]
    for check in (*policy.pre_health, *policy.post_health):
        assert check.argv[0] == "/usr/bin/curl"
        assert check.argv[-1] == "http://127.0.0.1:8001/api/health"
        assert "sh" not in Path(check.argv[0]).name
