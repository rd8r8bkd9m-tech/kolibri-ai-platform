#!/usr/bin/env python3
"""Validate or install the current-user Kolibri Codex provider LaunchAgent."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import ModuleType


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from mac_codex_provider_common import (  # noqa: E402
    LABEL,
    MAC_CODEX_READINESS_REFRESH_SECONDS,
    MANAGED_MARKER,
    MacProviderConfigError,
    MacProviderLayout,
    atomic_write,
    ensure_directory,
    json_line,
    launchctl,
    render_launch_agent,
    require_executable,
    require_regular_file,
    runtime_digest,
    source_files,
    validate_identifier,
)


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise MacProviderConfigError("runtime_module_unloadable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_runner_access(source_root: Path, manifest_path: Path) -> dict[str, object]:
    runner_access = load_module(source_root / "ops" / "runner_access.py", "mac_provider_runner_access")
    try:
        manifest = runner_access.load_runner_access_manifest(manifest_path)
    except Exception as exc:
        raise MacProviderConfigError("runner_access_manifest_invalid") from exc
    codex = manifest["runners"]["codex"]
    mimo = manifest["runners"]["mimo"]
    if codex.get("mode") != "local_service_account" or codex.get("authorization_flow") != "browser_device":
        raise MacProviderConfigError("mac_codex_local_device_flow_required")
    if mimo.get("mode") != "disabled":
        raise MacProviderConfigError("mac_provider_mimo_must_be_disabled")
    return manifest


def resolve_dynamic_home(source_root: Path, mesh_manifest: Path) -> str:
    endpoint = load_module(
        source_root / "ops" / "control_plane_endpoint.py",
        "mac_provider_control_plane_endpoint",
    )
    try:
        return endpoint.resolve_home_control_plane_url(manifest_path=mesh_manifest)
    except Exception as exc:
        raise MacProviderConfigError("dynamic_home_resolution_failed") from exc


def current_user_codex_ready(codex_bin: Path, home: Path, execution_path: str) -> bool:
    environment = {
        "HOME": str(home),
        "PATH": execution_path,
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
    }
    try:
        completed = subprocess.run(
            [str(codex_bin), "login", "status"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    # Output is intentionally discarded: it is not installation evidence and
    # must never be copied into logs or the LaunchAgent plist.
    return completed.returncode == 0 and "logged in" in f"{completed.stdout}\n{completed.stderr}".lower()


def execution_path(codex_bin: Path, python_bin: Path) -> str:
    directories = [
        str(codex_bin.parent),
        str(python_bin.parent),
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ]
    return ":".join(dict.fromkeys(directories))


def install_runtime(layout: MacProviderLayout, files: list[tuple[Path, str]], digest: str) -> Path:
    ensure_directory(layout.releases.parent)
    ensure_directory(layout.releases)
    release = layout.releases / digest
    if release.exists():
        marker = release / MANAGED_MARKER
        if (
            release.is_symlink()
            or not release.is_dir()
            or not marker.is_file()
            or marker.is_symlink()
            or marker.read_text(encoding="utf-8").strip() != LABEL
        ):
            raise MacProviderConfigError("runtime_release_not_managed")
        for source, installed_name in files:
            installed = release / installed_name
            if (
                not installed.is_file()
                or installed.is_symlink()
                or installed.read_bytes() != source.read_bytes()
                or stat.S_IMODE(installed.stat().st_mode) != 0o500
            ):
                raise MacProviderConfigError("runtime_release_digest_mismatch")
        return release

    staging = Path(tempfile.mkdtemp(prefix=f".{digest}.", dir=layout.releases))
    try:
        os.chmod(staging, 0o700)
        for source, installed_name in files:
            target = staging / installed_name
            shutil.copyfile(source, target)
            os.chmod(target, 0o500)
        (staging / MANAGED_MARKER).write_text(f"{LABEL}\n", encoding="utf-8")
        os.chmod(staging / MANAGED_MARKER, 0o400)
        os.replace(staging, release)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return release


def safe_existing_plist(path: Path) -> bytes | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise MacProviderConfigError("existing_launch_agent_unsafe")
    payload = path.read_bytes()
    try:
        parsed = plistlib.loads(payload)
    except plistlib.InvalidFileException as exc:
        raise MacProviderConfigError("existing_launch_agent_invalid") from exc
    if (
        parsed.get("Label") != LABEL
        or parsed.get("KolibriManagedContract") != "kolibri.mac-codex-provider.launchagent.v1"
    ):
        raise MacProviderConfigError("existing_launch_agent_not_managed")
    return payload


def bootstrap_launch_agent(
    domain: str,
    service: str,
    plist: Path,
    *,
    attempts: int = 4,
) -> subprocess.CompletedProcess[str]:
    """Bound launchd's asynchronous bootout/bootstrap transition.

    ``launchctl bootout`` can return before launchd has fully released the
    label.  A single immediate bootstrap then fails even though the plist is
    valid.  Retry the exact managed label only, with a short bounded backoff.
    """

    for attempt in range(max(1, attempts)):
        try:
            return launchctl(["bootstrap", domain, str(plist)])
        except MacProviderConfigError:
            if attempt + 1 >= max(1, attempts):
                raise
            launchctl(["bootout", service], tolerate_missing=True)
            time.sleep(0.5 * (attempt + 1))
    raise MacProviderConfigError("launchctl_operation_failed")  # pragma: no cover


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh-manifest", type=Path, required=True)
    parser.add_argument("--runner-access", type=Path)
    parser.add_argument("--source-root", type=Path, default=SCRIPT_DIR.parents[1])
    parser.add_argument("--python-bin", type=Path, default=Path(shutil.which("python3") or ""))
    parser.add_argument("--codex-bin", type=Path, default=Path(shutil.which("codex") or ""))
    parser.add_argument("--node-id", default="mac-codex-provider")
    parser.add_argument("--agent-id", default="mac-codex-provider")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--load", action="store_true", help="bootstrap the LaunchAgent after installation")
    args = parser.parse_args(argv)

    if args.load and not args.apply:
        raise MacProviderConfigError("load_requires_apply")
    if os.geteuid() == 0:
        raise MacProviderConfigError("launch_agent_must_install_as_current_user")

    source_root = args.source_root.expanduser().resolve()
    layout = MacProviderLayout.from_home(Path.home())
    node_id = validate_identifier(args.node_id, "node_id")
    agent_id = validate_identifier(args.agent_id, "agent_id")
    mesh_manifest = require_regular_file(args.mesh_manifest, "mesh_manifest_invalid")
    runner_access_source = require_regular_file(
        args.runner_access or source_root / "ops" / "launchd" / "mac-codex-provider.runner-access.json",
        "runner_access_manifest_invalid",
    )
    python_bin = require_executable(args.python_bin, "python_executable_invalid")
    codex_bin = require_executable(args.codex_bin, "codex_executable_invalid")
    template = require_regular_file(
        source_root / "ops" / "launchd" / f"{LABEL}.plist.in",
        "launch_agent_template_missing",
    )
    files = source_files(source_root)
    digest = runtime_digest(files)
    runtime_dir = layout.releases / digest
    validate_runner_access(source_root, runner_access_source)
    control_url = resolve_dynamic_home(source_root, mesh_manifest)
    path_value = execution_path(codex_bin, python_bin)
    if not current_user_codex_ready(codex_bin, layout.home, path_value):
        raise MacProviderConfigError("current_user_codex_session_unavailable")

    labels = json.dumps({
        "physical_node_id": node_id,
        "provider": "codex",
        "runtime": "macos_launchagent",
    }, sort_keys=True, separators=(",", ":"))
    replacements = {
        "PYTHON_BIN": str(python_bin),
        "RUNTIME_DIR": str(runtime_dir),
        "SANITIZED_LOG": str(layout.sanitized_log),
        "BOOTSTRAP_LOG": str(layout.bootstrap_log),
        "NODE_ID": node_id,
        "AGENT_ID": agent_id,
        "WORK_ROOT": str(layout.work),
        "ARTIFACT_ROOT": str(layout.artifacts),
        "USER_HOME": str(layout.home),
        "EXEC_PATH": path_value,
        "MESH_MANIFEST": str(mesh_manifest),
        "RUNNER_ACCESS": str(layout.runner_access),
        "PROVIDER_CREDENTIAL": str(layout.provider_credential),
        "NODE_LABELS_JSON": labels,
    }
    plist_bytes, _payload = render_launch_agent(template, replacements)
    plan = {
        "status": "validated",
        "apply": args.apply,
        "load": args.load,
        "label": LABEL,
        "node_id": node_id,
        "control_plane_source": "replicated_mesh_manifest",
        "control_plane_url": control_url,
        "runtime_digest": f"sha256:{digest}",
        "launch_agent": str(layout.launch_agent),
        "codex_readiness_refresh_seconds": MAC_CODEX_READINESS_REFRESH_SECONDS,
    }
    if not args.apply:
        print(json_line(plan))
        return 0

    credential = require_regular_file(
        layout.provider_credential,
        "external_provider_actor_credential_missing",
    )
    credential_mode = stat.S_IMODE(credential.stat().st_mode)
    if credential_mode != 0o600 or credential.stat().st_uid != os.getuid():
        raise MacProviderConfigError("external_provider_actor_credential_unsafe")

    ensure_directory(layout.base)
    ensure_directory(layout.config)
    ensure_directory(layout.work)
    ensure_directory(layout.artifacts)
    ensure_directory(layout.logs)
    ensure_directory(layout.launch_agent.parent, change_mode=False)
    for log_path in (layout.sanitized_log, layout.bootstrap_log):
        log_path.touch(mode=0o600, exist_ok=True)
        os.chmod(log_path, 0o600)

    installed_runtime = install_runtime(layout, files, digest)
    if installed_runtime != runtime_dir:
        raise MacProviderConfigError("runtime_install_path_mismatch")
    atomic_write(layout.runner_access, runner_access_source.read_bytes(), 0o600)
    previous_plist = safe_existing_plist(layout.launch_agent)
    atomic_write(layout.launch_agent, plist_bytes, 0o600)

    if args.load:
        domain = f"gui/{os.getuid()}"
        service = f"{domain}/{LABEL}"
        launchctl(["bootout", service], tolerate_missing=True)
        try:
            bootstrap_launch_agent(domain, service, layout.launch_agent)
            launchctl(["kickstart", "-k", service])
        except MacProviderConfigError:
            launchctl(["bootout", service], tolerate_missing=True)
            if previous_plist is None:
                layout.launch_agent.unlink(missing_ok=True)
            else:
                atomic_write(layout.launch_agent, previous_plist, 0o600)
                try:
                    bootstrap_launch_agent(domain, service, layout.launch_agent)
                except MacProviderConfigError:
                    pass
            raise

    plan["status"] = "installed_and_loaded" if args.load else "installed_not_loaded"
    print(json_line(plan))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MacProviderConfigError as exc:
        print(json_line({"status": "failed", "error": exc.code}))
        raise SystemExit(1)
