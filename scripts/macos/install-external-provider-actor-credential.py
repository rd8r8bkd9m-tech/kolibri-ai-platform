#!/usr/bin/env python3
"""Dry-run by default installer for the scoped Mac provider credential."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from mac_codex_provider_common import (  # noqa: E402
    LABEL, MacProviderConfigError, MacProviderLayout, atomic_write, json_line,
    validate_identifier,
)

TOKEN_RE = re.compile(r"[A-Za-z0-9._~-]{32,512}\Z")
HOME_AUTH_FILE = "/etc/kolibri/external-provider-actor.sha256"
SSH_OPTIONS = [
    "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
    "-o", "ConnectionAttempts=1", "-o", "StrictHostKeyChecking=yes",
]


def home_ip(path: Path) -> str:
    try:
        ops_dir = SCRIPT_DIR.parents[1] / "ops"
        if str(ops_dir) not in sys.path:
            sys.path.insert(0, str(ops_dir))
        import control_plane_endpoint  # type: ignore
        url = control_plane_endpoint.resolve_home_control_plane_url(manifest_path=path)
        value = urllib.parse.urlsplit(url).hostname or ""
    except Exception as exc:
        raise MacProviderConfigError("mesh_manifest_invalid") from exc
    return value


def read_token(path: Path) -> str:
    try:
        info = path.lstat()
        if (
            stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid()
            or not 32 <= info.st_size <= 513
        ):
            raise MacProviderConfigError("credential_source_unsafe")
        value = path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as exc:
        raise MacProviderConfigError("credential_source_unreadable") from exc
    if not TOKEN_RE.fullmatch(value):
        raise MacProviderConfigError("credential_source_invalid")
    return value


def read_existing_mac_credential(path: Path) -> dict[str, object]:
    try:
        info = path.lstat()
        if (
            stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid()
            or not 64 <= info.st_size <= 2048
        ):
            raise MacProviderConfigError("credential_destination_unsafe")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except MacProviderConfigError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MacProviderConfigError("credential_destination_unsafe") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "credential_id", "node_id", "epoch", "token"}
        or payload.get("schema_version") != "kolibri.external-provider-credential.v1"
        or not TOKEN_RE.fullmatch(str(payload.get("token") or ""))
        or type(payload.get("epoch")) is not int
        or int(payload["epoch"]) < 1
    ):
        raise MacProviderConfigError("credential_destination_invalid")
    validate_identifier(str(payload.get("credential_id") or ""), "credential_id")
    validate_identifier(str(payload.get("node_id") or ""), "node_id")
    return payload


def run(
    command: list[str], *, stdin: bytes | None = None,
    accepted_returncodes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            command, input=stdin, capture_output=True, check=False, timeout=90,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MacProviderConfigError("credential_install_command_failed") from exc
    if completed.returncode not in accepted_returncodes:
        raise MacProviderConfigError("credential_install_command_failed")
    return completed


def remote_apply_script() -> bytes:
    return b"""set -euo pipefail
stage=$1
target=$2
backup=$3
node_id=$4
expected_id=$5
expected_epoch=$6
expected_hash=$7
new_epoch=$8
rotation=$9
install -d -m700 "$backup" "$(dirname "$target")"
curl -fsS --max-time 5 -H 'Content-Type: application/json' \
  -d '{"drain":true}' "http://127.0.0.1:9101/v1/nodes/${node_id}/drain" >/dev/null
diagnostics=$(curl -fsS --max-time 5 http://127.0.0.1:9101/v1/tasks/queue/diagnostics)
test "$(printf '%s' "$diagnostics" | jq -r '.redis')" = PONG
test "$(printf '%s' "$diagnostics" | jq -r '.lease_index_total')" = 0
test "$(printf '%s' "$diagnostics" | jq -r '.expired_leases')" = 0
test "$(printf '%s' "$diagnostics" | jq -r '.stuck_heartbeat_tasks')" = 0
if [ "$rotation" = 1 ]; then
  test -f "$target" && test ! -L "$target"
  test "$(stat -c '%a:%U:%G' "$target")" = '600:root:root'
  test "$(jq -r '.node_id' "$target")" = "$node_id"
  test "$(jq -r '.schema_version' "$target")" = 'kolibri.external-provider-credential.v1'
  test "$(jq -r '.credential_id' "$target")" = "$expected_id"
  test "$(jq -r '.epoch' "$target")" = "$expected_epoch"
  test "$(jq -r '.token_sha256' "$target")" = "$expected_hash"
  test "$new_epoch" -eq $((expected_epoch + 1))
else
  test ! -e "$target"
fi
if [ -e "$target" ]; then cp -a "$target" "$backup/previous"; else : >"$backup/absent"; fi
rollback() {
  set +e
  if [ -e "$backup/previous" ]; then
    cp -a "$backup/previous" "$target"
  elif [ -e "$backup/absent" ]; then
    rm -f "$target"
  fi
  systemctl restart kolibri-factory-control.service
}
trap rollback ERR INT TERM
install -o root -g root -m600 "$stage" "$target"
systemctl restart kolibri-factory-control.service
for _attempt in $(seq 1 20); do
  curl -fsS --max-time 2 http://127.0.0.1:9101/health >/dev/null && break
  sleep 1
done
curl -fsS --max-time 3 http://127.0.0.1:9101/health >/dev/null
actors=$(curl -fsS --max-time 3 'http://127.0.0.1:9101/v1/runtime/provider-actors?runner=codex&limit=1')
new_id=$(jq -r '.credential_id' "$target")
printf '%s' "$actors" | jq -e --arg node "$node_id" --arg credential "$new_id" --argjson epoch "$new_epoch" \
  '.auth_configured == true and .auth_binding.bound_node_id == $node and .auth_binding.credential_id == $credential and .auth_binding.epoch == $epoch' >/dev/null
rm -f "$stage"
rmdir "$(dirname "$stage")" 2>/dev/null || true
trap - ERR INT TERM
"""


def remote_verify_actor_script() -> bytes:
    return b"""set -euo pipefail
node_id=$1
credential_id=$2
epoch=$3
marker_bound=0
for _attempt in $(seq 1 30); do
  node=$(curl -fsS --max-time 3 "http://127.0.0.1:9101/v1/nodes/${node_id}?scope=all") || true
  if printf '%s' "$node" | jq -e --arg credential "$credential_id" --argjson epoch "$epoch" \
    '.external_provider_auth.credential_id == $credential and .external_provider_auth.epoch == $epoch' >/dev/null; then
    marker_bound=1
    if printf '%s' "$node" | jq -e \
      '.freshness == "fresh" and .runner_readiness.codex.status == "available" and .runner_readiness.codex.login_status == "authenticated" and .runner_readiness.codex.probe.status == "passed"' >/dev/null; then
      exit 0
    fi
  fi
  sleep 1
done
if [ "$marker_bound" = 1 ]; then exit 42; fi
exit 1
"""


def remote_marker_probe_script() -> bytes:
    return b"""set -euo pipefail
node_id=$1
credential_id=$2
epoch=$3
node=$(curl -fsS --max-time 3 "http://127.0.0.1:9101/v1/nodes/${node_id}?scope=all")
printf '%s' "$node" | jq -e --arg credential "$credential_id" --argjson epoch "$epoch" \
  '.external_provider_auth.credential_id == $credential and .external_provider_auth.epoch == $epoch' >/dev/null
"""


def remote_rollback_script() -> bytes:
    return b"""set -euo pipefail
target=$1
backup=$2
if [ -e "$backup/previous" ]; then cp -a "$backup/previous" "$target"; elif [ -e "$backup/absent" ]; then rm -f "$target"; fi
systemctl restart kolibri-factory-control.service
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh-manifest", required=True, type=Path)
    parser.add_argument("--node-id", default="mac-codex-provider")
    parser.add_argument("--credential-id", default="mac-codex-provider-v1")
    parser.add_argument("--epoch", type=int, default=1)
    parser.add_argument("--credential-source", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rotate", action="store_true")
    parser.add_argument("--reload-launch-agent", action="store_true")
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        raise MacProviderConfigError("credential_installer_must_run_as_current_user")
    node_id = validate_identifier(args.node_id, "node_id")
    credential_id = validate_identifier(args.credential_id, "credential_id")
    if args.epoch < 1:
        raise MacProviderConfigError("credential_epoch_invalid")
    if args.reload_launch_agent and not args.rotate:
        raise MacProviderConfigError("initial_install_requires_separate_launch_agent_load")
    if args.apply and args.rotate and not args.reload_launch_agent:
        raise MacProviderConfigError("rotation_requires_launch_agent_reload")
    resolved_home = home_ip(args.mesh_manifest.expanduser())
    layout = MacProviderLayout.from_home(Path.home())
    destination_exists = layout.provider_credential.exists() or layout.provider_credential.is_symlink()
    existing = read_existing_mac_credential(layout.provider_credential) if destination_exists else None
    if args.apply and destination_exists and not args.rotate:
        raise MacProviderConfigError("credential_exists_rotate_required")
    if args.rotate and existing is None:
        raise MacProviderConfigError("credential_rotation_source_missing")
    if existing is not None:
        if existing["node_id"] != node_id:
            raise MacProviderConfigError("credential_rotation_node_mismatch")
        if args.rotate and args.epoch != int(existing["epoch"]) + 1:
            raise MacProviderConfigError("credential_epoch_not_increasing")
    if args.credential_source:
        read_token(args.credential_source.expanduser())
    plan = {
        "status": "validated", "apply": args.apply, "rotate": args.rotate,
        "node_id": node_id, "credential_id": credential_id, "epoch": args.epoch,
        "credential_source": "existing_private_file" if args.credential_source else "generate_on_apply",
        "mac_destination": str(layout.provider_credential),
        "home_destination": HOME_AUTH_FILE, "home_source": "replicated_mesh_manifest",
        "secrets_returned": False,
    }
    if not args.apply:
        print(json_line(plan))
        return 0

    token = read_token(args.credential_source.expanduser()) if args.credential_source else secrets.token_urlsafe(48)
    if not TOKEN_RE.fullmatch(token):
        raise MacProviderConfigError("generated_credential_invalid")
    previous = layout.provider_credential.read_bytes() if destination_exists else None
    record = {
        "schema_version": "kolibri.external-provider-credential.v1",
        "credential_id": credential_id, "node_id": node_id, "epoch": args.epoch,
        "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
    }
    mac_record = {
        "schema_version": record["schema_version"],
        "credential_id": credential_id,
        "node_id": node_id,
        "epoch": args.epoch,
        "token": token,
    }
    run_id = f"external-provider-auth-{int(time.time())}-{os.getpid()}"
    remote_stage_dir = f"/run/kolibri/{run_id}"
    remote_stage = f"{remote_stage_dir}/credential.json"
    remote_backup = f"/var/backups/kolibri/{run_id}"
    descriptor, temp_name = tempfile.mkstemp(prefix="kolibri-provider-hash-")
    temp_hash = Path(temp_name)
    marker_bound_readiness_pending = False
    home_switched = False
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write((json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode())
        os.chmod(temp_hash, 0o600)
        atomic_write(
            layout.provider_credential,
            (json.dumps(mac_record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"),
            0o600,
        )
        run(["ssh", *SSH_OPTIONS, f"root@{resolved_home}", "mkdir", "-m700", remote_stage_dir])
        run(["scp", "-q", *SSH_OPTIONS, str(temp_hash), f"root@{resolved_home}:{remote_stage}"])
        run([
            "ssh", *SSH_OPTIONS, f"root@{resolved_home}", "/bin/bash", "-s", "--",
            remote_stage, HOME_AUTH_FILE, remote_backup, node_id,
            str(existing["credential_id"]) if existing else "-",
            str(existing["epoch"]) if existing else "0",
            hashlib.sha256(str(existing["token"]).encode("utf-8")).hexdigest() if existing else "-",
            str(args.epoch), "1" if args.rotate else "0",
        ], stdin=remote_apply_script())
        home_switched = True
        if args.reload_launch_agent:
            run(["/bin/launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{LABEL}"])
            verification = run([
                "ssh", *SSH_OPTIONS, f"root@{resolved_home}", "/bin/bash", "-s", "--",
                node_id, credential_id, str(args.epoch),
            ], stdin=remote_verify_actor_script(), accepted_returncodes=(0, 42))
            marker_bound_readiness_pending = bool(
                verification is not None and verification.returncode == 42
            )
    except Exception as original_error:
        marker_committed = False
        if home_switched and args.reload_launch_agent:
            try:
                probe = run([
                    "ssh", *SSH_OPTIONS, f"root@{resolved_home}", "/bin/bash", "-s", "--",
                    node_id, credential_id, str(args.epoch),
                ], stdin=remote_marker_probe_script(), accepted_returncodes=(0, 1))
                marker_committed = bool(probe is not None and probe.returncode == 0)
            except MacProviderConfigError:
                marker_committed = False
        if args.rotate and home_switched:
            raise MacProviderConfigError(
                "credential_rotation_committed_actor_drained_recovery_required"
                if marker_committed else
                "credential_rotation_switched_actor_drained_recovery_required"
            ) from original_error
        if previous is None:
            layout.provider_credential.unlink(missing_ok=True)
        else:
            atomic_write(layout.provider_credential, previous, 0o600)
        try:
            run([
                "ssh", *SSH_OPTIONS, f"root@{resolved_home}", "/bin/bash", "-s", "--",
                HOME_AUTH_FILE, remote_backup,
            ], stdin=remote_rollback_script())
        except MacProviderConfigError:
            pass
        raise
    finally:
        temp_hash.unlink(missing_ok=True)
    plan["status"] = (
        "rotated_marker_bound_readiness_pending"
        if marker_bound_readiness_pending else
        "rotated_actor_drained"
        if args.rotate else
        "credential_installed_actor_drained"
    )
    plan["next_action"] = (
        "verify marker/readiness, then explicitly undrain actor"
        if args.rotate else
        "install/load the Mac provider runtime, verify marker/readiness, then explicitly undrain actor"
    )
    print(json_line(plan))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MacProviderConfigError as exc:
        print(json_line({"status": "failed", "error": exc.code, "secrets_returned": False}))
        raise SystemExit(1)
