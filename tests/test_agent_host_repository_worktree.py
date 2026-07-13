import argparse
import importlib.util
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_agent_host():
    spec = importlib.util.spec_from_file_location(
        "agent_host_repository_worktree", ROOT / "ops" / "agent_host.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=str(repo), text=True, stderr=subprocess.DEVNULL
    ).strip()


def source_repository(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "source"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Kolibri Test")
    git(repo, "config", "user.email", "test@kolibri.invalid")
    (repo / "version.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "version.txt")
    git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "version.txt").write_text("newer\n", encoding="utf-8")
    git(repo, "commit", "-am", "newer")
    return repo, base, git(repo, "rev-parse", "HEAD")


def make_args(tmp_path: Path, repo: Path) -> argparse.Namespace:
    manifest = tmp_path / "mesh.json"
    manifest.write_text(
        json.dumps({"peers": [{"node_id": "home", "mesh_ip": "10.99.0.1"}]}),
        encoding="utf-8",
    )
    return argparse.Namespace(
        control_url="http://10.99.0.1:9101",
        mesh_membership_manifest=str(manifest),
        node_id="worker-test",
        agent_id="agent-host-test",
        capabilities="generic_implementation,runner:mimo",
        repo_url=str(repo),
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
    )


def task(task_id: str, base_commit: str) -> dict:
    return {
        "task_id": task_id,
        "kind": "owner_remote_task",
        "attempt": 1,
        "attempt_id": f"{task_id}-attempt-1",
        "max_attempts": 1,
        "envelope": {
            "execution_contract": "kolibri.development-task.v1",
            "kind": "owner_remote_task",
            "runner": "mimo",
            "repository": "test/immutable-repository",
            "objective": "inspect the repository and return the observed base",
            "branch": f"agent/{task_id.lower()}",
            "base_commit": base_commit,
        },
    }


def test_direct_mimo_clones_and_binds_exact_immutable_base(
    tmp_path: Path, monkeypatch
) -> None:
    agent_host = load_agent_host()
    repo, base_commit, newer_commit = source_repository(tmp_path)
    monkeypatch.setattr(
        agent_host.shutil,
        "which",
        lambda name: "/usr/bin/mimo" if name == "mimo" else None,
    )

    class Host(agent_host.AgentHost):
        def __init__(self):
            super().__init__(make_args(tmp_path, repo))
            self.posts = []
            self.mimo_cwds = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

        def run_command(
            self, command, cwd, stdout_path, stderr_path, leased_task, branch,
            logs, env=None, command_label=None, stdin_path=None,
        ):
            if command[0] == "git":
                return super().run_command(
                    command, cwd, stdout_path, stderr_path, leased_task, branch,
                    logs, env, command_label, stdin_path,
                )
            assert command[0] == "/usr/bin/mimo"
            self.mimo_cwds.append(Path(cwd))
            with stdout_path.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps({
                        "status": "completed",
                        "objective_verdict": "passed",
                        "response": "repository inspected",
                        "changed_files": [],
                    }) + "\n"
                )
            stderr_path.touch()

    host = Host()
    host.run_task(task("MIMO-REPO-BOUND", base_commit))

    assert len(host.mimo_cwds) == 1
    worktree = host.mimo_cwds[0]
    assert (worktree / ".git").exists()
    assert git(worktree, "rev-parse", "HEAD") == base_commit
    assert base_commit != newer_commit
    assert (worktree / "version.txt").read_text(encoding="utf-8") == "base\n"

    complete = [body for path, body in host.posts if path.endswith("/complete")]
    assert len(complete) == 1
    binding = complete[0]["result"]["repository_binding"]
    assert binding["base_commit"] == base_commit
    assert binding["checked_out_commit"] == base_commit
    assert len(binding["binding_sha256"]) == 64
    assert complete[0]["result"]["objective_verdict"] == "passed"
    binding_path = (
        tmp_path / "artifacts" / "MIMO-REPO-BOUND"
        / "MIMO-REPO-BOUND-attempt-1" / "repository-binding.json"
    )
    assert json.loads(binding_path.read_text(encoding="utf-8")) == binding


def test_direct_mimo_never_runs_when_requested_commit_cannot_be_checked_out(
    tmp_path: Path, monkeypatch
) -> None:
    agent_host = load_agent_host()
    repo, _base_commit, _newer_commit = source_repository(tmp_path)
    monkeypatch.setattr(
        agent_host.shutil,
        "which",
        lambda name: "/usr/bin/mimo" if name == "mimo" else None,
    )

    class Host(agent_host.AgentHost):
        def __init__(self):
            super().__init__(make_args(tmp_path, repo))
            self.posts = []
            self.mimo_ran = False

        def post(self, path, body):
            self.posts.append((path, body))
            return body

        def run_command(
            self, command, cwd, stdout_path, stderr_path, leased_task, branch,
            logs, env=None, command_label=None, stdin_path=None,
        ):
            if command[0] == "/usr/bin/mimo":
                self.mimo_ran = True
            return super().run_command(
                command, cwd, stdout_path, stderr_path, leased_task, branch,
                logs, env, command_label, stdin_path,
            )

    host = Host()
    host.run_task(task("MIMO-REPO-MISSING", "0" * 40))

    assert host.mimo_ran is False
    failures = [body for path, body in host.posts if path.endswith("/fail")]
    assert len(failures) == 1
    assert failures[0]["error_type"] == "repository_checkout_failed"
    assert failures[0]["retry"] is False
    assert failures[0]["result"]["status"] == "blocked"
    assert failures[0]["result"]["blocked_reason"] == "repository_checkout_failed"
