from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_provisioning_installs_and_enables_persistent_peer_apply_unit():
    provision = (ROOT / "scripts" / "provision-server.sh").read_text(encoding="utf-8")
    rollout = (ROOT / "scripts" / "rollout-home-only-bootstrap.sh").read_text(
        encoding="utf-8"
    )

    for source in (provision, rollout):
        assert "ops/systemd/kolibri-mesh-apply-peers.service" in source
        assert "systemctl enable --now kolibri-mesh-apply-peers.service" in source


def test_fleet_check_treats_home_self_as_local_management_cell():
    check = (ROOT / "scripts" / "check-fleet.sh").read_text(encoding="utf-8")

    assert 'if [ "$node_id" = home ]; then' in check
    assert '"$HOME_TARGET" true' in check
