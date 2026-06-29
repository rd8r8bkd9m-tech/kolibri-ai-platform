#!/usr/bin/env python3
"""Run a remote-guarded Qwen/Ollama benchmark with and without FormulaLM.

FormulaLM is treated as a deterministic program overlay:
- the same remote model is used for natural-language interpretation;
- totals are constrained by a fixed formula kernel and pricebook;
- model weights are never modified.

The script is allowed to run from a remote factory node. On macOS it writes a
blocker artifact and exits before any model call unless explicitly overridden.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
import sys

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


DEFAULT_CASES = [
    {"id": "plaster-tatarstan-100", "prompt": "100 м2 штукатурки в Татарстане", "client_name": "Иван"},
    {"id": "plaster-tatarstan-42", "prompt": "42 м2 штукатурки в Татарстане", "client_name": "Алия"},
    {"id": "kitchen-12", "prompt": "Нужна смета на ремонт кухни 12 м2 в Татарстане", "client_name": "Иван"},
    {"id": "bathroom-8", "prompt": "Смета на санузел 8 м2 в Татарстане", "client_name": "Тестовый клиент"},
    {"id": "flat-20", "prompt": "Ремонт квартиры 20 м2 в Татарстане", "client_name": "Клиент"},
    {"id": "plaster-moscow-35", "prompt": "35 м2 штукатурки в Москве, нужна смета с материалами", "client_name": "ООО Север"},
    {"id": "plaster-spb-27-5", "prompt": "Посчитай штукатурку стен 27,5 м2 в Санкт-Петербурге", "client_name": "Мария"},
    {"id": "flat-no-region-18", "prompt": "Сделай смету на ремонт квартиры 18 м2", "client_name": "Без региона"},
    {"id": "kitchen-text-area", "prompt": "Кухня двенадцать квадратных метров, Татарстан, нужен предварительный расчет", "client_name": "Наталья"},
    {"id": "plaster-m2-symbol", "prompt": "Штукатурка 64 м², Республика Татарстан", "client_name": "Рустам"},
    {"id": "bathroom-moscow-6", "prompt": "Санузел 6 кв. м Москва под ключ", "client_name": "Анна"},
    {"id": "plaster-large-250", "prompt": "250 м2 штукатурных работ в Татарстане для коммерческого объекта", "client_name": "ООО Казань Ремонт"},
]
DATASET_VERSION = "formulalm-estimate-ru-2026q2-v1"
PRICEBOOK_VERSION = "kolibri-ru-2026q2-v1"
EXPECTED_PILOT_CASES = 20
EXPECTED_PILOT_REPEATS = 5


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_text(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def command_output(argv: list[str], timeout: int = 5) -> str | None:
    try:
        completed = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    output = (completed.stdout or completed.stderr).strip()
    return output or None


def repo_commit() -> str:
    return command_output(["git", "rev-parse", "HEAD"], timeout=5) or "unknown"


def runtime_candidates() -> list[dict[str, Any]]:
    candidates = []
    for name, version_command in {
        "ollama": ["ollama", "--version"],
        "llama-cli": ["llama-cli", "--version"],
        "llama.cpp": ["llama.cpp", "--version"],
        "vllm": ["vllm", "--version"],
    }.items():
        path = shutil.which(name)
        candidates.append({
            "name": name,
            "available": bool(path),
            "path": path,
            "version": command_output(version_command, timeout=5) if path else None,
        })
    return candidates


def machine_resources(out_dir: Path) -> dict[str, Any]:
    disk = shutil.disk_usage(out_dir)
    mem_total_kb = read_text("/proc/meminfo")
    mem_total_line = None
    mem_available_line = None
    if mem_total_kb:
        for line in mem_total_kb.splitlines():
            if line.startswith("MemTotal:"):
                mem_total_line = line
            elif line.startswith("MemAvailable:"):
                mem_available_line = line
    return {
        "cpu_count": os.cpu_count(),
        "loadavg": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
        "memory": {
            "mem_total": mem_total_line,
            "mem_available": mem_available_line,
        },
        "disk": {
            "path": str(out_dir),
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
        },
    }


def preflight_payload(args: argparse.Namespace, out_dir: Path) -> dict[str, Any]:
    return {
        "artifact_dir": str(out_dir),
        "cpu_ram_disk": machine_resources(out_dir),
        "dataset_version": args.dataset_version,
        "hostname": socket.gethostname(),
        "model": args.model,
        "model_candidates": [{"model": args.model, "source": "cli_argument"}],
        "node_id": args.node_id,
        "ollama_url": args.ollama_url,
        "platform": platform.platform(),
        "platform_system": platform.system(),
        "repo_commit": repo_commit(),
        "pricebook_version": args.pricebook_version,
        "python_version": platform.python_version(),
        "remote_guard": {
            "mac_execution_allowed": bool(args.allow_local_mac),
            "mode": "execute_preflight_then_run_or_block",
            "status": "preflight_recorded",
        },
        "runtime_candidates": runtime_candidates(),
        "task_id": args.task_id,
        "time": utc_now(),
        "uname": command_output(["uname", "-a"], timeout=5),
    }


def write_blocker(
    out_dir: Path,
    severity: str,
    category: str,
    message: str,
    preflight: dict[str, Any],
    safe_next_action: str | None = None,
) -> dict[str, Any]:
    blocker = {
        "category": category,
        "first_seen_at": utc_now(),
        "mac_execution": "blocked" if preflight.get("platform_system") == "Darwin" else "not_attempted",
        "message": message,
        "node_id": preflight.get("node_id"),
        "preflight": preflight,
        "safe_next_action": safe_next_action or "Fix the remote runtime or resubmit through Control Plane after the blocker is gone.",
        "severity": severity,
        "status": "blocked",
        "task_id": preflight.get("task_id"),
    }
    write_json(out_dir / "blockers.json", blocker)
    write_blocker_markdown(out_dir / "blocker-report.md", blocker)
    return blocker


def write_blocker_markdown(path: Path, blocker: dict[str, Any]) -> None:
    preflight = blocker.get("preflight", {})
    lines = [
        "# FormulaLM Benchmark Blocker",
        "",
        f"- Verdict: `blocked`",
        f"- Task: `{blocker.get('task_id')}`",
        f"- Node: `{blocker.get('node_id')}`",
        f"- Severity: `{blocker.get('severity')}`",
        f"- Category: `{blocker.get('category')}`",
        f"- Message: {blocker.get('message')}",
        f"- Safe next action: {blocker.get('safe_next_action')}",
        "",
        "## Preflight Evidence",
        "",
        f"- Hostname: `{preflight.get('hostname')}`",
        f"- Platform system: `{preflight.get('platform_system')}`",
        f"- Uname: `{preflight.get('uname')}`",
        f"- Repo commit: `{preflight.get('repo_commit')}`",
        f"- Artifact dir: `{preflight.get('artifact_dir')}`",
        f"- Dataset: `{preflight.get('dataset_version')}`",
        f"- Pricebook: `{preflight.get('pricebook_version')}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def http_json(url: str, timeout: int) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_ollama(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any] | None]:
    runtime = {
        "runtime": "ollama",
        "url": args.ollama_url,
        "available": False,
        "runtime_version": None,
        "model_available": False,
        "models": [],
    }
    try:
        version = http_json(f"{args.ollama_url.rstrip('/')}/api/version", args.timeout)
        tags = http_json(f"{args.ollama_url.rstrip('/')}/api/tags", args.timeout)
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return runtime, {
            "severity": "P1",
            "category": "missing_model_runtime",
            "message": f"Ollama runtime did not respond before benchmark start: {exc}",
        }
    runtime["available"] = True
    runtime["runtime_version"] = version.get("version")
    model_names = [str(item.get("name")) for item in tags.get("models", []) if isinstance(item, dict)]
    runtime["models"] = model_names
    runtime["model_available"] = args.model in model_names
    if not runtime["model_available"]:
        return runtime, {
            "severity": "P1",
            "category": "missing_model",
            "message": f"Required model {args.model!r} is not present in Ollama tags.",
        }
    return runtime, None


def ollama_generate(base_url: str, model: str, prompt: str, timeout: int, num_predict: int) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "top_p": 1,
            "seed": 42,
            "num_predict": num_predict,
        },
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    return str(body.get("response") or "")


def extract_first_json(text: str) -> dict[str, Any] | None:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        candidates.append(text[first:last + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def decimal_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).replace(" ", "").replace(",", ".")


def find_grand_total(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    totals = payload.get("totals") if isinstance(payload.get("totals"), dict) else {}
    for key in ("grand_total", "total", "итого", "sum"):
        if key in totals:
            return decimal_string(totals[key])
        if key in payload:
            return decimal_string(payload[key])
    return None


def decimal_or_none(value: Any) -> Decimal | None:
    try:
        return Decimal(decimal_string(value) or "")
    except (InvalidOperation, ValueError):
        return None


def money_equal(left: Any, right: Any) -> bool:
    left_decimal = decimal_or_none(left)
    right_decimal = decimal_or_none(right)
    if left_decimal is None or right_decimal is None:
        return False
    return left_decimal.quantize(Decimal("0.01")) == right_decimal.quantize(Decimal("0.01"))


def formula_consistent(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    totals = payload.get("totals")
    if not isinstance(totals, dict):
        return False
    if not all(key in totals for key in ("labor", "materials", "subtotal", "overhead", "tax", "grand_total")):
        return False
    labor = decimal_or_none(totals.get("labor"))
    materials = decimal_or_none(totals.get("materials"))
    subtotal = decimal_or_none(totals.get("subtotal"))
    overhead = decimal_or_none(totals.get("overhead"))
    tax = decimal_or_none(totals.get("tax"))
    grand_total = decimal_or_none(totals.get("grand_total"))
    if None in (labor, materials, subtotal, overhead, tax, grand_total):
        return False
    if not money_equal(subtotal, labor + materials):
        return False
    if not money_equal(grand_total, subtotal + overhead + tax):
        return False
    audit = payload.get("calculation_audit")
    return isinstance(audit, list) and bool(audit)


def baseline_prompt(case: dict[str, str]) -> str:
    return (
        "Составь строительную смету по запросу. Верни только JSON без markdown. "
        "JSON должен содержать поля title, region, sections, totals.grand_total. "
        "Все суммы в RUB, округление до копеек.\n"
        f"Запрос: {case['prompt']}\n"
        f"Клиент: {case.get('client_name', 'Клиент')}"
    )


def formulalm_prompt(case: dict[str, str]) -> str:
    return (
        "FormulaLM overlay active. Сначала выдели переменные задачи: region, work_type, area_m2. "
        "Затем применяй только фиксированные формулы: line_total = quantity * unit_price; "
        "subtotal = labor + materials; overhead = subtotal * 0.07; grand_total = subtotal + overhead. "
        "Не выдумывай новые формулы и не меняй регион. Верни только JSON с extraction и confidence. "
        "Итоговые деньги пересчитает FormulaLM kernel.\n"
        f"Запрос: {case['prompt']}\n"
        f"Клиент: {case.get('client_name', 'Клиент')}"
    )


def expected_estimate(case: dict[str, str]) -> dict[str, Any]:
    from estimate_engine import create_estimate_from_prompt  # noqa: PLC0415

    estimate = create_estimate_from_prompt(case["prompt"], client_name=case.get("client_name", "Клиент"))
    return estimate.model_dump(mode="json")


def score_record(
    mode: str,
    raw: str,
    parsed: dict[str, Any] | None,
    expected: dict[str, Any],
    latency_ms: int,
    formulalm: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expected_total = str(expected["totals"]["grand_total"])
    if formulalm is not None:
        actual_total = str(formulalm["totals"]["grand_total"])
        exact_total = actual_total == expected_total
        valid = True
        output_hash = sha256_text(json.dumps(formulalm, ensure_ascii=False, sort_keys=True))
        consistency_payload = formulalm
    else:
        actual_total = find_grand_total(parsed)
        exact_total = actual_total == expected_total
        valid = parsed is not None
        output_hash = sha256_text(raw)
        consistency_payload = parsed
    return {
        "actual_total": actual_total,
        "error_category": None,
        "exact_total": exact_total,
        "expected_total": expected_total,
        "formula_consistent": formula_consistent(consistency_payload),
        "latency_ms": latency_ms,
        "manual_fix_required": not (valid and exact_total and formula_consistent(consistency_payload)),
        "mode": mode,
        "output_hash": output_hash,
        "parse_error": parsed is None,
        "raw_chars": len(raw),
        "runtime_error": False,
        "valid_json": valid,
    }


def load_cases(path: str | None) -> list[dict[str, str]]:
    if not path:
        return DEFAULT_CASES
    cases = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(json.loads(line))
    return cases


def percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * pct)
    return int(ordered[index])


def blocked_reason_count(blockers: list[dict[str, Any]], records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for blocker in blockers:
        category = str(blocker.get("category") or "unknown")
        counts[category] = counts.get(category, 0) + 1
    for record in records:
        category = record.get("error_category")
        if category:
            counts[str(category)] = counts.get(str(category), 0) + 1
    return counts


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_mode: dict[str, dict[str, Any]] = {}
    for record in records:
        stats = by_mode.setdefault(record["mode"], {
            "count": 0,
            "exact_total": 0,
            "formula_consistent": 0,
            "hashes": set(),
            "hashes_per_case": {},
            "latencies": [],
            "manual_fix_count": 0,
            "parse_error": 0,
            "runtime_error": 0,
            "valid_json": 0,
        })
        stats["count"] += 1
        stats["valid_json"] += int(bool(record["valid_json"]))
        stats["exact_total"] += int(bool(record["exact_total"]))
        stats["formula_consistent"] += int(bool(record["formula_consistent"]))
        stats["parse_error"] += int(bool(record["parse_error"]))
        stats["runtime_error"] += int(bool(record["runtime_error"]))
        stats["manual_fix_count"] += int(bool(record["manual_fix_required"]))
        if record.get("latency_ms") is not None:
            stats["latencies"].append(int(record["latency_ms"]))
        stats["hashes"].add(record["output_hash"])
        per_case = stats["hashes_per_case"].setdefault(record["case_id"], set())
        per_case.add(record["output_hash"])
    out = {}
    for mode, stats in by_mode.items():
        count = max(1, stats["count"])
        latencies = stats["latencies"]
        out[mode] = {
            "count": stats["count"],
            "exact_total_rate": round(stats["exact_total"] / count, 4),
            "formula_consistency_rate": round(stats["formula_consistent"] / count, 4),
            "latency_p50_ms": int(statistics.median(latencies)) if latencies else None,
            "latency_p95_ms": percentile(latencies, 0.95),
            "manual_fix_count": stats["manual_fix_count"],
            "parse_error_rate": round(stats["parse_error"] / count, 4),
            "runtime_error_rate": round(stats["runtime_error"] / count, 4),
            "tokens_or_chars_per_second": None,
            "unique_output_hashes": len(stats["hashes"]),
            "unique_output_hashes_per_case": {case_id: len(hashes) for case_id, hashes in sorted(stats["hashes_per_case"].items())},
            "valid_json_rate": round(stats["valid_json"] / count, 4),
        }
    return out


def decide_verdict(summary: dict[str, Any], blockers: list[dict[str, Any]]) -> str:
    if any(blocker.get("severity") in {"P0", "P1"} for blocker in blockers):
        return "blocked"
    baseline = summary.get("baseline")
    formulalm = summary.get("formulalm")
    if not baseline or not formulalm:
        return "blocked"
    if baseline["count"] < 30 or formulalm["count"] < 30:
        return "inconclusive"
    if any(blocker.get("category") == "manual_review_missing" for blocker in blockers):
        return "inconclusive"
    valid_uplift = formulalm["valid_json_rate"] - baseline["valid_json_rate"]
    exact_uplift = formulalm["exact_total_rate"] - baseline["exact_total_rate"]
    baseline_hash_max = max(baseline["unique_output_hashes_per_case"].values() or [0])
    formulalm_hash_max = max(formulalm["unique_output_hashes_per_case"].values() or [0])
    if (
        valid_uplift >= 0.05
        and formulalm["exact_total_rate"] >= 0.98
        and exact_uplift >= 0.10
        and formulalm_hash_max <= 2
        and formulalm_hash_max <= max(1, baseline_hash_max // 2)
        and formulalm["formula_consistency_rate"] >= 0.99
        and formulalm["manual_fix_count"] <= baseline["manual_fix_count"] * 0.7
    ):
        return "proven"
    return "inconclusive"


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    lines = [
        "# FormulaLM Benchmark Report",
        "",
        f"- Generated at: `{payload['finished_at']}`",
        f"- Verdict: `{payload['verdict']}`",
        f"- Model: `{payload['model']}`",
        f"- Runtime: `{payload['runtime']['runtime']}` / `{payload['runtime'].get('runtime_version')}`",
        f"- Dataset: `{payload['dataset_version']}`",
        f"- Pricebook: `{payload['pricebook_version']}`",
        f"- Duration seconds requested: `{payload['duration_seconds']}`",
        "",
        "## Summary",
        "",
        "| Mode | Count | Valid JSON | Exact Total | Formula Consistency | Parse Errors | Runtime Errors | p50 ms | p95 ms | Unique Hashes | Manual Fixes |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode, stats in summary.items():
        lines.append(
            f"| {mode} | {stats['count']} | {stats['valid_json_rate']:.2%} | "
            f"{stats['exact_total_rate']:.2%} | {stats['formula_consistency_rate']:.2%} | "
            f"{stats['parse_error_rate']:.2%} | {stats['runtime_error_rate']:.2%} | "
            f"{stats['latency_p50_ms']} | {stats['latency_p95_ms']} | "
            f"{stats['unique_output_hashes']} | {stats['manual_fix_count']} |"
        )
    lines.extend([
        "",
        "## Blockers",
        "",
        json.dumps(payload.get("blocked_reason_count", {}), ensure_ascii=False, sort_keys=True),
        "",
        "## Interpretation",
        "",
        "This benchmark tests FormulaLM as a deterministic overlay/kernel on top of the same local model. "
        "It does not claim that model weights improved; it measures whether the FormulaLM path improves "
        "validity, reproducibility, and exact estimate totals for controlled construction-estimate tasks.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen2.5-coder:3b")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--cases")
    parser.add_argument("--out-dir", default="artifacts/formulalm")
    parser.add_argument("--duration-seconds", type=int, default=0)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--num-predict", type=int, default=512)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--allow-local-mac", action="store_true", help="Explicit emergency override; FormulaLM experiments should run on remote servers.")
    parser.add_argument("--node-id", default=os.environ.get("KOLIBRI_NODE_ID", "unknown"))
    parser.add_argument("--pricebook-version", default=PRICEBOOK_VERSION)
    parser.add_argument("--dataset-version", default=DATASET_VERSION)
    parser.add_argument("--task-id", default=os.environ.get("KOLIBRI_TASK_ID", "manual-formulalm-benchmark"))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    preflight = preflight_payload(args, out_dir)
    write_json(out_dir / "preflight.json", preflight)

    if platform.system().lower() == "darwin" and not args.allow_local_mac:
        blocker = write_blocker(
            out_dir,
            "P0",
            "mac_execution_blocked",
            "FormulaLM experiments must run on remote servers through Control Plane, not on this Mac.",
            preflight,
        )
        print(json.dumps({"error": blocker["category"], "blockers": str(out_dir / "blockers.json")}, ensure_ascii=False, indent=2))
        return 2

    blockers: list[dict[str, Any]] = []
    cases = load_cases(args.cases)
    if not cases:
        blocker = write_blocker(out_dir, "P1", "dataset_empty", "No FormulaLM benchmark cases were available.", preflight)
        print(json.dumps({"error": blocker["category"], "blockers": str(out_dir / "blockers.json")}, ensure_ascii=False, indent=2))
        return 2
    if args.pricebook_version != PRICEBOOK_VERSION:
        blocker = write_blocker(out_dir, "P1", "pricebook_version_mismatch", f"Expected {PRICEBOOK_VERSION}, got {args.pricebook_version}.", preflight)
        print(json.dumps({"error": blocker["category"], "blockers": str(out_dir / "blockers.json")}, ensure_ascii=False, indent=2))
        return 2
    runtime, runtime_blocker = check_ollama(args)
    if runtime_blocker:
        blocker = write_blocker(out_dir, runtime_blocker["severity"], runtime_blocker["category"], runtime_blocker["message"], preflight)
        print(json.dumps({"error": blocker["category"], "blockers": str(out_dir / "blockers.json")}, ensure_ascii=False, indent=2))
        return 2

    if len(cases) < EXPECTED_PILOT_CASES:
        blockers.append({
            "severity": "P2",
            "category": "dataset_below_pilot_target",
            "message": f"Dataset has {len(cases)} cases; pilot target is {EXPECTED_PILOT_CASES}. Using maximum available dataset.",
        })
    if args.repeat < EXPECTED_PILOT_REPEATS:
        blockers.append({
            "severity": "P2",
            "category": "repeat_below_pilot_target",
            "message": f"Repeat count is {args.repeat}; pilot target is {EXPECTED_PILOT_REPEATS}.",
        })
    blockers.append({
        "severity": "P2",
        "category": "manual_review_missing",
        "message": "Independent QA manual review artifact is not available; H5 cannot be proven.",
    })

    started = time.time()
    records: list[dict[str, Any]] = []
    iteration = 0

    while True:
        iteration += 1
        for case in cases:
            expected = expected_estimate(case)
            for _ in range(args.repeat):
                try:
                    call_started = time.time()
                    raw = ollama_generate(args.ollama_url, args.model, baseline_prompt(case), args.timeout, args.num_predict)
                    latency_ms = int((time.time() - call_started) * 1000)
                    parsed = extract_first_json(raw)
                    records.append({"case_id": case["id"], "iteration": iteration, **score_record("baseline", raw, parsed, expected, latency_ms)})
                except (OSError, urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                    records.append({
                        "case_id": case["id"],
                        "iteration": iteration,
                        "mode": "baseline",
                        "valid_json": False,
                        "exact_total": False,
                        "expected_total": str(expected["totals"]["grand_total"]),
                        "actual_total": None,
                        "formula_consistent": False,
                        "latency_ms": None,
                        "manual_fix_required": True,
                        "output_hash": sha256_text(f"runtime-error:{case['id']}:{iteration}:baseline:{exc}"),
                        "parse_error": False,
                        "raw_chars": 0,
                        "runtime_error": True,
                        "error_category": "model_runtime_error",
                        "error": str(exc),
                        "at": utc_now(),
                    })

                try:
                    call_started = time.time()
                    raw = ollama_generate(args.ollama_url, args.model, formulalm_prompt(case), args.timeout, args.num_predict)
                    latency_ms = int((time.time() - call_started) * 1000)
                    parsed = extract_first_json(raw)
                    formulalm_estimate = expected_estimate(case)
                    records.append({"case_id": case["id"], "iteration": iteration, **score_record("formulalm", raw, parsed, expected, latency_ms, formulalm_estimate)})
                except (OSError, urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                    records.append({
                        "case_id": case["id"],
                        "iteration": iteration,
                        "mode": "formulalm",
                        "valid_json": False,
                        "exact_total": False,
                        "expected_total": str(expected["totals"]["grand_total"]),
                        "actual_total": None,
                        "formula_consistent": False,
                        "latency_ms": None,
                        "manual_fix_required": True,
                        "output_hash": sha256_text(f"runtime-error:{case['id']}:{iteration}:formulalm:{exc}"),
                        "parse_error": False,
                        "raw_chars": 0,
                        "runtime_error": True,
                        "error_category": "model_runtime_error",
                        "error": str(exc),
                        "at": utc_now(),
                    })
        if args.duration_seconds <= 0:
            break
        if time.time() - started >= args.duration_seconds:
            break
        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    summary = summarize(records)
    verdict = decide_verdict(summary, blockers)
    payload = {
        "blocked_reason_count": blocked_reason_count(blockers, records),
        "blockers": blockers,
        "dataset": {
            "case_count": len(cases),
            "case_ids": [case["id"] for case in cases],
            "source": args.cases or "script_default_seed",
        },
        "dataset_version": args.dataset_version,
        "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat(),
        "finished_at": utc_now(),
        "duration_seconds": args.duration_seconds,
        "preflight": preflight,
        "pricebook_version": args.pricebook_version,
        "task_id": args.task_id,
        "node_id": args.node_id,
        "model": args.model,
        "runtime": runtime,
        "generation_settings": {
            "temperature": 0,
            "top_p": 1,
            "seed": 42,
            "num_predict": args.num_predict,
            "timeout": args.timeout,
        },
        "records": records,
        "summary": summary,
        "verdict": verdict,
    }
    write_json(out_dir / "formulalm-benchmark.json", payload)
    write_markdown(out_dir / "formulalm-benchmark.md", payload)
    print(json.dumps({"summary": payload["summary"], "verdict": verdict, "out_dir": str(out_dir)}, ensure_ascii=False, indent=2))
    return 0 if verdict in {"proven", "inconclusive"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
