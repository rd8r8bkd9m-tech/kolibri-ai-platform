#!/usr/bin/env python3
"""Fail closed when a build runs with a non-canonical Kolibri toolchain."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def command_version(*command: str) -> str:
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return (result.stdout or result.stderr).strip()


def normalized(value: str) -> str:
    match = re.search(r"\d+\.\d+\.\d+", value)
    if not match:
        raise SystemExit(f"unparseable tool version: {value!r}")
    return match.group(0)


def main() -> int:
    manifest = json.loads((ROOT / "toolchains.json").read_text(encoding="utf-8"))
    expected = {name: manifest[name]["version"] for name in ("node", "python", "rust")}
    actual = {
        "node": normalized(command_version("node", "--version")),
        "python": normalized(command_version(sys.executable, "--version")),
        "rust": normalized(command_version("rustc", "--version")),
    }
    mismatches = {
        name: {"expected": expected[name], "actual": actual[name]}
        for name in expected
        if actual[name] != expected[name]
    }
    if mismatches:
        print(json.dumps({"status": "blocked", "mismatches": mismatches}, sort_keys=True))
        return 1
    print(json.dumps({"status": "verified", "versions": actual}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
