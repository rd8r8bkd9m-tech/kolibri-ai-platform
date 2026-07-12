#!/usr/bin/env python3
"""Probe Codex model entitlement without exposing provider error bodies.

The probe is deliberately observational.  It emits a bounded, redacted JSON
attestation that a signed release may review before setting
``KOLIBRI_CODEX_MODELS``.  It never edits provider configuration or copies
credentials between nodes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "kolibri.codex-model-entitlement.v1"
DEFAULT_MODELS = ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,119}$")
SUCCESS_MARKER = "KOLIBRI_ENTITLEMENT_OK"
SAFE_ENV_KEYS = {
    "ALL_PROXY", "CODEX_HOME", "HOME", "HTTPS_PROXY", "HTTP_PROXY", "LANG",
    "LC_ALL", "LOGNAME", "NO_PROXY", "PATH", "SSL_CERT_DIR", "SSL_CERT_FILE",
    "TERM", "TMPDIR", "USER", "XDG_CACHE_HOME", "XDG_CONFIG_HOME",
}


def _safe_environment(work_dir: Path) -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items()
        if key in SAFE_ENV_KEYS and isinstance(value, str)
    }
    environment["TMPDIR"] = str(work_dir)
    environment.setdefault("LANG", "C.UTF-8")
    environment.setdefault("PATH", os.defpath)
    return environment


def _assistant_text(stdout: str) -> str:
    parts: list[str] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item") if isinstance(event.get("item"), dict) else event
        if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "".join(parts).strip()


def _failure_category(stdout: str, stderr: str, return_code: int) -> str:
    text = f"{stdout}\n{stderr}".lower()
    if return_code == 124 or re.search(r"timed? out|timeout", text):
        return "timeout"
    if re.search(r"usage|quota|rate.?limit|capacity", text):
        return "usage_or_capacity"
    if re.search(r"auth|login|credential|unauthor|forbidden", text):
        return "authentication"
    if re.search(r"risk.?control|policy|safety", text):
        return "risk_control"
    if re.search(r"model|unsupported|not available|does not exist", text):
        return "model_unavailable"
    if re.search(r"network|connect|dns|cloudflare|proxy", text):
        return "network"
    return "runner_failure"


def probe_model(
    codex_bin: Path,
    model: str,
    repository: Path,
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="kolibri-codex-entitlement-") as temp:
        work_dir = Path(temp)
        command = [
            str(codex_bin), "exec", "--json", "--ephemeral",
            "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules",
            "--color", "never", "--sandbox", "read-only", "-C", str(repository),
            "-c", 'shell_environment_policy.inherit="none"', "--model", model, "-",
        ]
        try:
            completed = subprocess.run(
                command,
                input=f"Return exactly: {SUCCESS_MARKER}\n",
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
                check=False,
                env=_safe_environment(work_dir),
            )
            return_code = completed.returncode
            stdout = completed.stdout[-262_144:]
            stderr = completed.stderr[-65_536:]
        except subprocess.TimeoutExpired as exc:
            return_code = 124
            stdout = str(exc.stdout or "")[-262_144:]
            stderr = str(exc.stderr or "")[-65_536:]
    answer = _assistant_text(stdout)
    entitled = return_code == 0 and answer == SUCCESS_MARKER
    return {
        "model": model,
        "status": "entitled" if entitled else "unavailable",
        "entitled": entitled,
        "failure_category": None if entitled else _failure_category(stdout, stderr, return_code),
        "exit_code": return_code,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "output_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest() if answer else None,
        "output_bytes": len(answer.encode("utf-8")),
    }


def build_report(
    codex_bin: Path,
    repository: Path,
    models: list[str],
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    results = [
        probe_model(codex_bin, model, repository, timeout_seconds=timeout_seconds)
        for model in models
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runner_sha256": hashlib.sha256(codex_bin.read_bytes()).hexdigest(),
        "repository_sha256": hashlib.sha256(str(repository.resolve()).encode("utf-8")).hexdigest(),
        "results": results,
        "enabled_models": [item["model"] for item in results if item["entitled"]],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-bin", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--timeout-seconds", type=int, default=45)
    parser.add_argument("--require-entitled", action="store_true")
    args = parser.parse_args(argv)
    if not args.codex_bin.is_file() or not os.access(args.codex_bin, os.X_OK):
        parser.error("codex binary must be an executable regular file")
    if not args.repository.is_dir():
        parser.error("repository must be a directory")
    models = list(dict.fromkeys(args.models or DEFAULT_MODELS))
    if not models or any(not MODEL_PATTERN.fullmatch(item) for item in models):
        parser.error("invalid model identifier")
    if not 5 <= args.timeout_seconds <= 120:
        parser.error("timeout must be between 5 and 120 seconds")
    report = build_report(
        args.codex_bin.resolve(), args.repository.resolve(), models,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 2 if args.require_entitled and not report["enabled_models"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
