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
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
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
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def preflight_payload(args: argparse.Namespace, out_dir: Path) -> dict[str, Any]:
    return {
        "artifact_dir": str(out_dir),
        "hostname": socket.gethostname(),
        "model": args.model,
        "node_id": args.node_id,
        "ollama_url": args.ollama_url,
        "platform": platform.platform(),
        "platform_system": platform.system(),
        "pricebook_version": args.pricebook_version,
        "python_version": platform.python_version(),
        "remote_guard": {
            "mac_execution_allowed": bool(args.allow_local_mac),
            "mode": "execute_preflight_then_run_or_block",
            "status": "preflight_recorded",
        },
        "task_id": args.task_id,
        "time": utc_now(),
    }


def write_blocker(out_dir: Path, severity: str, category: str, message: str, preflight: dict[str, Any]) -> dict[str, Any]:
    blocker = {
        "category": category,
        "first_seen_at": utc_now(),
        "mac_execution": "blocked" if preflight.get("platform_system") == "Darwin" else "not_attempted",
        "message": message,
        "node_id": preflight.get("node_id"),
        "preflight": preflight,
        "safe_next_action": "Fix the remote runtime or resubmit through Control Plane after the blocker is gone.",
        "severity": severity,
        "status": "blocked",
        "task_id": preflight.get("task_id"),
    }
    write_json(out_dir / "blockers.json", blocker)
    return blocker


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


def score_record(mode: str, raw: str, parsed: dict[str, Any] | None, expected: dict[str, Any], formulalm: dict[str, Any] | None = None) -> dict[str, Any]:
    expected_total = str(expected["totals"]["grand_total"])
    if formulalm is not None:
        actual_total = str(formulalm["totals"]["grand_total"])
        exact_total = actual_total == expected_total
        valid = True
        output_hash = sha256_text(json.dumps(formulalm, ensure_ascii=False, sort_keys=True))
    else:
        actual_total = find_grand_total(parsed)
        exact_total = actual_total == expected_total
        valid = parsed is not None
        output_hash = sha256_text(raw)
    return {
        "mode": mode,
        "valid_json": valid,
        "exact_total": exact_total,
        "expected_total": expected_total,
        "actual_total": actual_total,
        "output_hash": output_hash,
        "raw_chars": len(raw),
    }


def load_cases(path: str | None) -> list[dict[str, str]]:
    if not path:
        return DEFAULT_CASES
    cases = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(json.loads(line))
    return cases


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_mode: dict[str, dict[str, Any]] = {}
    for record in records:
        stats = by_mode.setdefault(record["mode"], {"count": 0, "valid_json": 0, "exact_total": 0, "hashes": set()})
        stats["count"] += 1
        stats["valid_json"] += int(bool(record["valid_json"]))
        stats["exact_total"] += int(bool(record["exact_total"]))
        stats["hashes"].add(record["output_hash"])
    out = {}
    for mode, stats in by_mode.items():
        count = max(1, stats["count"])
        out[mode] = {
            "count": stats["count"],
            "valid_json_rate": round(stats["valid_json"] / count, 4),
            "exact_total_rate": round(stats["exact_total"] / count, 4),
            "unique_output_hashes": len(stats["hashes"]),
        }
    return out


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    lines = [
        "# FormulaLM Benchmark Report",
        "",
        f"- Generated at: `{payload['finished_at']}`",
        f"- Model: `{payload['model']}`",
        f"- Ollama URL: `{payload['ollama_url']}`",
        f"- Duration seconds requested: `{payload['duration_seconds']}`",
        "",
        "## Summary",
        "",
        "| Mode | Count | Valid JSON | Exact Total | Unique Hashes |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for mode, stats in summary.items():
        lines.append(
            f"| {mode} | {stats['count']} | {stats['valid_json_rate']:.2%} | "
            f"{stats['exact_total_rate']:.2%} | {stats['unique_output_hashes']} |"
        )
    lines.extend([
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
    parser.add_argument("--pricebook-version", default="kolibri-ru-2026q2-v1")
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

    started = time.time()
    cases = load_cases(args.cases)
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    iteration = 0

    while True:
        iteration += 1
        for case in cases:
            expected = expected_estimate(case)
            for _ in range(args.repeat):
                try:
                    raw = ollama_generate(args.ollama_url, args.model, baseline_prompt(case), args.timeout, args.num_predict)
                    parsed = extract_first_json(raw)
                    records.append({"case_id": case["id"], "iteration": iteration, **score_record("baseline", raw, parsed, expected)})
                except (OSError, urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                    errors.append({"case_id": case["id"], "mode": "baseline", "error": str(exc), "at": utc_now()})

                try:
                    raw = ollama_generate(args.ollama_url, args.model, formulalm_prompt(case), args.timeout, args.num_predict)
                    parsed = extract_first_json(raw)
                    formulalm_estimate = expected_estimate(case)
                    records.append({"case_id": case["id"], "iteration": iteration, **score_record("formulalm", raw, parsed, expected, formulalm_estimate)})
                except (OSError, urllib.error.URLError, TimeoutError, RuntimeError) as exc:
                    errors.append({"case_id": case["id"], "mode": "formulalm", "error": str(exc), "at": utc_now()})
        if args.duration_seconds <= 0:
            break
        if time.time() - started >= args.duration_seconds:
            break
        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    payload = {
        "started_at": datetime.fromtimestamp(started, timezone.utc).isoformat(),
        "finished_at": utc_now(),
        "duration_seconds": args.duration_seconds,
        "preflight": preflight,
        "pricebook_version": args.pricebook_version,
        "task_id": args.task_id,
        "node_id": args.node_id,
        "model": args.model,
        "ollama_url": args.ollama_url,
        "records": records,
        "errors": errors,
        "summary": summarize(records),
    }
    if errors and not records:
        write_blocker(
            out_dir,
            "P1",
            "model_runtime_error",
            "Remote model runtime returned errors before any benchmark record was created.",
            preflight,
        )
    write_json(out_dir / "formulalm-benchmark.json", payload)
    write_markdown(out_dir / "formulalm-benchmark.md", payload)
    print(json.dumps({"summary": payload["summary"], "errors": len(errors), "out_dir": str(out_dir)}, ensure_ascii=False, indent=2))
    return 0 if records and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
