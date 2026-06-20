#!/usr/bin/env python3
"""Validate FormulaLM Proof v1 contract and optional local data readiness."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
RUN_ID = "formulalm-proof-v1"
EXP_DIR = PROJECT_DIR / "ops" / "experiments" / RUN_ID
CONFIG_PATH = EXP_DIR / "configuration.json"
ROLE_MAP_PATH = EXP_DIR / "role_map.json"
AGENTS_PATH = PROJECT_DIR / "ops" / "agents.yml"
ESTIMATE_SUFFIXES = {".pdf", ".docx", ".xlsx", ".csv", ".json", ".txt", ".md"}
DATASET_COUNT_MIN = 401
DATASET_COUNT_MAX = 421


class ValidationError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"{path} must contain object")
    return data


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_contract() -> dict[str, Any]:
    config = load_json(CONFIG_PATH)
    role_map = load_json(ROLE_MAP_PATH)
    agents = load_json(AGENTS_PATH).get("servers", {})

    if config.get("run_id") != RUN_ID or role_map.get("run_id") != RUN_ID:
        raise ValidationError("run_id mismatch")
    if role_map.get("run_dir") != "/srv/kolibri/runs/formulalm-proof-v1":
        raise ValidationError("unexpected run_dir")
    dataset = config.get("dataset", {})
    if dataset.get("expected_count_min") != DATASET_COUNT_MIN or dataset.get("expected_count_max") != DATASET_COUNT_MAX:
        raise ValidationError("dataset expected count range must be 401-421")

    servers = role_map.get("servers", {})
    if len(servers) != 4:
        raise ValidationError(f"Proof v1 must use exactly 4 servers, got {len(servers)}")
    unknown = sorted(set(servers) - set(agents))
    if unknown:
        raise ValidationError(f"Unknown servers in role_map: {unknown}")

    seeds = sorted(item.get("seed") for item in servers.values() if item.get("seed") is not None)
    if seeds != [101, 202, 303]:
        raise ValidationError(f"Expected FormulaLM seeds [101, 202, 303], got {seeds}")

    logits = config.get("logits", {})
    expected_logits = {
        "base_model": "Qwen2.5-1.5B",
        "base_model_frozen": True,
        "context_length_tokens": 64,
        "top_k": 64,
        "train_contexts": 10000,
        "validation_contexts": 2000,
        "test_contexts": 2000,
    }
    for key, expected in expected_logits.items():
        if logits.get(key) != expected:
            raise ValidationError(f"logits.{key} expected {expected!r}, got {logits.get(key)!r}")

    formulalm = config.get("formulalm", {})
    if formulalm.get("population") != 8 or formulalm.get("generations") != 100:
        raise ValidationError("FormulaLM population/generations mismatch")
    if formulalm.get("seeds") != [101, 202, 303]:
        raise ValidationError("FormulaLM seed list mismatch")
    if formulalm.get("alpha") != [0.03, 0.1, 0.3]:
        raise ValidationError("FormulaLM alpha list mismatch")
    if formulalm.get("backpropagation_allowed") is not False:
        raise ValidationError("Backpropagation must be forbidden")
    if formulalm.get("checkpoint_selection") != "validation_only":
        raise ValidationError("Checkpoint selection must be validation_only")

    baselines = set(config.get("baselines", []))
    required_baselines = {
        "frozen_qwen",
        "qwen_plus_random_formulalm",
        "qwen_plus_constant_rank_bias",
        "qwen_plus_evolved_formulalm",
    }
    if baselines != required_baselines:
        raise ValidationError(f"Baseline mismatch: {sorted(baselines)}")

    criteria = config.get("proof_criteria", {})
    if criteria.get("delta_ce_positive") is not True:
        raise ValidationError("delta_ce_positive criterion missing")
    if criteria.get("ci_lower_bound_positive") is not True:
        raise ValidationError("ci_lower_bound_positive criterion missing")
    if criteria.get("positive_seeds_min") != 2 or criteria.get("total_seeds") != 3:
        raise ValidationError("seed success criterion mismatch")
    if criteria.get("train_test_leakage_allowed") is not False:
        raise ValidationError("train/test leakage must be forbidden")
    if criteria.get("max_model_size_mb") != 50:
        raise ValidationError("model size criterion must be 50 MB")
    if criteria.get("max_inference_overhead_percent") != 10:
        raise ValidationError("latency overhead criterion must be 10 percent")

    return {
        "configuration_sha256": sha256(CONFIG_PATH),
        "role_map_sha256": sha256(ROLE_MAP_PATH),
        "server_count": len(servers),
        "seeds": seeds,
    }


def discover_estimates(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    files = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in ESTIMATE_SUFFIXES:
            continue
        lowered = path.name.lower()
        if "estimate" not in lowered and "smeta" not in lowered and "смет" not in lowered:
            continue
        files.append(
            {
                "path": str(path),
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return sorted(files, key=lambda item: item["path"])


def validate_data_readiness(root: Path) -> dict[str, Any]:
    estimates = discover_estimates(root)
    status = "ready" if DATASET_COUNT_MIN <= len(estimates) <= DATASET_COUNT_MAX else "blocked"
    return {
        "status": status,
        "root": str(root),
        "estimate_like_files": len(estimates),
        "required_min_estimates": DATASET_COUNT_MIN,
        "required_max_estimates": DATASET_COUNT_MAX,
        "sample": estimates[:10],
        "blocker": None if status == "ready" else "current 401-421 estimate corpus was not found under the checked root",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate FormulaLM Proof v1 contract")
    parser.add_argument("--check-data-root", help="Optional local/remote path to inspect for estimate files")
    args = parser.parse_args()

    try:
        payload = {
            "status": "ok",
            "run_id": RUN_ID,
            "contract": validate_contract(),
            "data_readiness": None,
            "training_started": False,
            "servers_contacted": False,
        }
        if args.check_data_root:
            payload["data_readiness"] = validate_data_readiness(Path(args.check_data_root).expanduser().resolve())
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        return 0 if not payload["data_readiness"] or payload["data_readiness"]["status"] == "ready" else 2
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
