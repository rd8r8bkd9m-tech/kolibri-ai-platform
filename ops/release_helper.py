#!/usr/bin/env python3
"""Narrow Unix-socket boundary for privileged release installation."""

from __future__ import annotations

import argparse
import json
import os
import pwd
import socket
import struct
from pathlib import Path
from typing import Any, Callable

try:
    from ops.release_installer import (
        RELEASE_CAPABILITY,
        RELEASE_TASK_KINDS,
        ReleaseInstallError,
        ReleaseInstaller,
    )
except ImportError:  # installed standalone beside this module
    from release_installer import (
        RELEASE_CAPABILITY,
        RELEASE_TASK_KINDS,
        ReleaseInstallError,
        ReleaseInstaller,
    )


PROTOCOL_VERSION = "kolibri.release-helper.v1"
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
DEFAULT_SOCKET = "/run/kolibri-release/installer.sock"


class ReleaseHelperProtocolError(RuntimeError):
    pass


def _encode_frame(value: dict[str, Any], *, max_bytes: int) -> bytes:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if not payload or len(payload) > max_bytes:
        raise ReleaseHelperProtocolError("release_helper_frame_too_large")
    return struct.pack("!I", len(payload)) + payload


def _recv_exact(
    connection: socket.socket,
    size: int,
    *,
    progress_callback: Callable[[], None] | None = None,
) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        try:
            chunk = connection.recv(remaining)
        except socket.timeout:
            if progress_callback is not None:
                progress_callback()
            continue
        if not chunk:
            raise ReleaseHelperProtocolError("release_helper_connection_closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _recv_frame(
    connection: socket.socket,
    *,
    max_bytes: int,
    progress_callback: Callable[[], None] | None = None,
) -> dict[str, Any]:
    header = _recv_exact(connection, 4, progress_callback=progress_callback)
    size = struct.unpack("!I", header)[0]
    if not 1 <= size <= max_bytes:
        raise ReleaseHelperProtocolError("release_helper_frame_too_large")
    raw = _recv_exact(connection, size, progress_callback=progress_callback)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseHelperProtocolError("release_helper_json_invalid") from exc
    if not isinstance(value, dict):
        raise ReleaseHelperProtocolError("release_helper_request_invalid")
    return value


class ReleaseHelperClient:
    def __init__(self, socket_path: str | Path | None = None):
        self.socket_path = Path(
            socket_path or os.environ.get("KOLIBRI_RELEASE_HELPER_SOCKET", DEFAULT_SOCKET)
        )

    @classmethod
    def from_environment(cls, **_ignored: Any) -> "ReleaseHelperClient":
        return cls()

    def _request(
        self,
        request: dict[str, Any],
        *,
        progress_callback: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        frame = _encode_frame(request, max_bytes=MAX_REQUEST_BYTES)
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(2)
                connection.connect(str(self.socket_path))
                connection.sendall(frame)
                connection.settimeout(1)
                return _recv_frame(
                    connection,
                    max_bytes=MAX_RESPONSE_BYTES,
                    progress_callback=progress_callback,
                )
        except ReleaseInstallError:
            raise
        except (OSError, ReleaseHelperProtocolError) as exc:
            raise ReleaseInstallError("release_helper_unavailable", retryable=True) from exc
        except Exception as exc:
            raise ReleaseInstallError("release_task_heartbeat_failed", retryable=True) from exc

    def prerequisite_status(self) -> dict[str, Any]:
        try:
            response = self._request({"protocol_version": PROTOCOL_VERSION, "operation": "status"})
        except ReleaseInstallError as exc:
            return {
                "status": "unavailable",
                "capability": RELEASE_CAPABILITY,
                "reasons": [exc.code],
                "privilege_boundary": "unix_socket_helper",
            }
        status = response.get("result") if isinstance(response.get("result"), dict) else {}
        return {**status, "privilege_boundary": "unix_socket_helper"}

    def execute(
        self,
        kind: str,
        envelope: dict[str, Any],
        evidence_dir: Path,
        *,
        progress_callback: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        response = self._request(
            {
                "protocol_version": PROTOCOL_VERSION,
                "operation": "execute",
                "kind": kind,
                "envelope": envelope,
                "evidence_dir": str(evidence_dir),
            },
            progress_callback=progress_callback,
        )
        if response.get("status") == "error":
            error = response.get("error") if isinstance(response.get("error"), dict) else {}
            raise ReleaseInstallError(
                str(error.get("code") or "release_helper_failed"),
                retryable=error.get("retryable") is True,
                evidence=error.get("evidence") if isinstance(error.get("evidence"), dict) else None,
            )
        result = response.get("result")
        if response.get("status") != "ok" or not isinstance(result, dict):
            raise ReleaseInstallError("release_helper_response_invalid")
        return result


class ReleaseHelperServer:
    def __init__(self, installer: ReleaseInstaller, *, allowed_uid: int):
        self.installer = installer
        self.allowed_uid = allowed_uid

    def _verify_peer(self, connection: socket.socket) -> None:
        if not hasattr(socket, "SO_PEERCRED"):
            raise ReleaseHelperProtocolError("release_helper_peer_credentials_unavailable")
        raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", raw)
        if uid != self.allowed_uid:
            raise ReleaseHelperProtocolError("release_helper_peer_forbidden")

    @staticmethod
    def _ensure_connected(connection: socket.socket) -> None:
        previous_timeout = connection.gettimeout()
        try:
            connection.setblocking(False)
            try:
                pending = connection.recv(1, socket.MSG_PEEK)
            except BlockingIOError:
                return
            if pending == b"":
                raise ReleaseInstallError("release_helper_client_disconnected", retryable=True)
            raise ReleaseInstallError("release_helper_protocol_trailing_data")
        finally:
            connection.settimeout(previous_timeout)

    def _dispatch(self, request: dict[str, Any], connection: socket.socket) -> dict[str, Any]:
        if request.get("protocol_version") != PROTOCOL_VERSION:
            raise ReleaseHelperProtocolError("release_helper_protocol_version_invalid")
        operation = request.get("operation")
        if operation == "status":
            if set(request) != {"protocol_version", "operation"}:
                raise ReleaseHelperProtocolError("release_helper_request_invalid")
            return {"status": "ok", "result": self.installer.prerequisite_status()}
        if operation != "execute" or set(request) != {
            "protocol_version",
            "operation",
            "kind",
            "envelope",
            "evidence_dir",
        }:
            raise ReleaseHelperProtocolError("release_helper_request_invalid")
        kind = str(request.get("kind") or "")
        envelope = request.get("envelope")
        evidence_dir = request.get("evidence_dir")
        if kind not in RELEASE_TASK_KINDS or not isinstance(envelope, dict):
            raise ReleaseHelperProtocolError("release_helper_request_invalid")
        if not isinstance(evidence_dir, str) or not evidence_dir.startswith("/") or len(evidence_dir) > 4096:
            raise ReleaseHelperProtocolError("release_helper_request_invalid")
        self._ensure_connected(connection)
        result = self.installer.execute(
            kind,
            envelope,
            Path(evidence_dir),
            progress_callback=lambda: self._ensure_connected(connection),
        )
        return {"status": "ok", "result": result}

    def handle(self, connection: socket.socket) -> None:
        try:
            connection.settimeout(5)
            self._verify_peer(connection)
            request = _recv_frame(connection, max_bytes=MAX_REQUEST_BYTES)
            response = self._dispatch(request, connection)
        except ReleaseInstallError as exc:
            response = {
                "status": "error",
                "error": {"code": exc.code, "retryable": exc.retryable, "evidence": exc.evidence},
            }
        except ReleaseHelperProtocolError as exc:
            response = {"status": "error", "error": {"code": str(exc), "retryable": False}}
        except Exception:
            response = {
                "status": "error",
                "error": {"code": "release_helper_internal_error", "retryable": True},
            }
        try:
            connection.sendall(_encode_frame(response, max_bytes=MAX_RESPONSE_BYTES))
        except OSError:
            pass

    def serve(self, listener: socket.socket) -> None:
        while True:
            connection, _address = listener.accept()
            with connection:
                self.handle(connection)


def _systemd_listener() -> socket.socket:
    if int(os.environ.get("LISTEN_PID", "0")) != os.getpid() or int(
        os.environ.get("LISTEN_FDS", "0")
    ) != 1:
        raise ReleaseHelperProtocolError("release_helper_systemd_socket_missing")
    return socket.fromfd(3, socket.AF_UNIX, socket.SOCK_STREAM)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve-systemd", action="store_true")
    parser.add_argument(
        "--allowed-user",
        default=os.environ.get("KOLIBRI_RELEASE_HELPER_ALLOWED_USER", "kolibri-agent"),
    )
    args = parser.parse_args(argv)
    if not args.serve_systemd:
        parser.error("only --serve-systemd is supported")
    try:
        allowed_uid = pwd.getpwnam(args.allowed_user).pw_uid
    except KeyError as exc:
        raise SystemExit("release_helper_allowed_user_missing") from exc
    server = ReleaseHelperServer(ReleaseInstaller.from_environment(), allowed_uid=allowed_uid)
    server.serve(_systemd_listener())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
