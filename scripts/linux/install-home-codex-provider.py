#!/usr/bin/env python3
"""Validate or install the Home current-user Codex provider actor.

The installer is dry-run by default. It never reads or copies Codex browser
credentials: Codex CLI resolves the already-authorized current user's session
in place. Starting the managed user service is a separate explicit action.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping
from urllib.parse import urlsplit


SERVICE_NAME = "kolibri-home-codex-provider.service"
MANAGED_CONTRACT = "kolibri.home-codex-provider.systemd-user.v1"
MANAGED_MARKER = ".managed-by-kolibri-home-codex-provider"
READINESS_REFRESH_SECONDS = 240
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
TOKEN_RE = re.compile(r"[A-Za-z0-9._~-]{32,512}\Z")
RUNTIME_SOURCE_FILES = (
    ("ops/agent_host.py", "agent_host.py"),
    ("ops/control_plane_endpoint.py", "control_plane_endpoint.py"),
    ("ops/fleet_membership.py", "fleet_membership.py"),
    ("ops/runner_access.py", "runner_access.py"),
    ("ops/release_authority.py", "release_authority.py"),
    ("ops/release_helper.py", "release_helper.py"),
    ("ops/release_installer.py", "release_installer.py"),
    ("ops/macos/mac_codex_provider_launcher.py", "provider_actor_launcher.py"),
)


class HomeProviderConfigError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class HomeProviderLayout:
    home: Path
    base: Path
    releases: Path
    config: Path
    work: Path
    artifacts: Path
    logs: Path
    runner_access: Path
    provider_credential: Path
    sanitized_log: Path
    bootstrap_log: Path
    service_unit: Path

    @classmethod
    def from_home(cls, home: str | Path) -> "HomeProviderLayout":
        owner_home = Path(home).expanduser().resolve()
        base = owner_home / ".local" / "share" / "kolibri" / "home-codex-provider"
        logs = base / "logs"
        return cls(
            home=owner_home,
            base=base,
            releases=base / "runtime" / "releases",
            config=base / "config",
            work=base / "worktrees",
            artifacts=base / "artifacts",
            logs=logs,
            runner_access=base / "config" / "runner-access.json",
            provider_credential=base / "config" / "external-provider-actor.credential",
            sanitized_log=logs / "agent-host.log",
            bootstrap_log=logs / "systemd-bootstrap.log",
            service_unit=owner_home / ".config" / "systemd" / "user" / SERVICE_NAME,
        )


def json_line(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_identifier(value: str, field: str) -> str:
    normalized = str(value or "").strip()
    if not SAFE_ID.fullmatch(normalized):
        raise HomeProviderConfigError(f"invalid_{field}")
    return normalized


def require_regular_file(path: str | Path, code: str) -> Path:
    candidate = Path(path).expanduser()
    try:
        info = candidate.lstat()
    except OSError as exc:
        raise HomeProviderConfigError(code) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise HomeProviderConfigError(code)
    return candidate.resolve()


def require_executable(path: str | Path, code: str) -> Path:
    candidate = Path(path).expanduser().absolute()
    try:
        resolved = candidate.resolve(strict=True)
        info = resolved.stat()
    except OSError as exc:
        raise HomeProviderConfigError(code) from exc
    if not stat.S_ISREG(info.st_mode) or not os.access(resolved, os.X_OK):
        raise HomeProviderConfigError(code)
    return candidate


def ensure_directory(path: Path, mode: int = 0o700, *, change_mode: bool = True) -> Path:
    try:
        info = path.lstat()
    except FileNotFoundError:
        path.mkdir(parents=True, mode=mode)
        info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise HomeProviderConfigError("managed_directory_unsafe")
    if change_mode:
        os.chmod(path, mode)
    return path


def atomic_write(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise HomeProviderConfigError("runtime_module_unloadable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_runner_access(source_root: Path, manifest_path: Path) -> dict[str, Any]:
    module = load_module(source_root / "ops" / "runner_access.py", "home_provider_runner_access")
    try:
        manifest = module.load_runner_access_manifest(manifest_path)
    except Exception as exc:
        raise HomeProviderConfigError("runner_access_manifest_invalid") from exc
    codex = manifest["runners"]["codex"]
    mimo = manifest["runners"]["mimo"]
    if (
        codex.get("mode") != "local_service_account"
        or codex.get("authorization_flow") != "browser_device"
        or codex.get("identity_ref") != "service-user://home-owner"
    ):
        raise HomeProviderConfigError("home_codex_local_device_flow_required")
    if mimo.get("mode") != "disabled":
        raise HomeProviderConfigError("home_provider_mimo_must_be_disabled")
    return manifest


def assert_local_home(source_root: Path, manifest_path: Path, interface: str) -> str:
    module = load_module(
        source_root / "ops" / "control_plane_endpoint.py",
        "home_provider_control_plane_endpoint",
    )
    try:
        return module.assert_local_home_control_plane(
            manifest_path=manifest_path,
            interface=interface,
        )
    except Exception as exc:
        raise HomeProviderConfigError("home_provider_must_install_on_home") from exc


def validate_proxy_url(value: str | None) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    parsed = urlsplit(normalized)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.port is None
        or not 1024 <= parsed.port <= 65535
    ):
        raise HomeProviderConfigError("provider_proxy_url_invalid")
    return f"http://127.0.0.1:{parsed.port}"


def execution_path(codex_bin: Path, python_bin: Path) -> str:
    directories = [
        str(codex_bin.parent), str(python_bin.parent), "/usr/local/bin",
        "/usr/bin", "/bin", "/usr/local/sbin", "/usr/sbin", "/sbin",
    ]
    return ":".join(dict.fromkeys(directories))


def current_user_codex_ready(
    codex_bin: Path,
    home: Path,
    path_value: str,
    proxy_url: str,
) -> bool:
    environment = {
        "HOME": str(home),
        "PATH": path_value,
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
    }
    if proxy_url:
        environment.update({"HTTP_PROXY": proxy_url, "HTTPS_PROXY": proxy_url})
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
    # Never expose or persist auth command output.
    return completed.returncode == 0 and "logged in" in (
        f"{completed.stdout}\n{completed.stderr}".lower()
    )


def source_files(source_root: Path) -> list[tuple[Path, str]]:
    return [
        (require_regular_file(source_root / relative, "runtime_source_missing"), installed)
        for relative, installed in RUNTIME_SOURCE_FILES
    ]


def runtime_digest(files: list[tuple[Path, str]]) -> str:
    digest = hashlib.sha256()
    for path, installed_name in sorted(files, key=lambda item: item[1]):
        digest.update(installed_name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def systemd_quote(value: str) -> str:
    if any(character in value for character in ("\0", "\n", "\r")):
        raise HomeProviderConfigError("systemd_value_invalid")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return f'"{escaped}"'


def render_service(template_path: Path, replacements: Mapping[str, str]) -> bytes:
    rendered = require_regular_file(template_path, "service_template_missing").read_text(
        encoding="utf-8"
    )
    for key, value in replacements.items():
        rendered = rendered.replace(f"__{key}__", systemd_quote(value))
    if re.search(r"__[A-Z0-9_]+__", rendered):
        raise HomeProviderConfigError("service_placeholder_unresolved")
    validate_service(rendered)
    return rendered.encode("utf-8")


def validate_service(rendered: str) -> None:
    required = (
        f"# X-Kolibri-Managed-Contract={MANAGED_CONTRACT}",
        "KOLIBRI_MESH_MEMBERSHIP_MANIFEST=",
        "KOLIBRI_EXTERNAL_PROVIDER_ACTOR_CREDENTIAL_FILE=",
        "KOLIBRI_RELEASE_CURRENT_LINK=",
        "KOLIBRI_RELEASE_ROOT=",
        "KOLIBRI_NODE_LABELS_JSON=",
        "home_systemd_user",
        "ConditionPathExists=",
        "WorkingDirectory=%h/.local/share/kolibri/home-codex-provider/worktrees",
        "--capabilities codex_provider_broker",
        "--max-inflight 1",
        "Restart=on-failure",
        "NoNewPrivileges=yes",
        "ProtectSystem=strict",
    )
    if any(item not in rendered for item in required):
        raise HomeProviderConfigError("service_contract_incomplete")
    lowered = rendered.lower()
    forbidden = (
        "conditionpathisregular=",
        'workingdirectory="',
        "kolibri_factory_control_url",
        "kolibri_factory_control_urls",
        "authorization=",
        "access_token",
        "refresh_token",
        "private_key",
        "api_key",
        "bearer ",
        "auth.json",
        "/.codex/",
    )
    if any(item in lowered for item in forbidden):
        raise HomeProviderConfigError("service_secret_or_static_authority_forbidden")


def validate_local_credential(path: Path, node_id: str) -> dict[str, Any]:
    try:
        info = path.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()
            or not 64 <= info.st_size <= 2048
        ):
            raise HomeProviderConfigError("external_provider_actor_credential_unsafe")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except HomeProviderConfigError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HomeProviderConfigError("external_provider_actor_credential_unreadable") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "credential_id", "node_id", "epoch", "token"}
        or payload.get("schema_version") != "kolibri.external-provider-credential.v1"
        or payload.get("node_id") != node_id
        or not SAFE_ID.fullmatch(str(payload.get("credential_id") or ""))
        or type(payload.get("epoch")) is not int
        or payload["epoch"] < 1
        or not TOKEN_RE.fullmatch(str(payload.get("token") or ""))
    ):
        raise HomeProviderConfigError("external_provider_actor_credential_invalid")
    return {"credential_id": payload["credential_id"], "epoch": payload["epoch"]}


def install_runtime(
    layout: HomeProviderLayout,
    files: list[tuple[Path, str]],
    digest: str,
) -> Path:
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
            or marker.read_text(encoding="utf-8").strip() != MANAGED_CONTRACT
        ):
            raise HomeProviderConfigError("runtime_release_not_managed")
        for source, installed_name in files:
            installed = release / installed_name
            if (
                not installed.is_file()
                or installed.is_symlink()
                or installed.read_bytes() != source.read_bytes()
                or stat.S_IMODE(installed.stat().st_mode) != 0o500
            ):
                raise HomeProviderConfigError("runtime_release_digest_mismatch")
        return release
    staging = Path(tempfile.mkdtemp(prefix=f".{digest}.", dir=layout.releases))
    try:
        os.chmod(staging, 0o700)
        for source, installed_name in files:
            target = staging / installed_name
            shutil.copyfile(source, target)
            os.chmod(target, 0o500)
        marker = staging / MANAGED_MARKER
        marker.write_text(f"{MANAGED_CONTRACT}\n", encoding="utf-8")
        os.chmod(marker, 0o400)
        os.replace(staging, release)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return release


def safe_existing_unit(path: Path) -> bytes | None:
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise HomeProviderConfigError("existing_service_unit_unsafe")
    payload = path.read_bytes()
    if f"X-Kolibri-Managed-Contract={MANAGED_CONTRACT}" not in payload.decode(
        "utf-8", "replace"
    ):
        raise HomeProviderConfigError("existing_service_unit_not_managed")
    return payload


def user_linger_enabled() -> bool:
    try:
        completed = subprocess.run(
            ["loginctl", "show-user", str(os.getuid()), "--property=Linger", "--value"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0 and completed.stdout.strip().lower() == "yes"


def systemctl_user(*args: str) -> None:
    try:
        completed = subprocess.run(
            ["systemctl", "--user", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HomeProviderConfigError("systemd_user_operation_failed") from exc
    if completed.returncode != 0:
        raise HomeProviderConfigError("systemd_user_operation_failed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh-manifest", type=Path, required=True)
    parser.add_argument("--mesh-interface", default="wg-kolibri")
    parser.add_argument("--runner-access", type=Path)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--python-bin", type=Path, default=Path(shutil.which("python3") or ""))
    parser.add_argument("--codex-bin", type=Path, default=Path(shutil.which("codex") or ""))
    parser.add_argument("--provider-proxy-url", default=os.environ.get("KOLIBRI_PROVIDER_PROXY_URL", ""))
    parser.add_argument("--node-id", default="home-codex-provider")
    parser.add_argument("--agent-id", default="home-codex-provider")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--start", action="store_true")
    args = parser.parse_args(argv)

    if args.start and not args.apply:
        raise HomeProviderConfigError("start_requires_apply")
    if os.geteuid() == 0:
        raise HomeProviderConfigError("home_provider_must_run_as_authorized_owner")

    source_root = args.source_root.expanduser().resolve()
    layout = HomeProviderLayout.from_home(Path.home())
    node_id = validate_identifier(args.node_id, "node_id")
    agent_id = validate_identifier(args.agent_id, "agent_id")
    mesh_manifest = require_regular_file(args.mesh_manifest, "mesh_manifest_invalid")
    assert_local_home(source_root, mesh_manifest, args.mesh_interface)
    runner_access_source = require_regular_file(
        args.runner_access or source_root / "ops" / "systemd" / "home-codex-provider.runner-access.json",
        "runner_access_manifest_invalid",
    )
    validate_runner_access(source_root, runner_access_source)
    python_bin = require_executable(args.python_bin, "python_executable_invalid")
    codex_bin = require_executable(args.codex_bin, "codex_executable_invalid")
    proxy_url = validate_proxy_url(args.provider_proxy_url)
    path_value = execution_path(codex_bin, python_bin)
    if not current_user_codex_ready(codex_bin, layout.home, path_value, proxy_url):
        raise HomeProviderConfigError("current_user_codex_session_unavailable")

    files = source_files(source_root)
    digest = runtime_digest(files)
    runtime_dir = layout.releases / digest
    labels = json.dumps({
        "authority": "home",
        "physical_node_id": node_id,
        "provider": "codex",
        "runtime": "home_systemd_user",
    }, sort_keys=True, separators=(",", ":"))
    template = source_root / "ops" / "systemd" / "kolibri-home-codex-provider.service.in"
    replacements = {
        "MESH_MANIFEST": str(mesh_manifest),
        "RUNNER_ACCESS": str(layout.runner_access),
        "PROVIDER_CREDENTIAL": str(layout.provider_credential),
        "WORK_ROOT": str(layout.work),
        "ARTIFACT_ROOT": str(layout.artifacts),
        "USER_HOME": str(layout.home),
        "RUNTIME_DIR": str(runtime_dir),
        "PYTHON_BIN": str(python_bin),
        "SANITIZED_LOG": str(layout.sanitized_log),
        "BOOTSTRAP_OUTPUT": f"append:{layout.bootstrap_log}",
        "HOME_ENV": f"HOME={layout.home}",
        "PATH_ENV": f"PATH={path_value}",
        "PYTHONPATH_ENV": f"PYTHONPATH={runtime_dir}",
        "PROVIDER_RELEASE_CURRENT_ENV": (
            f"KOLIBRI_RELEASE_CURRENT_LINK={layout.base / 'runtime' / 'provider-current'}"
        ),
        "PROVIDER_RELEASE_ROOT_ENV": f"KOLIBRI_RELEASE_ROOT={layout.releases}",
        "MESH_MANIFEST_ENV": f"KOLIBRI_MESH_MEMBERSHIP_MANIFEST={mesh_manifest}",
        "RUNNER_ACCESS_ENV": f"KOLIBRI_RUNNER_ACCESS_MANIFEST={layout.runner_access}",
        "PROVIDER_CREDENTIAL_ENV": (
            f"KOLIBRI_EXTERNAL_PROVIDER_ACTOR_CREDENTIAL_FILE={layout.provider_credential}"
        ),
        "NODE_LABELS_ENV": f"KOLIBRI_NODE_LABELS_JSON={labels}",
        "PROVIDER_PROXY_ENV": f"KOLIBRI_PROVIDER_PROXY_URL={proxy_url}",
        "EXEC_PATH": path_value,
        "PROVIDER_PROXY_URL": proxy_url,
        "NODE_LABELS_JSON": labels,
        "NODE_ID": node_id,
        "AGENT_ID": agent_id,
        "BOOTSTRAP_LOG": str(layout.bootstrap_log),
    }
    service_bytes = render_service(template, replacements)
    credential_present = layout.provider_credential.exists()
    plan: dict[str, Any] = {
        "schema_version": "kolibri.home-codex-provider-install.v1",
        "status": "validated",
        "apply": args.apply,
        "start": args.start,
        "node_id": node_id,
        "actor_scope": "external_provider_actor",
        "control_plane_authority": "home",
        "control_plane_source": "replicated_mesh_manifest",
        "runtime": "home_systemd_user",
        "runtime_digest": f"sha256:{digest}",
        "service_unit": str(layout.service_unit),
        "credential_present": credential_present,
        "codex_session": "current_user_authenticated",
        "credentials_copied": False,
        "public_model": "kolibri",
        "readiness_refresh_seconds": READINESS_REFRESH_SECONDS,
        "persistent_user_manager": user_linger_enabled(),
    }
    if not args.apply:
        plan["next_action"] = (
            "provision the scoped external-provider actor credential locally on Home"
            if not credential_present
            else "apply the managed runtime, then verify readiness and a fenced provider canary"
        )
        print(json_line(plan))
        return 0

    credential_metadata = validate_local_credential(layout.provider_credential, node_id)
    if args.start and not user_linger_enabled():
        raise HomeProviderConfigError("home_owner_linger_required_for_24x7_service")

    for directory in (
        layout.base, layout.config, layout.work, layout.artifacts, layout.logs,
        layout.service_unit.parent,
    ):
        ensure_directory(directory)
    for log_path in (layout.sanitized_log, layout.bootstrap_log):
        log_path.touch(mode=0o600, exist_ok=True)
        os.chmod(log_path, 0o600)
    installed_runtime = install_runtime(layout, files, digest)
    if installed_runtime != runtime_dir:
        raise HomeProviderConfigError("runtime_install_path_mismatch")
    atomic_write(layout.runner_access, runner_access_source.read_bytes(), 0o600)
    previous_unit = safe_existing_unit(layout.service_unit)
    atomic_write(layout.service_unit, service_bytes, 0o600)

    if args.start:
        try:
            systemctl_user("daemon-reload")
            systemctl_user("enable", "--now", SERVICE_NAME)
        except HomeProviderConfigError:
            if previous_unit is None:
                layout.service_unit.unlink(missing_ok=True)
            else:
                atomic_write(layout.service_unit, previous_unit, 0o600)
            try:
                systemctl_user("daemon-reload")
            except HomeProviderConfigError:
                pass
            raise

    plan.update({
        "status": "installed_and_started_unverified" if args.start else "installed_not_started",
        "credential_id": credential_metadata["credential_id"],
        "credential_epoch": credential_metadata["epoch"],
        "credential_value_returned": False,
        "next_action": (
            "verify fresh Codex readiness and one fenced provider canary before undrain/use"
        ),
    })
    print(json_line(plan))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HomeProviderConfigError as exc:
        print(json_line({"status": "failed", "error": exc.code}))
        raise SystemExit(1)
