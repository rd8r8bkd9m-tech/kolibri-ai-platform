from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_watchdog_rollout_derives_home_and_forbids_agent_forwarding():
    source = (ROOT / "scripts" / "rollout-home-only-watchdogs.sh").read_text(
        encoding="utf-8"
    )

    assert 'HOME_TARGET=""' in source
    assert 'select(.node_id == "home")' in source
    assert 'HOME_TARGET="root@$HOME_IP"' in source
    assert "192.168.88.210" not in source
    assert "ssh -A" not in source
    assert "ProxyJump=home" not in source
    assert 'ProxyJump="$HOME_TARGET"' in source
