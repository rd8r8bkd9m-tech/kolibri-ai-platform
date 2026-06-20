#!/usr/bin/env python3
"""Validate the FormulaLM estimate pilot orchestration contract.

This script is intentionally dependency-free. It validates the repo artifacts
that must exist before Codex can fan out FormulaLM preflight work to agents. It
does not start training, contact servers, or create runtime task envelopes
unless --write-envelopes is explicitly added later.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
RUN_ID = "estimate-pilot-001"
RUN_DIR = "/srv/kolibri/runs/estimate-pilot-001"
FORMULALM_DIR = PROJECT_DIR / "ops" / "formulalm"
ROLE_MAP_PATH = PROJECT_DIR / "ops" / "experiments" / RUN_ID / "role_map.json"
AGENTS_PATH = PROJECT_DIR / "ops" / "agents.yml"
REQUIRED_FORBIDDEN = {".env", ".ssh", ".mimocode", "auth.json"}
REQUIRED_SAFETY_PHRASES = (
    "--dangerously-skip-permissions",
    "pkill",
    "source estimate files are immutable",
    "final-test data must not appear",
    "do not deploy",
    "do not read or log secrets",
    "success requires metrics",
)


class ValidationError(RuntimeError):
    """Raised for validation failures that should block fanout."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"{path} must contain a JSON object")
    return data


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_json_files() -> list[dict[str, str]]:
    files = [
        FORMULALM_DIR / "task_envelope.schema.json",
        FORMULALM_DIR / "status.schema.json",
        FORMULALM_DIR / "result.schema.json",
        FORMULALM_DIR / "sample_task_envelope.json",
        ROLE_MAP_PATH,
    ]
    return [{"path": str(path.relative_to(PROJECT_DIR)), "sha256": sha256_file(path)} for path in files if load_json(path)]


def validate_role_map() -> dict[str, Any]:
    agents = load_json(AGENTS_PATH).get("servers", {})
    role_map = load_json(ROLE_MAP_PATH)
    servers = role_map.get("servers", {})
    if role_map.get("run_id") != RUN_ID:
        raise ValidationError("role_map.run_id must be estimate-pilot-001")
    if role_map.get("run_dir") != RUN_DIR:
        raise ValidationError(f"role_map.run_dir must be {RUN_DIR}")
    if set(agents) != set(servers):
        missing = sorted(set(agents) - set(servers))
        extra = sorted(set(servers) - set(agents))
        raise ValidationError(f"role_map server mismatch; missing={missing}; extra={extra}")
    if len(servers) != 19:
        raise ValidationError(f"role_map must contain 19 servers, got {len(servers)}")

    islands = [name for name, item in servers.items() if item.get("experiment_role") == "formulalm-island"]
    if len(islands) != 8:
        raise ValidationError(f"Expected 8 FormulaLM islands, got {len(islands)}: {islands}")

    seeds = [item.get("seed") for item in servers.values()]
    if len(seeds) != len(set(seeds)):
        raise ValidationError("FormulaLM role_map seeds must be unique")
    for name, item in servers.items():
        for key in ("experiment_role", "track", "phase", "shard", "seed"):
            if key not in item:
                raise ValidationError(f"role_map.{name} missing {key}")
    gates = role_map.get("gates", {})
    required_true = {
        "preflight_required_before_envelopes",
        "training_requires_preflight_pass",
        "success_requires_metrics",
        "codex_review_required_before_scale",
    }
    for key in required_true:
        if gates.get(key) is not True:
            raise ValidationError(f"role_map.gates.{key} must be true")
    if gates.get("final_test_leakage_allowed") is not False:
        raise ValidationError("role_map.gates.final_test_leakage_allowed must be false")
    return {"server_count": len(servers), "formula_islands": sorted(islands)}


def validate_sample_envelope() -> dict[str, Any]:
    schema = load_json(FORMULALM_DIR / "task_envelope.schema.json")
    sample = load_json(FORMULALM_DIR / "sample_task_envelope.json")
    missing = [key for key in schema.get("required", []) if key not in sample]
    if missing:
        raise ValidationError(f"sample_task_envelope missing required fields: {missing}")
    if sample.get("run_id") != RUN_ID:
        raise ValidationError("sample_task_envelope.run_id mismatch")
    if sample.get("run_dir") != RUN_DIR:
        raise ValidationError("sample_task_envelope.run_dir mismatch")
    dataset = sample.get("dataset_scope", {})
    if dataset.get("range") != "401-421":
        raise ValidationError("sample_task_envelope dataset range must be 401-421")
    if dataset.get("immutable") is not True or dataset.get("final_test_hidden") is not True:
        raise ValidationError("sample_task_envelope dataset must be immutable and final-test hidden")
    forbidden = set(sample.get("forbidden_paths", []))
    if not REQUIRED_FORBIDDEN.issubset(forbidden):
        raise ValidationError(f"sample_task_envelope missing forbidden paths: {sorted(REQUIRED_FORBIDDEN - forbidden)}")
    return {"task_id": sample["task_id"], "required_fields": len(schema.get("required", []))}


def validate_safety_text() -> dict[str, Any]:
    text = "\n".join(
        [
            (PROJECT_DIR / "AGENTS.md").read_text(encoding="utf-8"),
            (FORMULALM_DIR / "worker_prompt.md").read_text(encoding="utf-8"),
            json.dumps(load_json(ROLE_MAP_PATH), sort_keys=True),
        ]
    ).lower()
    missing = [phrase for phrase in REQUIRED_SAFETY_PHRASES if phrase.lower() not in text]
    if missing:
        raise ValidationError(f"Missing safety phrase(s): {missing}")
    return {"phrases": len(REQUIRED_SAFETY_PHRASES)}


def dry_run_envelopes() -> list[dict[str, Any]]:
    role_map = load_json(ROLE_MAP_PATH)
    envelopes = []
    for server, item in sorted(role_map["servers"].items()):
        mode = "read_only"
        phase = "preflight"
        envelopes.append(
            {
                "run_id": RUN_ID,
                "task_id": f"{RUN_ID}-{phase}-{server}",
                "server": server,
                "role": item["experiment_role"],
                "phase": phase,
                "mode": mode,
                "run_dir": RUN_DIR,
                "allowed_paths": [RUN_DIR],
                "forbidden_paths": sorted(REQUIRED_FORBIDDEN | {"private_keys", "tokens"}),
                "dataset_scope": {
                    "source": "current estimate files discovered during preflight",
                    "range": "401-421",
                    "immutable": True,
                    "final_test_hidden": True,
                },
                "prompt": (
                    "Perform read-only FormulaLM preflight for the assigned role. "
                    "Do not train, mutate source data, read secrets, or deploy."
                ),
                "required_checks": ["python3 scripts/validate_formulalm_experiment.py --dry-run"],
                "expected_outputs": ["status JSON", "artifact list", "risk list"],
                "safety_rules": [
                    "Do not read or log secrets.",
                    "Do not mutate source estimate files.",
                    "Do not expose final-test data to training or tuning prompts.",
                ],
                "timeout_seconds": 900,
            }
        )
    if len(envelopes) != 19:
        raise ValidationError(f"dry-run envelope generation expected 19, got {len(envelopes)}")
    return envelopes


def validate(args: argparse.Namespace) -> dict[str, Any]:
    json_files = validate_json_files()
    role_map = validate_role_map()
    sample = validate_sample_envelope()
    safety = validate_safety_text()
    envelopes = dry_run_envelopes()
    return {
        "status": "ok",
        "run_id": RUN_ID,
        "json_files": json_files,
        "role_map": role_map,
        "sample_envelope": sample,
        "safety": safety,
        "dry_run": {
            "envelope_count": len(envelopes),
            "training_started": False,
            "servers_contacted": False,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate FormulaLM estimate pilot artifacts")
    parser.add_argument("--dry-run", action="store_true", help="Validate and dry-run envelope generation only")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        print(json.dumps(validate(args), ensure_ascii=True, indent=2))
        return 0
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
