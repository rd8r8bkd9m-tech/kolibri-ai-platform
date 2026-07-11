#!/usr/bin/env python3
"""Supervise Agent Host and write only bounded, redacted rotating logs."""

from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO


MAX_LOG_BYTES = 5 * 1024 * 1024
MAX_LINE_CHARS = 4096
SECRET_MARKERS = (
    "access_token",
    "api key",
    "api_key",
    "authorization",
    "bearer ",
    "client_secret",
    "cookie",
    "credential",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "token=",
)
TOKEN_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b", re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_log_line(value: str) -> str:
    line = str(value).replace("\x00", "").rstrip("\r\n")
    lowered = line.lower()
    if TOKEN_PATTERN.search(line) or any(marker in lowered for marker in SECRET_MARKERS):
        return f"{utc_now()} [redacted sensitive provider log line]"
    if len(line) > MAX_LINE_CHARS:
        return f"{line[:MAX_LINE_CHARS]} [truncated]"
    return line


class RotatingSecureLog:
    def __init__(self, path: Path, max_bytes: int = MAX_LOG_BYTES):
        self.path = path
        self.max_bytes = max_bytes
        self.handle: TextIO | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        self._open()

    def _open(self) -> None:
        self.handle = self.path.open("a", encoding="utf-8")
        os.chmod(self.path, 0o600)

    def _rotate_if_needed(self) -> None:
        if self.path.stat().st_size < self.max_bytes:
            return
        assert self.handle is not None
        self.handle.close()
        previous = self.path.with_suffix(f"{self.path.suffix}.1")
        try:
            previous.unlink()
        except FileNotFoundError:
            pass
        os.replace(self.path, previous)
        os.chmod(previous, 0o600)
        self._open()

    def write(self, line: str) -> None:
        self._rotate_if_needed()
        assert self.handle is not None
        self.handle.write(f"{redact_log_line(line)}\n")
        self.handle.flush()

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-path", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("a supervised command is required")

    log = RotatingSecureLog(args.log_path.expanduser())
    child: subprocess.Popen[str] | None = None

    def forward(signum: int, _frame: object) -> None:
        if child is not None and child.poll() is None:
            child.send_signal(signum)

    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGINT, forward)
    try:
        child = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            close_fds=True,
        )
        log.write(f"{utc_now()} launcher_started child_pid={child.pid}")
        assert child.stdout is not None
        for line in child.stdout:
            log.write(line)
        return_code = child.wait()
        log.write(f"{utc_now()} launcher_stopped exit_code={return_code}")
        return return_code
    except Exception as exc:
        log.write(f"{utc_now()} launcher_failed error_type={type(exc).__name__}")
        return 70
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        log.close()


if __name__ == "__main__":
    raise SystemExit(main())
