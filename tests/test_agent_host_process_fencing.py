import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_agent_host():
    spec = importlib.util.spec_from_file_location(
        "agent_host_process_fencing",
        ROOT / "ops" / "agent_host.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_task(task_id: str, max_wall_seconds):
    return {
        "task_id": task_id,
        "attempt_id": f"{task_id}-attempt-1",
        "envelope": {
            "constraints": {"max_wall_seconds": max_wall_seconds},
        },
    }


def process_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    status = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)],
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return bool(status) and not status.startswith("Z")


def assert_processes_stopped(*pids: int) -> None:
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if not any(process_is_running(pid) for pid in pids):
            return
        time.sleep(0.05)
    assert not {
        pid for pid in pids if process_is_running(pid)
    }, "the fenced process group still contains live processes"


def sleeping_process_group_command(
    pid_file: Path,
    child_ready_file: Path,
    child_terminated_file: Path,
) -> list[str]:
    child_code = r"""
import os
import signal
import sys
import time
from pathlib import Path

ready_file = Path(sys.argv[1])
terminated_file = Path(sys.argv[2])

def terminate(_signum, _frame):
    terminated_file.write_text(str(os.getpid()), encoding="utf-8")
    raise SystemExit(0)

signal.signal(signal.SIGTERM, terminate)
ready_file.write_text(str(os.getpid()), encoding="utf-8")
while True:
    time.sleep(1)
"""
    parent_code = r"""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

pid_file = Path(sys.argv[1])
ready_file = Path(sys.argv[2])
terminated_file = Path(sys.argv[3])
child_code = sys.argv[4]
child = subprocess.Popen(
    [sys.executable, "-c", child_code, str(ready_file), str(terminated_file)]
)

def terminate(_signum, _frame):
    try:
        child.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=1.0)
    raise SystemExit(0)

signal.signal(signal.SIGTERM, terminate)
ready_deadline = time.monotonic() + 5.0
while not ready_file.exists():
    if child.poll() is not None:
        raise RuntimeError("child exited before installing its SIGTERM handler")
    if time.monotonic() >= ready_deadline:
        raise RuntimeError("child readiness timed out")
    time.sleep(0.01)
pid_file.write_text(
    json.dumps({"parent": os.getpid(), "child": child.pid}),
    encoding="utf-8",
)
while True:
    time.sleep(1)
"""
    return [
        sys.executable,
        "-c",
        parent_code,
        str(pid_file),
        str(child_ready_file),
        str(child_terminated_file),
        child_code,
    ]


def stubborn_child_process_group_command(pid_file: Path) -> list[str]:
    child_code = r"""
import signal
import time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
while True:
    time.sleep(1)
"""
    parent_code = r"""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

pid_file = Path(sys.argv[1])
child = subprocess.Popen([sys.executable, "-c", sys.argv[2]])
signal.signal(signal.SIGTERM, lambda *_args: (_ for _ in ()).throw(SystemExit(0)))
pid_file.write_text(json.dumps({"parent": os.getpid(), "child": child.pid}), encoding="utf-8")
while True:
    time.sleep(1)
"""
    return [sys.executable, "-c", parent_code, str(pid_file), child_code]


def run_fenced_command(host, task, tmp_path: Path, pid_file: Path) -> None:
    host.run_command(
        sleeping_process_group_command(
            pid_file,
            tmp_path / "child-ready",
            tmp_path / "child-terminated",
        ),
        tmp_path,
        tmp_path / "stdout.log",
        tmp_path / "stderr.log",
        task,
        None,
        {"stdout": "stdout.log", "stderr": "stderr.log"},
    )


def test_max_wall_seconds_fences_entire_process_group_with_typed_timeout(tmp_path):
    agent_host = load_agent_host()
    pid_file = tmp_path / "pids.json"

    class Host(agent_host.AgentHost):
        def __init__(self):
            self.lease_refresh = 0.25
            self.heartbeat_calls = 0

        def task_heartbeat(self, task, worktree, branch, logs, pid=None):
            del task, worktree, branch, logs, pid
            self.heartbeat_calls += 1
            return {"state": "running"}

    host = Host()
    started = time.monotonic()
    with pytest.raises(agent_host.TaskProcessInterrupted) as error:
        run_fenced_command(host, make_task("TIMEOUT", 0.75), tmp_path, pid_file)

    assert error.value.error_type == "provider_timeout"
    assert error.value.retry is False
    assert "constraints.max_wall_seconds" in str(error.value)
    assert time.monotonic() - started < 3.0
    assert host.heartbeat_calls >= 1
    pids = json.loads(pid_file.read_text(encoding="utf-8"))
    assert (tmp_path / "child-terminated").read_text(encoding="utf-8") == str(
        pids["child"]
    )
    assert_processes_stopped(pids["parent"], pids["child"])


def test_authoritative_heartbeat_cancellation_fences_entire_process_group(tmp_path):
    agent_host = load_agent_host()
    pid_file = tmp_path / "pids.json"

    class Host(agent_host.AgentHost):
        def __init__(self):
            self.lease_refresh = 0.25
            self.heartbeat_calls = 0

        def task_heartbeat(self, task, worktree, branch, logs, pid=None):
            del task, worktree, branch, logs, pid
            self.heartbeat_calls += 1
            if pid_file.exists():
                return {
                    "state": "cancelled",
                    "cancel_requested_at": "2026-07-11T00:00:00Z",
                    "cancel_fence_id": "cancel-fence-1",
                }
            return {"state": "running"}

    host = Host()
    task = make_task("CANCELLED", 10)
    started = time.monotonic()
    with pytest.raises(agent_host.TaskProcessInterrupted) as error:
        run_fenced_command(host, task, tmp_path, pid_file)

    assert error.value.error_type == "task_cancelled"
    assert error.value.retry is False
    assert "terminal cancellation fence" in str(error.value)
    assert time.monotonic() - started < 3.0
    assert host.heartbeat_calls >= 2
    pids = json.loads(pid_file.read_text(encoding="utf-8"))
    assert (tmp_path / "child-terminated").read_text(encoding="utf-8") == str(
        pids["child"]
    )
    assert_processes_stopped(pids["parent"], pids["child"])


def test_sigkill_escalation_catches_child_after_parent_exits_on_sigterm(tmp_path):
    agent_host = load_agent_host()
    pid_file = tmp_path / "stubborn-pids.json"

    class Host(agent_host.AgentHost):
        def __init__(self):
            self.lease_refresh = 0.25

        def task_heartbeat(self, task, worktree, branch, logs, pid=None):
            del task, worktree, branch, logs, pid
            return {"state": "running"}

    started = time.monotonic()
    with pytest.raises(agent_host.TaskProcessInterrupted) as error:
        Host().run_command(
            stubborn_child_process_group_command(pid_file),
            tmp_path,
            tmp_path / "stubborn-stdout.log",
            tmp_path / "stubborn-stderr.log",
            make_task("STUBBORN", 0.5),
            None,
            {},
        )

    assert error.value.error_type == "provider_timeout"
    assert time.monotonic() - started < 5.0
    pids = json.loads(pid_file.read_text(encoding="utf-8"))
    assert_processes_stopped(pids["parent"], pids["child"])


@pytest.mark.parametrize(
    "authoritative",
    [
        {"state": "completed"},
        {"state": "failed"},
        {"state": "dead_letter"},
        {"state": "running", "cancel_fence_id": "fence"},
        {"task": {"state": "cancelled"}},
        {},
        None,
    ],
)
def test_authoritative_terminal_or_cancel_fence_is_never_treated_as_running(
    authoritative,
):
    agent_host = load_agent_host()
    assert agent_host.AgentHost.task_cancel_requested(authoritative) is True


@pytest.mark.parametrize("invalid_max_wall_seconds", [0, -1, True, "60", 86_401])
def test_invalid_max_wall_seconds_is_rejected_before_process_spawn(
    tmp_path,
    invalid_max_wall_seconds,
):
    agent_host = load_agent_host()
    spawned_marker = tmp_path / "spawned"

    class Host(agent_host.AgentHost):
        def __init__(self):
            self.lease_refresh = 0.25

        def task_heartbeat(self, task, worktree, branch, logs, pid=None):
            raise AssertionError("invalid constraints must fail before heartbeat")

    command = [
        sys.executable,
        "-c",
        "from pathlib import Path; import sys; Path(sys.argv[1]).touch()",
        str(spawned_marker),
    ]
    with pytest.raises(agent_host.TaskProcessInterrupted) as error:
        Host().run_command(
            command,
            tmp_path,
            tmp_path / "stdout.log",
            tmp_path / "stderr.log",
            make_task("INVALID", invalid_max_wall_seconds),
            None,
            {},
        )

    assert error.value.error_type == "task_contract_invalid"
    assert error.value.retry is False
    assert not spawned_marker.exists()
    assert not (tmp_path / "stdout.log").exists()
    assert not (tmp_path / "stderr.log").exists()


def test_exhausted_attempt_deadline_is_rejected_before_process_spawn(tmp_path):
    agent_host = load_agent_host()
    spawned_marker = tmp_path / "spawned-after-deadline"
    task = make_task("ALREADY-EXPIRED", 0.25)
    task["_agent_host_started_monotonic"] = time.monotonic() - 1.0

    class Host(agent_host.AgentHost):
        def __init__(self):
            self.lease_refresh = 0.25

        def task_heartbeat(self, task, worktree, branch, logs, pid=None):
            raise AssertionError("expired attempt must fail before heartbeat")

    command = [
        sys.executable,
        "-c",
        "from pathlib import Path; import sys; Path(sys.argv[1]).touch()",
        str(spawned_marker),
    ]
    with pytest.raises(agent_host.TaskProcessInterrupted) as error:
        Host().run_command(
            command,
            tmp_path,
            tmp_path / "expired-stdout.log",
            tmp_path / "expired-stderr.log",
            task,
            None,
            {},
        )

    assert error.value.error_type == "provider_timeout"
    assert error.value.retry is False
    assert not spawned_marker.exists()
    assert not (tmp_path / "expired-stdout.log").exists()
    assert not (tmp_path / "expired-stderr.log").exists()


def test_preexisting_cancel_fence_is_rejected_before_process_spawn(tmp_path):
    agent_host = load_agent_host()
    spawned_marker = tmp_path / "spawned-after-cancel"

    class Host(agent_host.AgentHost):
        def __init__(self):
            self.lease_refresh = 0.25

        def task_heartbeat(self, task, worktree, branch, logs, pid=None):
            del task, worktree, branch, logs, pid
            return {
                "state": "cancelled",
                "cancel_requested_at": "2026-07-11T00:00:00Z",
                "cancel_fence_id": "cancel-before-spawn",
            }

    command = [
        sys.executable,
        "-c",
        "from pathlib import Path; import sys; Path(sys.argv[1]).touch()",
        str(spawned_marker),
    ]
    with pytest.raises(agent_host.TaskProcessInterrupted) as error:
        Host().run_command(
            command,
            tmp_path,
            tmp_path / "cancelled-stdout.log",
            tmp_path / "cancelled-stderr.log",
            make_task("CANCELLED-BEFORE-SPAWN", 10),
            None,
            {},
        )

    assert error.value.error_type == "task_cancelled"
    assert error.value.retry is False
    assert not spawned_marker.exists()
    assert not (tmp_path / "cancelled-stdout.log").exists()
    assert not (tmp_path / "cancelled-stderr.log").exists()


def test_authoritative_process_fence_takes_precedence_over_provider_error_log(
    tmp_path,
):
    agent_host = load_agent_host()

    class Host(agent_host.AgentHost):
        def __init__(self):
            pass

        def run_command(
            self, command, cwd, stdout_path, stderr_path, task, branch, logs,
            env=None, command_label=None, stdin_path=None,
        ):
            del self, command, cwd, task, branch, logs, env, command_label, stdin_path
            stdout_path.write_text("HTTP 401 unauthorized from an earlier event\n")
            stderr_path.write_text("provider output before deadline\n")
            raise agent_host.TaskProcessInterrupted(
                "provider_timeout",
                "execution exceeded constraints.max_wall_seconds",
                retry=False,
            )

    with pytest.raises(agent_host.TaskProcessInterrupted) as error:
        Host().run_json_payload_command(
            ["mimo"],
            "mimo <prompt>",
            "mimo",
            tmp_path,
            tmp_path / "provider-stdout.log",
            tmp_path / "provider-stderr.log",
            make_task("FENCE-PRECEDENCE", 1),
            None,
            {},
        )

    assert error.value.error_type == "provider_timeout"
    assert error.value.retry is False


@pytest.mark.parametrize("error_type", ["provider_timeout", "task_cancelled"])
def test_run_task_reports_process_fences_as_non_retryable_typed_failures(
    tmp_path,
    error_type,
):
    agent_host = load_agent_host()

    class Host(agent_host.AgentHost):
        def __init__(self):
            self.artifact_root = tmp_path / "artifacts"
            self.node_id = "worker-fenced"
            self.hostname = "worker-fenced.example"
            self.agent_id = "agent-worker-fenced"
            self.pid = os.getpid()
            self.failures = []

        def unsupported_task_reason(self, task):
            return None

        def validate_runtime_permission_contract(self, task):
            return agent_host.classify_permission_pack(task)

        def run_read_only_probe(self, task):
            raise agent_host.TaskProcessInterrupted(
                error_type,
                "authoritative process fence",
                retry=False,
            )

        def fail(
            self, task, observed_error_type, error, result, result_path,
            retry=True,
        ):
            self.failures.append({
                "task": task,
                "error_type": observed_error_type,
                "error": error,
                "result": result,
                "result_path": result_path,
                "retry": retry,
            })

    task = {
        "task_id": f"TYPED-{error_type}",
        "attempt": 1,
        "attempt_id": f"TYPED-{error_type}-attempt-1",
        "max_retries": 3,
        "kind": "read_only_probe",
        "envelope": {"kind": "read_only_probe", "read_only": True},
    }
    host = Host()

    host.run_task(task)

    assert len(host.failures) == 1
    failure = host.failures[0]
    assert failure["error_type"] == error_type
    assert failure["retry"] is False
    assert failure["result"]["status"] == "failed"
    assert failure["result"]["failure_reason"].startswith(error_type + ":")
    persisted = json.loads(Path(failure["result_path"]).read_text(encoding="utf-8"))
    assert persisted["failure_reason"].startswith(error_type + ":")
