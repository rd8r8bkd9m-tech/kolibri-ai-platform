from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_home_control_plane_bootstrap_is_dynamic_reversible_and_dry_run_by_default():
    source = (ROOT / "scripts" / "bootstrap-home-control-plane.sh").read_text(
        encoding="utf-8"
    )

    assert 'select(.node_id == "home")' in source
    assert "10.99.0.1" not in source
    assert '"main"' not in source
    assert '"primary"' not in source
    assert "APPLY=false" in source
    assert 'if [ "$APPLY" != true ]' in source
    assert "active fenced tasks" in source
    assert "checksums.before" in source
    assert "rollback()" in source
    assert "scope=active" in source
    assert 'membership.authority == "replicated_mesh_manifest"' in source


def test_home_control_plane_bootstrap_installs_all_runtime_dependencies():
    source = (ROOT / "scripts" / "bootstrap-home-control-plane.sh").read_text(
        encoding="utf-8"
    )

    for name in (
        "factory_control.py",
        "fleet_membership.py",
        "release_authority.py",
        "telegram_superfactory.py",
    ):
        assert name in source
