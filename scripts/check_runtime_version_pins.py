#!/usr/bin/env python3
"""Validate the canonical Node.js and Python runtime pins without network access."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
WORKFLOWS = (
    ROOT / ".github" / "workflows" / "ci.yml",
    ROOT / ".github" / "workflows" / "pages.yml",
)
PACKAGE_MANIFESTS = (
    ROOT / "apps" / "kolibri-shell-next" / "package.json",
    ROOT / "frontend" / "package.json",
)
NPM_VERSION = "11.17.0"


def read_pin(filename: str) -> str:
    value = (ROOT / filename).read_text(encoding="utf-8").strip()
    if not VERSION_PATTERN.fullmatch(value):
        raise AssertionError(f"{filename} must contain one stable x.y.z version")
    return value


def validate_workflows() -> None:
    setup_node_count = 0
    node_file_count = 0
    setup_python_count = 0
    python_file_count = 0

    for path in WORKFLOWS:
        source = path.read_text(encoding="utf-8")
        if re.search(r"^\s*node-version:\s*", source, re.MULTILINE):
            raise AssertionError(f"{path.relative_to(ROOT)} has a divergent Node.js literal")
        if re.search(r"^\s*python-version:\s*", source, re.MULTILINE):
            raise AssertionError(f"{path.relative_to(ROOT)} has a divergent Python literal")
        node_action_versions = re.findall(r"actions/setup-node@(v[0-9]+)", source)
        python_action_versions = re.findall(r"actions/setup-python@(v[0-9]+)", source)
        if any(version != "v6" for version in node_action_versions):
            raise AssertionError(f"{path.relative_to(ROOT)} must use setup-node v6")
        if any(version != "v6" for version in python_action_versions):
            raise AssertionError(f"{path.relative_to(ROOT)} must use setup-python v6")
        setup_node_count += source.count("actions/setup-node@")
        node_file_count += source.count('node-version-file: ".node-version"')
        setup_python_count += source.count("actions/setup-python@")
        python_file_count += source.count('python-version-file: ".python-version"')

    if setup_node_count != node_file_count:
        raise AssertionError("every setup-node step must use .node-version")
    if setup_python_count != python_file_count:
        raise AssertionError("every setup-python step must use .python-version")


def validate_package_engines(node_pin: str) -> None:
    for path in PACKAGE_MANIFESTS:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        label = path.relative_to(ROOT)
        if manifest.get("packageManager") != f"npm@{NPM_VERSION}":
            raise AssertionError(f"{label} must pin npm@{NPM_VERSION}")
        engines = manifest.get("engines", {})
        if engines.get("node") != node_pin:
            raise AssertionError(f"{label} Node.js engine must match .node-version")
        if engines.get("npm") != NPM_VERSION:
            raise AssertionError(f"{label} npm engine must match bundled npm")


def command_version(command: list[str]) -> str:
    return subprocess.check_output(command, text=True).strip().removeprefix("v")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check-installed",
        action="store_true",
        help="also require the running Node.js and Python patch versions to match",
    )
    args = parser.parse_args()

    node_pin = read_pin(".node-version")
    python_pin = read_pin(".python-version")
    validate_workflows()
    validate_package_engines(node_pin)

    if args.check_installed:
        actual_node = command_version(["node", "--version"])
        actual_python = ".".join(map(str, sys.version_info[:3]))
        if actual_node != node_pin:
            raise AssertionError(f"Node.js {actual_node} != pinned {node_pin}")
        if actual_python != python_pin:
            raise AssertionError(f"Python {actual_python} != pinned {python_pin}")

    print(
        f"runtime_pins=ok node={node_pin} npm={NPM_VERSION} python={python_pin}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
