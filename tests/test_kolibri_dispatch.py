import importlib.machinery
import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_dispatch():
    loader = importlib.machinery.SourceFileLoader("kolibri_dispatch", str(ROOT / "ops" / "kolibri-dispatch"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def init_repo(repo: Path) -> None:
    git(repo, "init")
    git(repo, "config", "user.name", "Dispatch Test")
    git(repo, "config", "user.email", "dispatch-test@example.invalid")


def test_ref_preflight_paths_extracts_machine_references_only():
    dispatch = load_dispatch()
    envelope = {
        "base_ref": "HEAD",
        "goal": "Create docs/agent-work/output-to-be-created.md during the task.",
        "verification_commands": [
            "python3 -m json.tool ops/envelopes/KOL-READY.json >/dev/null",
            "test -s docs/agent-work/result.md",
        ],
        "source": {"source_docs": ["docs/desktop-control-app.md"]},
    }

    assert dispatch.ref_preflight_paths(envelope) == [
        "docs/agent-work/result.md",
        "docs/desktop-control-app.md",
        "ops/envelopes/KOL-READY.json",
    ]


def test_ref_preflight_blocks_local_file_missing_from_base_ref(tmp_path):
    dispatch = load_dispatch()
    init_repo(tmp_path)
    envelope_path = tmp_path / "ops" / "envelopes" / "KOL-NEW.json"
    envelope_path.parent.mkdir(parents=True)
    envelope_path.write_text('{"task_id":"KOL-NEW"}\n', encoding="utf-8")
    git(tmp_path, "commit", "--allow-empty", "-m", "base")
    envelope = {
        "base_ref": "HEAD",
        "verification_commands": [
            "python3 -m json.tool ops/envelopes/KOL-NEW.json >/dev/null",
        ],
    }

    assert dispatch.ref_preflight_errors(envelope, tmp_path) == [
        "ops/envelopes/KOL-NEW.json exists locally but is missing from base_ref HEAD",
    ]


def test_ref_preflight_blocks_local_file_that_differs_from_base_ref(tmp_path):
    dispatch = load_dispatch()
    init_repo(tmp_path)
    doc_path = tmp_path / "docs" / "agent-work" / "report.md"
    doc_path.parent.mkdir(parents=True)
    doc_path.write_text("old\n", encoding="utf-8")
    git(tmp_path, "add", "docs/agent-work/report.md")
    git(tmp_path, "commit", "-m", "base")
    doc_path.write_text("new\n", encoding="utf-8")
    envelope = {
        "base_ref": "HEAD",
        "source": {"input_files": ["docs/agent-work/report.md"]},
    }

    assert dispatch.ref_preflight_errors(envelope, tmp_path) == [
        "docs/agent-work/report.md differs from base_ref HEAD; commit and push it before submit",
    ]


def test_ref_preflight_accepts_file_matching_base_ref(tmp_path):
    dispatch = load_dispatch()
    init_repo(tmp_path)
    envelope_path = tmp_path / "ops" / "envelopes" / "KOL-READY.json"
    envelope_path.parent.mkdir(parents=True)
    envelope_path.write_text('{"task_id":"KOL-READY"}\n', encoding="utf-8")
    git(tmp_path, "add", "ops/envelopes/KOL-READY.json")
    git(tmp_path, "commit", "-m", "base")
    envelope = {
        "base_ref": "HEAD",
        "verification_commands": [
            "python3 -m json.tool ops/envelopes/KOL-READY.json >/dev/null",
        ],
    }

    assert dispatch.ref_preflight_errors(envelope, tmp_path) == []
