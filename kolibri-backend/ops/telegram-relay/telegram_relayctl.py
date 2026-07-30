#!/usr/bin/env python3
"""Validate, install, or roll back the stateless Telegram relay.

The default ``prepare`` command is read-only apart from its explicit output
file. ``install`` and ``rollback`` are protected operations: they require root
and an owner approval identifier, keep a checksum backup, run ``nginx -t``,
reload nginx, and restore the previous configuration automatically on failure.

This tool never reads the Bot API token or webhook secret.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


PUBLIC_IPV4 = "78.17.4.108"
DOMAIN = "kolibriai.ru"
MESH_NETWORK = ipaddress.ip_network("10.99.0.0/16")
OFFICIAL_TELEGRAM_CIDRS = ("149.154.160.0/20", "91.108.4.0/22")
DEFAULT_TARGET = Path("/etc/nginx/conf.d/kolibriai-telegram-webhook-relay.conf")
DEFAULT_BACKUP_ROOT = Path("/var/lib/kolibri/release-backups/telegram-relay")
TEMPLATE = Path(__file__).with_name("kolibriai-telegram-webhook-relay.nginx.conf.template")


class RelayError(RuntimeError):
    pass


@dataclass(frozen=True)
class RelayInputs:
    home_mesh_ip: str
    relay_mesh_ip: str
    fullchain_path: str
    private_key_path: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mesh_address(value: str, label: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise RelayError(f"{label} is not an IP address") from exc
    if address.version != 4 or address not in MESH_NETWORK:
        raise RelayError(f"{label} must be an IPv4 address in {MESH_NETWORK}")
    return str(address)


def validate_inputs(inputs: RelayInputs, *, require_files: bool) -> RelayInputs:
    home_mesh_ip = _mesh_address(inputs.home_mesh_ip, "home mesh address")
    relay_mesh_ip = _mesh_address(inputs.relay_mesh_ip, "relay mesh address")
    if home_mesh_ip == relay_mesh_ip:
        raise RelayError("home and relay mesh addresses must be different")

    fullchain = Path(inputs.fullchain_path)
    private_key = Path(inputs.private_key_path)
    for path, label in ((fullchain, "full chain"), (private_key, "private key")):
        if not path.is_absolute():
            raise RelayError(f"{label} path must be absolute")
        if require_files and not path.is_file():
            raise RelayError(f"{label} file does not exist")

    return RelayInputs(
        home_mesh_ip=home_mesh_ip,
        relay_mesh_ip=relay_mesh_ip,
        fullchain_path=str(fullchain),
        private_key_path=str(private_key),
    )


def render_config(inputs: RelayInputs, template_text: str | None = None) -> str:
    inputs = validate_inputs(inputs, require_files=False)
    source = TEMPLATE.read_text(encoding="utf-8") if template_text is None else template_text
    rendered = (
        source.replace("__HOME_MESH_IP__", inputs.home_mesh_ip)
        .replace("__FULLCHAIN_PATH__", inputs.fullchain_path)
        .replace("__PRIVKEY_PATH__", inputs.private_key_path)
    )
    if "__" in rendered:
        raise RelayError("unresolved relay template placeholder")
    return rendered


def validate_contract(rendered: str) -> None:
    exact_location = "location = /api/v1/telegram/webhook"
    if rendered.count(exact_location) != 1:
        raise RelayError("candidate must expose exactly one exact webhook location")
    if rendered.count("proxy_pass ") != 1:
        raise RelayError("candidate must have exactly one upstream proxy route")
    for cidr in OFFICIAL_TELEGRAM_CIDRS:
        if f"allow {cidr};" not in rendered:
            raise RelayError(f"candidate is missing official Telegram CIDR {cidr}")
    required = (
        "listen 78.17.4.108:443 ssl;",
        "deny all;",
        "limit_except POST",
        "proxy_ssl_server_name on;",
        "proxy_ssl_name kolibriai.ru;",
        "proxy_ssl_verify on;",
        "proxy_set_header Host kolibriai.ru;",
        "proxy_set_header X-Telegram-Bot-Api-Secret-Token $http_x_telegram_bot_api_secret_token;",
        "proxy_set_header X-Forwarded-For $remote_addr;",
        "location / {",
        "return 404;",
    )
    missing = [item for item in required if item not in rendered]
    if missing:
        raise RelayError("candidate is missing required directives: " + ", ".join(missing))
    lowered = rendered.lower()
    if "bot_token" in lowered or "telegram_bot_token" in lowered:
        raise RelayError("candidate must not contain a Bot API token setting")


def _run(command: list[str], *, input_text: str | None = None, timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def validate_certificate(inputs: RelayInputs) -> None:
    expiry = _run(["openssl", "x509", "-in", inputs.fullchain_path, "-noout", "-checkend", "3600"])
    if expiry.returncode != 0:
        raise RelayError("TLS certificate is missing, invalid, or expires within one hour")
    names = _run(["openssl", "x509", "-in", inputs.fullchain_path, "-noout", "-ext", "subjectAltName"])
    if names.returncode != 0 or f"DNS:{DOMAIN}" not in names.stdout:
        raise RelayError(f"TLS certificate does not contain DNS:{DOMAIN}")

    cert_key = _run(["openssl", "x509", "-in", inputs.fullchain_path, "-pubkey", "-noout"])
    private_key = _run(["openssl", "pkey", "-in", inputs.private_key_path, "-pubout"])
    if cert_key.returncode != 0 or private_key.returncode != 0:
        raise RelayError("certificate or private key public-key extraction failed")
    if cert_key.stdout.strip() != private_key.stdout.strip():
        raise RelayError("TLS certificate and private key do not match")


def validate_home_tls(home_mesh_ip: str) -> None:
    probe = _run(
        [
            "openssl", "s_client", "-brief", "-verify_return_error",
            "-verify_hostname", DOMAIN, "-servername", DOMAIN,
            "-connect", f"{home_mesh_ip}:443",
            "-CAfile", "/etc/ssl/certs/ca-certificates.crt",
        ],
        input_text="",
        timeout=10,
    )
    if probe.returncode != 0:
        raise RelayError("Home mesh TLS/SNI validation failed")


def nginx_test(rendered: str) -> None:
    with tempfile.TemporaryDirectory(prefix="kolibri-telegram-relay-") as directory:
        root = Path(directory)
        candidate = root / "candidate.conf"
        main = root / "nginx.conf"
        candidate.write_text(rendered, encoding="utf-8")
        main.write_text(
            "worker_processes 1;\n"
            f"pid {root / 'nginx.pid'};\n"
            "error_log stderr warn;\n"
            "events { worker_connections 16; }\n"
            "http {\n"
            f"  include {candidate};\n"
            "}\n",
            encoding="utf-8",
        )
        result = _run(["nginx", "-t", "-c", str(main), "-p", "/"])
        if result.returncode != 0:
            raise RelayError("nginx candidate validation failed: " + result.stderr.strip())


def write_atomic(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(content, encoding="utf-8")
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def prepare(inputs: RelayInputs, output: Path, *, live_checks: bool) -> dict[str, object]:
    inputs = validate_inputs(inputs, require_files=live_checks)
    rendered = render_config(inputs)
    validate_contract(rendered)
    if live_checks:
        validate_certificate(inputs)
        validate_home_tls(inputs.home_mesh_ip)
        nginx_test(rendered)
    write_atomic(output, rendered)
    evidence_path = output.with_suffix(output.suffix + ".evidence.json")
    payload = {
        "status": "validated" if live_checks else "rendered",
        "candidate": str(output),
        "candidate_sha256": sha256_file(output),
        "public_ipv4": PUBLIC_IPV4,
        "domain": DOMAIN,
        "home_mesh_ip": inputs.home_mesh_ip,
        "relay_mesh_cidr_for_home": f"{inputs.relay_mesh_ip}/32",
        "official_telegram_cidrs": list(OFFICIAL_TELEGRAM_CIDRS),
        "live_checks": live_checks,
    }
    write_atomic(evidence_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return {**payload, "evidence": str(evidence_path)}


def _require_protected_action(approval_id: str) -> None:
    if os.geteuid() != 0:
        raise RelayError("protected relay mutation requires root")
    if not approval_id.strip():
        raise RelayError("protected relay mutation requires an owner approval identifier")


def _reload_nginx() -> None:
    syntax = _run(["nginx", "-t"])
    if syntax.returncode != 0:
        raise RelayError("system nginx validation failed: " + syntax.stderr.strip())
    syntax_output = f"{syntax.stdout}\n{syntax.stderr}".lower()
    if "conflicting server name" in syntax_output or "duplicate listen" in syntax_output:
        raise RelayError("system nginx validation found a conflicting virtual host")
    reload_result = _run(["systemctl", "reload", "nginx"])
    if reload_result.returncode != 0:
        raise RelayError("nginx reload failed: " + reload_result.stderr.strip())


def install(
    candidate: Path,
    evidence_path: Path,
    target: Path,
    backup_root: Path,
    approval_id: str,
) -> dict[str, object]:
    _require_protected_action(approval_id)
    if not candidate.is_file():
        raise RelayError("candidate file does not exist")
    if not evidence_path.is_file():
        raise RelayError("candidate validation evidence does not exist")
    rendered = candidate.read_text(encoding="utf-8")
    validate_contract(rendered)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if evidence.get("status") != "validated" or evidence.get("live_checks") is not True:
        raise RelayError("candidate has not passed live certificate, Home TLS, and nginx checks")
    if evidence.get("candidate_sha256") != sha256_file(candidate):
        raise RelayError("candidate changed after validation")
    if evidence.get("public_ipv4") != PUBLIC_IPV4 or evidence.get("domain") != DOMAIN:
        raise RelayError("candidate validation evidence targets a different relay identity")
    if evidence.get("official_telegram_cidrs") != list(OFFICIAL_TELEGRAM_CIDRS):
        raise RelayError("candidate validation evidence uses a different Telegram allowlist")
    nginx_test(rendered)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_root / stamp
    backup.mkdir(parents=True, mode=0o700, exist_ok=False)
    previous_exists = target.is_file()
    previous_sha256 = None
    if previous_exists:
        previous = backup / "previous.conf"
        shutil.copy2(target, previous)
        previous_sha256 = sha256_file(previous)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "approval_id": approval_id,
        "target": str(target),
        "previous_exists": previous_exists,
        "previous_sha256": previous_sha256,
        "candidate_sha256": sha256_file(candidate),
        "validation_evidence_sha256": sha256_file(evidence_path),
    }
    write_atomic(backup / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n", 0o600)

    try:
        write_atomic(target, rendered)
        _reload_nginx()
    except Exception:
        if previous_exists:
            write_atomic(target, (backup / "previous.conf").read_text(encoding="utf-8"))
        else:
            target.unlink(missing_ok=True)
        _reload_nginx()
        raise
    return {"status": "installed", "backup": str(backup), **manifest}


def rollback(target: Path, backup: Path, approval_id: str) -> dict[str, object]:
    _require_protected_action(approval_id)
    manifest_path = backup / "manifest.json"
    if not manifest_path.is_file():
        raise RelayError("rollback manifest does not exist")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("target") != str(target):
        raise RelayError("rollback target does not match the backup manifest")
    if manifest.get("previous_exists"):
        previous = backup / "previous.conf"
        if not previous.is_file() or sha256_file(previous) != manifest.get("previous_sha256"):
            raise RelayError("rollback backup checksum mismatch")
        write_atomic(target, previous.read_text(encoding="utf-8"))
    else:
        target.unlink(missing_ok=True)
    _reload_nginx()
    return {"status": "rolled_back", "backup": str(backup), "target": str(target)}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subcommands = result.add_subparsers(dest="command", required=True)

    prepare_parser = subcommands.add_parser("prepare", help="render and optionally validate without installing")
    prepare_parser.add_argument("--home-mesh-ip", required=True)
    prepare_parser.add_argument("--relay-mesh-ip", required=True)
    prepare_parser.add_argument("--fullchain", required=True)
    prepare_parser.add_argument("--private-key", required=True)
    prepare_parser.add_argument("--output", required=True, type=Path)
    prepare_parser.add_argument("--live-checks", action="store_true")

    install_parser = subcommands.add_parser("install", help="install a validated candidate with rollback")
    install_parser.add_argument("--candidate", required=True, type=Path)
    install_parser.add_argument("--evidence", required=True, type=Path)
    install_parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    install_parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    install_parser.add_argument("--approval-id", required=True)

    rollback_parser = subcommands.add_parser("rollback", help="restore one exact install backup")
    rollback_parser.add_argument("--backup", required=True, type=Path)
    rollback_parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    rollback_parser.add_argument("--approval-id", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "prepare":
            payload = prepare(
                RelayInputs(args.home_mesh_ip, args.relay_mesh_ip, args.fullchain, args.private_key),
                args.output,
                live_checks=args.live_checks,
            )
        elif args.command == "install":
            payload = install(
                args.candidate,
                args.evidence,
                args.target,
                args.backup_root,
                args.approval_id,
            )
        else:
            payload = rollback(args.target, args.backup, args.approval_id)
    except (RelayError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
