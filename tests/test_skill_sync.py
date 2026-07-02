import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_skill_sync():
    spec = importlib.util.spec_from_file_location("skill_sync", ROOT / "ops" / "skill_sync.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_skill(root, name="alpha", version="1.0.0", body="initial"):
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "skill.json").write_text(
        json.dumps({"name": name, "version": version, "description": "test skill"}),
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    return skill_dir


def test_build_registry_and_install_writes_artifact_proof(tmp_path):
    sync = load_skill_sync()
    source_root = tmp_path / "source"
    write_skill(source_root)
    registry_path = tmp_path / "registry.json"
    proof_path = tmp_path / "proof.json"

    assert sync.main(["build-registry", "--source-root", str(source_root), "--output", str(registry_path)]) == 0
    assert sync.main([
        "install",
        "--registry",
        str(registry_path),
        "--skill",
        "alpha",
        "--install-root",
        str(tmp_path / "installed"),
        "--source-root",
        str(source_root),
        "--proof",
        str(proof_path),
    ]) == 0

    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "installed" / "alpha" / ".kolibri-skill-install.json").read_text(encoding="utf-8"))
    assert proof["status"] == "completed"
    assert proof["action"] == "installed"
    assert proof["network_sources_allowed"] is False
    assert manifest["version"] == "1.0.0"
    assert (tmp_path / "installed" / "alpha" / "SKILL.md").read_text(encoding="utf-8") == "initial"


def test_update_replaces_older_version_atomically(tmp_path):
    sync = load_skill_sync()
    source_root = tmp_path / "source"
    skill_dir = write_skill(source_root, version="1.0.0", body="initial")
    registry_path = tmp_path / "registry.json"
    install_root = tmp_path / "installed"

    assert sync.main(["build-registry", "--source-root", str(source_root), "--output", str(registry_path)]) == 0
    assert sync.main(["install", "--registry", str(registry_path), "--skill", "alpha", "--install-root", str(install_root), "--source-root", str(source_root)]) == 0

    (skill_dir / "skill.json").write_text(
        json.dumps({"name": "alpha", "version": "1.1.0", "description": "test skill"}),
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text("updated", encoding="utf-8")
    assert sync.main(["build-registry", "--source-root", str(source_root), "--output", str(registry_path)]) == 0
    assert sync.main(["update", "--registry", str(registry_path), "--skill", "alpha", "--install-root", str(install_root), "--source-root", str(source_root)]) == 0

    manifest = json.loads((install_root / "alpha" / ".kolibri-skill-install.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "1.1.0"
    assert (install_root / "alpha" / "SKILL.md").read_text(encoding="utf-8") == "updated"


def test_install_blocks_network_sources_and_hash_mismatch(tmp_path):
    sync = load_skill_sync()
    source_root = tmp_path / "source"
    skill_dir = write_skill(source_root)
    registry = sync.build_registry(source_root)
    registry["skills"]["alpha"]["source"]["path"] = "https://example.invalid/alpha.tar.gz"
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    assert sync.main(["install", "--registry", str(registry_path), "--skill", "alpha", "--install-root", str(tmp_path / "installed")]) == 2

    registry = sync.build_registry(source_root)
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    (skill_dir / "SKILL.md").write_text("tampered after registry", encoding="utf-8")
    assert sync.main(["install", "--registry", str(registry_path), "--skill", "alpha", "--install-root", str(tmp_path / "installed"), "--source-root", str(source_root)]) == 2


def test_update_refuses_missing_install_and_downgrade(tmp_path):
    sync = load_skill_sync()
    source_root = tmp_path / "source"
    skill_dir = write_skill(source_root, version="2.0.0")
    registry_path = tmp_path / "registry.json"
    install_root = tmp_path / "installed"

    assert sync.main(["build-registry", "--source-root", str(source_root), "--output", str(registry_path)]) == 0
    assert sync.main(["update", "--registry", str(registry_path), "--skill", "alpha", "--install-root", str(install_root), "--source-root", str(source_root)]) == 2
    assert sync.main(["install", "--registry", str(registry_path), "--skill", "alpha", "--install-root", str(install_root), "--source-root", str(source_root)]) == 0

    (skill_dir / "skill.json").write_text(
        json.dumps({"name": "alpha", "version": "1.0.0", "description": "test skill"}),
        encoding="utf-8",
    )
    assert sync.main(["build-registry", "--source-root", str(source_root), "--output", str(registry_path)]) == 0
    assert sync.main(["install", "--registry", str(registry_path), "--skill", "alpha", "--install-root", str(install_root), "--source-root", str(source_root)]) == 2
