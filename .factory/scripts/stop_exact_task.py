#!/usr/bin/env python3
"""Safely stop one exact task by PID file and command-line match."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path


def cmdline(pid: int) -> str:
    proc = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, check=False)
    return proc.stdout.strip()


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--pid-file", required=True)
    parser.add_argument("--kill-after-seconds", type=int, default=10)
    args = parser.parse_args()

    pid_path = Path(args.pid_file)
    if not pid_path.exists():
        print(json.dumps({"stopped": False, "error": "pid_file_missing", "pid_file": str(pid_path)}, indent=2))
        return 1
    pid = int(pid_path.read_text(encoding="utf-8").strip())
    command = cmdline(pid)
    if args.task_id not in command:
        print(json.dumps({"stopped": False, "error": "task_id_not_in_command", "pid": pid, "command": command}, indent=2))
        return 2

    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + args.kill_after_seconds
    while time.time() < deadline:
        if not alive(pid):
            print(json.dumps({"stopped": True, "signal": "SIGTERM", "pid": pid, "command": command}, indent=2))
            return 0
        time.sleep(0.5)

    os.kill(pid, signal.SIGKILL)
    print(json.dumps({"stopped": True, "signal": "SIGKILL", "pid": pid, "command": command}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
