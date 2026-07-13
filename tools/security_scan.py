#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "release-evidence" / "security-scan.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

EXCLUDED = {".git", ".venv", "node_modules", "dist", "var", "data", "release-evidence"}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".json", ".md", ".yml", ".yaml", ".toml", ".sh", ".conf", ".txt", ".example"}
PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "generic_secret_assignment": re.compile(r"(?i)\b(?:password|secret|token|api[_-]?key)\s*[:=]\s*['\"](?!replace-|dev-|test-|canary-|\$\{|<)[^'\"\n]{12,}['\"]"),
}
FORBIDDEN_LITERALS = {
    "generic_failure": "Kolibri could not produce a verified response",
    "legacy_control_ip": "10.99.0.2",
    "legacy_primary_identity": "primary-candidate",
}

findings: list[dict] = []
scanned = 0
for path in ROOT.rglob("*"):
    relative = path.relative_to(ROOT)
    if not path.is_file() or any(part in EXCLUDED for part in relative.parts):
        continue
    if path.resolve() in {Path(__file__).resolve(), (ROOT / "tools/validate_architecture.py").resolve()}:
        continue
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Dockerfile.backend", "Dockerfile.frontend", ".env.example"}:
        continue
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    scanned += 1
    for kind, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            findings.append({"kind": kind, "path": str(path.relative_to(ROOT)), "line": text.count("\n", 0, match.start()) + 1})
    if not ("docs" in path.parts and "spec" in path.parts):
        for kind, literal in FORBIDDEN_LITERALS.items():
            if literal in text:
                findings.append({"kind": kind, "path": str(path.relative_to(ROOT)), "line": text[: text.index(literal)].count("\n") + 1})

report = {"status": "passed" if not findings else "failed", "scanned_files": scanned, "findings": findings}
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if not findings else 1)
