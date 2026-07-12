from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "kolibri-shell-next"
OFFICIAL_BIRD_SHA256 = (
    "6f30357f75c963e5e4d85b464b10eadb2545d2a6b40aced54861571c4322c3d7"
)


def test_clean_shell_is_the_only_ci_shell_authority() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "apps/kolibri-shell-next/package-lock.json" in workflow
    assert "working-directory: apps/kolibri-shell-next" in workflow
    assert re.search(r"apps/kolibri-shell(?:/|$)", workflow, re.MULTILINE) is None


def test_clean_shell_has_no_legacy_application_dependency() -> None:
    forbidden = (
        re.compile(r"apps/kolibri-shell(?:/|$)"),
        re.compile(r"(?:^|/)frontend(?:/|$)"),
    )
    source_files = [
        path
        for path in (SHELL / "src").rglob("*")
        if path.suffix in {".ts", ".tsx", ".js", ".jsx", ".mjs"}
    ]

    for path in source_files:
        source = path.read_text(encoding="utf-8").replace("\\", "/")
        assert not any(pattern.search(source) for pattern in forbidden), path


def test_clean_shell_runtime_and_brand_are_pinned() -> None:
    manifest = json.loads((SHELL / "package.json").read_text(encoding="utf-8"))
    bird = (SHELL / "public" / "kolibri-bird.png").read_bytes()

    assert manifest["engines"] == {"node": "26.5.0", "npm": "11.17.0"}
    assert manifest["packageManager"] == "npm@11.17.0"
    assert hashlib.sha256(bird).hexdigest() == OFFICIAL_BIRD_SHA256
