from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_helper_uses_a_root_owned_dedicated_artifact_boundary():
    unit = (ROOT / "ops" / "systemd" / "kolibri-release-helper.service").read_text(
        encoding="utf-8"
    )

    assert "KOLIBRI_ARTIFACT_ROOT=/var/lib/kolibri-release/artifacts" in unit
    assert "/var/lib/kolibri-release/artifacts" in unit
    assert "KOLIBRI_ARTIFACT_ROOT=/var/lib/kolibri-agent/artifacts" not in unit
    assert "ReadWritePaths=/opt/kolibri-ai /var/lib/kolibri-release/artifacts" in unit
