#!/usr/bin/env python3
"""Read-only MikroTik RouterOS live-state audit for Kolibri GoMesh.

The script has two safe modes:

1. Without --dump it checks MikroTik management reachability and whether
   non-interactive SSH is available. It does not authenticate with passwords and
   does not run write commands.
2. With --dump it parses text captured from `/system/script/run
   kolibri-home-gw-status` or a RouterOS export and verifies expected Kolibri
   routing, DNS redirect, and helper-script state.

It never changes RouterOS configuration and never reads PSK material.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_MANIFESTS = (
    Path("/etc/kolibri-gomesh/exits.json"),
    Path("/opt/kolibri/repo/ops/kolibri-gomesh-exits.json"),
)
DEFAULT_API_PASSWORD_FILE = Path("/etc/kolibri-gomesh/routeros-api.password")
DEFAULT_API_USER = "kolibri-ro"
DEFAULT_BUNDLE_VERIFY = Path("/usr/local/sbin/kolibri-gomesh-routeros-api-bundle-verify")


def run(argv: list[str], timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "exit_code": 127,
            "stdout": "",
            "stderr": str(exc),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "exit_code": 124,
            "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            "stderr": "timeout",
            "duration_ms": int((time.monotonic() - started) * 1000),
        }


def parse_json(stdout: str) -> dict[str, Any]:
    if not stdout:
        return {}
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {"ok": False, "parse_error": str(exc), "raw_stdout_prefix": stdout[:500]}
    return value if isinstance(value, dict) else {"ok": False, "parse_error": "JSON root is not object"}


def summarize_command(result: dict[str, Any]) -> dict[str, Any]:
    return {key: result[key] for key in ("ok", "exit_code", "duration_ms", "stderr")}


def load_manifest(path: Path | None) -> tuple[Path, dict[str, Any]]:
    candidates = (path,) if path else DEFAULT_MANIFESTS
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate, json.loads(candidate.read_text())
    searched = ", ".join(str(item) for item in candidates if item)
    raise SystemExit(f"manifest not found; searched: {searched}")


def tcp_check(host: str, port: int, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            ok = True
            error = ""
    except Exception as exc:  # noqa: BLE001 - audit output should include reason.
        ok = False
        error = f"{type(exc).__name__}: {exc}"
    return {
        "host": host,
        "port": port,
        "ok": ok,
        "error": error,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


def api_encode_len(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    if length < 0x4000:
        return bytes([(length >> 8) | 0x80, length & 0xFF])
    if length < 0x200000:
        return bytes([(length >> 16) | 0xC0, (length >> 8) & 0xFF, length & 0xFF])
    if length < 0x10000000:
        return bytes([(length >> 24) | 0xE0, (length >> 16) & 0xFF, (length >> 8) & 0xFF, length & 0xFF])
    return bytes([0xF0, (length >> 24) & 0xFF, (length >> 16) & 0xFF, (length >> 8) & 0xFF, length & 0xFF])


def api_read_exact(sock: socket.socket, length: int) -> bytes:
    data = b""
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise EOFError("RouterOS API connection closed")
        data += chunk
    return data


def api_read_len(sock: socket.socket) -> int | None:
    first = sock.recv(1)
    if not first:
        return None
    value = first[0]
    if (value & 0x80) == 0:
        return value
    if (value & 0xC0) == 0x80:
        return ((value & ~0xC0) << 8) + api_read_exact(sock, 1)[0]
    if (value & 0xE0) == 0xC0:
        data = api_read_exact(sock, 2)
        return ((value & ~0xE0) << 16) + (data[0] << 8) + data[1]
    if (value & 0xF0) == 0xE0:
        data = api_read_exact(sock, 3)
        return ((value & ~0xF0) << 24) + (data[0] << 16) + (data[1] << 8) + data[2]
    data = api_read_exact(sock, 4)
    return (data[0] << 24) + (data[1] << 16) + (data[2] << 8) + data[3]


def api_write_sentence(sock: socket.socket, words: list[str]) -> None:
    for word in words:
        data = word.encode()
        sock.sendall(api_encode_len(len(data)) + data)
    sock.sendall(b"\x00")


def api_read_sentence(sock: socket.socket) -> list[str]:
    words: list[str] = []
    while True:
        length = api_read_len(sock)
        if length is None:
            raise EOFError("RouterOS API connection closed")
        if length == 0:
            return words
        words.append(api_read_exact(sock, length).decode(errors="replace"))


def api_transact(sock: socket.socket, words: list[str], max_sentences: int = 200) -> list[list[str]]:
    api_write_sentence(sock, words)
    replies: list[list[str]] = []
    for _ in range(max_sentences):
        sentence = api_read_sentence(sock)
        replies.append(sentence)
        if sentence and sentence[0] in ("!done", "!fatal"):
            break
    return replies


def api_reply_ok(replies: list[list[str]]) -> bool:
    saw_done = any(sentence and sentence[0] == "!done" for sentence in replies)
    saw_error = any(sentence and sentence[0] in ("!trap", "!fatal") for sentence in replies)
    return saw_done and not saw_error


def api_word_dict(sentence: list[str]) -> dict[str, str]:
    item: dict[str, str] = {}
    for word in sentence:
        if not word.startswith("="):
            continue
        _, key, value = word.split("=", 2)
        item[key] = value
    return item


def api_rows(replies: list[list[str]]) -> list[dict[str, str]]:
    return [api_word_dict(sentence) for sentence in replies if sentence and sentence[0] == "!re"]


def normalize_value(key: str, value: str) -> str:
    if key == "disabled":
        if value.lower() in ("true", "yes"):
            return "yes"
        if value.lower() in ("false", "no"):
            return "no"
    if key == "allow-remote-requests":
        if value.lower() in ("true", "yes"):
            return "yes"
        if value.lower() in ("false", "no"):
            return "no"
    return value


def api_line(menu: str, row: dict[str, str], keys: list[str]) -> str:
    parts = []
    for key in keys:
        if key in row:
            parts.append(f"{key}={normalize_value(key, row[key])}")
    return f"{menu} " + " ".join(parts)


def api_dump_from_rows(manifest: dict[str, Any], rows_by_menu: dict[str, list[dict[str, str]]]) -> str:
    mikrotik = manifest.get("mikrotik_gateway", {})
    table = str(mikrotik.get("policy_table", "kolibri-home-gw"))
    lines: list[str] = []

    for row in rows_by_menu.get("/routing/table/print", []):
        if row.get("name") == table:
            lines.append(api_line("/routing/table", row, ["name", "fib", "disabled"]))

    for row in rows_by_menu.get("/ip/route/print", []):
        comment = row.get("comment", "")
        if "Kolibri Home gateway" in comment or row.get("routing-table") == table:
            lines.append(api_line("/ip/route", row, ["dst-address", "gateway", "routing-table", "distance", "disabled", "comment"]))

    for row in rows_by_menu.get("/routing/rule/print", []):
        if "Kolibri Home gateway" in row.get("comment", ""):
            lines.append(api_line("/routing/rule", row, ["src-address", "dst-address", "action", "table", "disabled", "comment"]))

    for row in rows_by_menu.get("/ip/firewall/nat/print", []):
        if "Kolibri DNS redirect" in row.get("comment", ""):
            lines.append(api_line("/ip/firewall/nat", row, ["chain", "action", "to-ports", "protocol", "src-address", "dst-port", "disabled", "comment"]))

    for row in rows_by_menu.get("/system/script/print", []):
        name = row.get("name", "")
        if "kolibri-home-gw" in name:
            lines.append(api_line("/system/script", row, ["name", "policy", "run-count", "source", "disabled"]))

    for row in rows_by_menu.get("/system/scheduler/print", []):
        name = row.get("name", "")
        if "kolibri-home-gw" in name:
            lines.append(api_line("/system/scheduler", row, ["name", "interval", "on-event", "policy", "disabled"]))

    for row in rows_by_menu.get("/ip/dns/print", []):
        lines.append(api_line("/ip/dns", row, ["servers", "allow-remote-requests"]))

    return "\n".join(lines) + ("\n" if lines else "")


def routeros_api_snapshot(
    manifest: dict[str, Any],
    host: str,
    port: int,
    user: str,
    password: str | None,
    timeout: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "attempted": bool(password is not None),
        "ok": False,
        "login_ok": False,
        "host": host,
        "port": port,
        "user": user,
        "error": "",
        "dump_text": "",
        "menus": {},
    }
    if password is None:
        result["error"] = "RouterOS API password not supplied"
        return result
    menus = [
        "/routing/table/print",
        "/ip/route/print",
        "/routing/rule/print",
        "/ip/firewall/nat/print",
        "/system/script/print",
        "/system/scheduler/print",
        "/ip/dns/print",
    ]
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            login = api_transact(sock, ["/login", f"=name={user}", f"=password={password}"], max_sentences=8)
            result["login_ok"] = api_reply_ok(login)
            result["login_reply_types"] = [sentence[0] for sentence in login if sentence]
            if not result["login_ok"]:
                result["error"] = "RouterOS API login failed"
                return result
            rows_by_menu: dict[str, list[dict[str, str]]] = {}
            for menu in menus:
                replies = api_transact(sock, [menu], max_sentences=500)
                rows_by_menu[menu] = api_rows(replies)
                result["menus"][menu] = {
                    "ok": api_reply_ok(replies),
                    "row_count": len(rows_by_menu[menu]),
                    "reply_types": [sentence[0] for sentence in replies if sentence][:5],
                }
            try:
                api_transact(sock, ["/quit"], max_sentences=2)
            except Exception:
                pass
        result["dump_text"] = api_dump_from_rows(manifest, rows_by_menu)
        result["ok"] = bool(result["dump_text"])
    except Exception as exc:  # noqa: BLE001 - audit output should include reason.
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def ssh_probe(host: str, user: str, timeout: int) -> dict[str, Any]:
    result = run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={timeout}",
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"{user}@{host}",
            "/system/resource/print",
        ],
        timeout=timeout + 3,
    )
    # Do not leak banners or auth detail beyond the first safe line.
    stderr = result["stderr"].replace("\r", "\n")
    stdout = result["stdout"].replace("\r", "\n")
    result["stderr"] = "\n".join(stderr.splitlines()[:3])
    result["stdout"] = "\n".join(stdout.splitlines()[:10])
    return result


def compact(text: str) -> str:
    return " ".join(line.strip() for line in text.splitlines() if line.strip())


def contains_all(text: str, needles: list[str]) -> bool:
    return all(needle in text for needle in needles)


def state_for_line(line: str) -> str:
    if "disabled=yes" in line or "disabled=true" in line:
        return "disabled"
    if "disabled=no" in line or "disabled=false" in line:
        return "enabled"
    return "enabled"


def find_line(text: str, needles: list[str]) -> str:
    for line in text.splitlines():
        if contains_all(line, needles):
            return line.strip()
    flat = compact(text)
    if contains_all(flat, needles):
        return flat
    return ""


def audit_dump(manifest: dict[str, Any], dump_text: str, expected_scope: str = "pre-rollout") -> dict[str, Any]:
    mikrotik = manifest.get("mikrotik_gateway", {})
    dns = mikrotik.get("dns", {})
    table = str(mikrotik.get("policy_table", "kolibri-home-gw"))
    home_next_hop = str(mikrotik.get("home_next_hop", ""))
    scripts = mikrotik.get("scripts", {})
    guard = mikrotik.get("guard", {})
    blockers: list[str] = []
    warnings: list[str] = []
    lan_expected_enabled = expected_scope == "lan"
    lan_expected_state = "enabled" if lan_expected_enabled else "disabled"

    checks: dict[str, Any] = {}

    table_line = find_line(dump_text, [table])
    checks["policy_table"] = {"ok": bool(table_line), "line": table_line}
    if not table_line:
        blockers.append(f"live dump does not show routing table {table}")

    route_checks = []
    for route in mikrotik.get("routes", []):
        needles = [
            str(route.get("dst", "")),
            str(route.get("gateway", "")),
            str(route.get("comment", "")),
        ]
        line = find_line(dump_text, [needle for needle in needles if needle])
        ok = bool(line)
        if route.get("enabled", True) and "disabled=yes" in line:
            ok = False
        route_checks.append({"comment": route.get("comment"), "ok": ok, "line": line})
        if not ok:
            blockers.append(f"live dump route check failed: {route.get('comment')}")
    checks["routes"] = route_checks

    dns_servers = ",".join(str(item) for item in dns.get("upstream_servers", []))
    dns_line = find_line(dump_text, ["servers=", "allow-remote-requests"])
    dns_ok = bool(dns_line) and dns_servers in dns_line and "allow-remote-requests=yes" in dns_line
    checks["dns"] = {"ok": dns_ok, "expected_servers": dns_servers, "line": dns_line}
    if not dns_ok:
        blockers.append("live dump DNS state does not match manifest")

    rule_checks = []
    for state, items, expected_disabled in (
        ("active_canary", mikrotik.get("active_canaries", []), False),
        ("disabled_canary", mikrotik.get("disabled_canaries", []), True),
    ):
        for item in items:
            line = find_line(dump_text, [str(item.get("ip")), str(item.get("routing_rule_comment"))])
            observed = state_for_line(line) if line else "missing"
            expected = "disabled" if expected_disabled else "enabled"
            ok = observed == expected
            rule_checks.append(
                {
                    "id": item.get("id"),
                    "state": state,
                    "ip": item.get("ip"),
                    "expected": expected,
                    "observed": observed,
                    "ok": ok,
                    "line": line,
                }
            )
            if not ok:
                blockers.append(f"live dump routing rule state mismatch for {item.get('id')}: expected {expected}, observed {observed}")
    rollout = mikrotik.get("disabled_rollout", {})
    rollout_line = find_line(dump_text, [str(rollout.get("src", "")), str(rollout.get("routing_rule_comment", ""))])
    rollout_observed = state_for_line(rollout_line) if rollout_line else "missing"
    rollout_ok = rollout_observed == lan_expected_state
    rule_checks.append(
        {
            "id": rollout.get("id", "lan-rollout"),
            "state": "lan_rollout",
            "src": rollout.get("src"),
            "expected": lan_expected_state,
            "observed": rollout_observed,
            "ok": rollout_ok,
            "line": rollout_line,
        }
    )
    if not rollout_ok:
        blockers.append(f"live dump LAN rollout state mismatch: expected {lan_expected_state}, observed {rollout_observed}")
    checks["routing_rules"] = rule_checks

    nat_checks = []
    for state, items, expected_disabled in (
        ("active_canary", mikrotik.get("active_canaries", []), False),
        ("disabled_canary", mikrotik.get("disabled_canaries", []), True),
    ):
        for item in items:
            if not item.get("dns_redirect"):
                continue
            for protocol in ("UDP", "TCP"):
                line = find_line(dump_text, [str(item.get("ip")), "Kolibri DNS redirect", protocol])
                observed = state_for_line(line) if line else "missing"
                expected = "disabled" if expected_disabled else "enabled"
                ok = observed == expected
                nat_checks.append(
                    {
                        "id": item.get("id"),
                        "state": state,
                        "protocol": protocol,
                        "expected": expected,
                        "observed": observed,
                        "ok": ok,
                        "line": line,
                    }
                )
                if not ok:
                    blockers.append(f"live dump DNS redirect state mismatch for {item.get('id')} {protocol}: expected {expected}, observed {observed}")
    for protocol in ("UDP", "TCP"):
        line = find_line(dump_text, [str(rollout.get("src", "")), "Kolibri DNS redirect LAN", protocol])
        observed = state_for_line(line) if line else "missing"
        ok = observed == lan_expected_state
        nat_checks.append(
            {
                "id": rollout.get("id", "lan-rollout"),
                "state": "lan_rollout",
                "protocol": protocol,
                "expected": lan_expected_state,
                "observed": observed,
                "ok": ok,
                "line": line,
            }
        )
        if not ok:
            blockers.append(f"live dump LAN DNS redirect {protocol} state mismatch: expected {lan_expected_state}, observed {observed}")
    checks["dns_redirects"] = nat_checks

    expected_scripts = [
        "kolibri-home-gw-enable-macbook",
        "kolibri-home-gw-disable-macbook",
        "kolibri-home-gw-enable-tv",
        "kolibri-home-gw-disable-tv",
        "kolibri-home-gw-enable-galaxy",
        "kolibri-home-gw-disable-galaxy",
        str(scripts.get("enable_stable_canaries", "kolibri-home-gw-enable-stable-canaries")),
        str(scripts.get("enable_lan", "kolibri-home-gw-enable-lan")),
        str(scripts.get("disable_lan", "kolibri-home-gw-disable-lan")),
        str(scripts.get("disable_all", "kolibri-home-gw-disable-all")),
        str(scripts.get("status", "kolibri-home-gw-status")),
        str(guard.get("script_name", "kolibri-home-gw-guard-macbook")),
    ]
    script_checks = []
    for script in expected_scripts:
        line = find_line(dump_text, [script])
        ok = bool(line)
        script_checks.append({"name": script, "ok": ok, "line": line})
        if not ok:
            blockers.append(f"live dump missing RouterOS script {script}")
    checks["scripts"] = script_checks

    scheduler_name = str(guard.get("scheduler", "kolibri-home-gw-guard-macbook"))
    scheduler_line = find_line(dump_text, [scheduler_name, "interval=30s"])
    scheduler_ok = bool(scheduler_line)
    checks["guard_scheduler"] = {"ok": scheduler_ok, "line": scheduler_line}
    if not scheduler_ok:
        blockers.append(f"live dump missing guard scheduler {scheduler_name} interval=30s")

    return {
        "live_config_verified": not blockers,
        "expected_scope": expected_scope,
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
    }


def manual_commands(mikrotik: dict[str, Any]) -> list[str]:
    status_script = mikrotik.get("scripts", {}).get("status", "kolibri-home-gw-status")
    return [
        f"/system/script/run {status_script}",
        "/routing/table/print detail where name=\"kolibri-home-gw\"",
        "/ip/route/print detail where comment~\"Kolibri Home gateway\" or routing-table=\"kolibri-home-gw\"",
        "/routing/rule/print detail where comment~\"Kolibri Home gateway\"",
        "/ip/firewall/nat/print detail where comment~\"Kolibri DNS redirect\"",
        "/system/script/print detail where name~\"kolibri-home-gw\"",
        "/system/scheduler/print detail where name~\"kolibri-home-gw\"",
        "/ip/dns/print",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--dump", type=Path, default=None, help="RouterOS status/export text to audit")
    parser.add_argument("--router-host", default=None)
    parser.add_argument("--ssh-user", default="admin")
    parser.add_argument("--api-port", type=int, default=8728)
    parser.add_argument("--api-user", default=os.environ.get("KOLIBRI_ROUTEROS_API_USER", DEFAULT_API_USER))
    parser.add_argument("--api-password-env", default="KOLIBRI_ROUTEROS_API_PASSWORD")
    parser.add_argument("--api-password-file", type=Path, default=DEFAULT_API_PASSWORD_FILE)
    parser.add_argument("--bundle-verify", type=Path, default=DEFAULT_BUNDLE_VERIFY)
    parser.add_argument("--timeout", type=int, default=4)
    parser.add_argument("--expected-scope", choices=("pre-rollout", "stable-canaries", "lan"), default="pre-rollout")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--fail-if-unverified", action="store_true")
    args = parser.parse_args()

    manifest_path, manifest = load_manifest(args.manifest)
    mikrotik = manifest.get("mikrotik_gateway", {})
    router_host = args.router_host or str(mikrotik.get("lan_ip", "192.168.88.1"))
    ports = [22, 80, 443, 8291, 8728, 8729]
    tcp_checks = [tcp_check(router_host, port, timeout=float(args.timeout)) for port in ports]
    ssh = ssh_probe(router_host, args.ssh_user, timeout=args.timeout) if any(item["port"] == 22 and item["ok"] for item in tcp_checks) else {}

    api_password: str | None = None
    api_password_source = "none"
    if args.api_password_file and args.api_password_file.exists():
        api_password = args.api_password_file.read_text(encoding="utf-8").strip()
        api_password_source = str(args.api_password_file)
    elif os.environ.get(args.api_password_env):
        api_password = str(os.environ[args.api_password_env])
        api_password_source = args.api_password_env
    api_snapshot = routeros_api_snapshot(
        manifest=manifest,
        host=router_host,
        port=args.api_port,
        user=args.api_user,
        password=api_password,
        timeout=args.timeout,
    )
    api_dump_audit = audit_dump(manifest, api_snapshot["dump_text"], expected_scope=args.expected_scope) if api_snapshot.get("dump_text") else None
    bundle_command: dict[str, Any] | None = None
    bundle_verify: dict[str, Any] = {
        "attempted": False,
        "ok": False,
        "path": str(args.bundle_verify),
        "summary": {},
    }
    if args.bundle_verify and args.bundle_verify.exists():
        bundle_result = run([str(args.bundle_verify)], timeout=max(args.timeout, 10))
        bundle_command = summarize_command(bundle_result)
        bundle_json = parse_json(bundle_result["stdout"])
        bundle_verify = {
            "attempted": True,
            "ok": bool(bundle_json.get("ok")),
            "path": str(args.bundle_verify),
            "command": bundle_command,
            "summary": {
                "live_changes_made": bundle_json.get("live_changes_made"),
                "password_printed": bundle_json.get("checks", {}).get("password_printed"),
                "password_matches_create_command": bundle_json.get("checks", {}).get("password_matches_create_command"),
                "password_file_mode": bundle_json.get("files", {}).get("password_file", {}).get("mode"),
                "create_command_file_mode": bundle_json.get("files", {}).get("create_command_file", {}).get("mode"),
                "blocker_count": len(bundle_json.get("blockers", [])),
            },
        }

    dump_audit = None
    if args.dump:
        dump_audit = audit_dump(
            manifest,
            args.dump.read_text(encoding="utf-8", errors="replace"),
            expected_scope=args.expected_scope,
        )
    elif api_dump_audit:
        dump_audit = api_dump_audit

    access = {
        "router_host": router_host,
        "tcp_checks": tcp_checks,
        "ssh_batch_probe": {
            "attempted": bool(ssh),
            "ok": bool(ssh.get("ok")),
            "exit_code": ssh.get("exit_code"),
            "stdout": ssh.get("stdout", ""),
            "stderr": ssh.get("stderr", ""),
            "duration_ms": ssh.get("duration_ms"),
        },
        "api_probe": {
            "attempted": bool(api_snapshot.get("attempted")),
            "ok": bool(api_snapshot.get("ok")),
            "login_ok": bool(api_snapshot.get("login_ok")),
            "host": api_snapshot.get("host"),
            "port": api_snapshot.get("port"),
            "user": api_snapshot.get("user"),
            "password_source": api_password_source if api_password is not None else "none",
            "error": api_snapshot.get("error", ""),
            "menus": api_snapshot.get("menus", {}),
        },
        "api_bootstrap_bundle": bundle_verify,
        "manual_live_dump_required": dump_audit is None and not bool(ssh.get("ok")) and not bool(api_snapshot.get("ok")),
    }
    result = {
        "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "manifest": str(manifest_path),
        "mode": "read_only_routeros_live_audit",
        "expected_scope": args.expected_scope,
        "access": access,
        "dump_audit": dump_audit,
        "manual_commands": manual_commands(mikrotik),
        "ok": bool(dump_audit and dump_audit.get("live_config_verified")),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    if args.fail_if_unverified and not result["ok"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
