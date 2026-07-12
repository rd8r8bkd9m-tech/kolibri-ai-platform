#!/usr/bin/env python3
"""Replay the shared Rust shadow fixture through Python task contracts.

This is a test adapter only. It never starts a listener, connects to Redis or
changes Control Plane state.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_control() -> Any:
    path = ROOT / "ops" / "factory_control.py"
    spec = importlib.util.spec_from_file_location("kolibri_rust_shadow_parity", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("factory_control_import_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.REQUIRE_LEASE_FENCING = True
    return module


def replay(fixture: dict[str, Any]) -> dict[str, Any]:
    control = load_control()
    task_spec = fixture["task"]
    task = control.normalize_task(
        {
            "task_id": task_spec["task_id"],
            "max_attempts": task_spec["max_attempts"],
        }
    )
    attempts_started = 0
    last_attempt_id: str | None = None
    active_fencing_token: int | None = None
    last_fencing_token = 0
    rejected_stale_completions = 0
    result_reference: str | None = None
    result_sha256: str | None = None
    binding_sha256: str | None = None
    completion_fencing_token: int | None = None
    verifier_verdict = "not_run"

    for expected_sequence, event in enumerate(fixture["events"], start=1):
        if event["sequence"] != expected_sequence:
            raise ValueError("sequence_mismatch")
        event_type = event["type"]
        if event_type == "task.created":
            if task["state"] != control.STATE_QUEUED:
                raise ValueError("created_state_mismatch")
            continue
        if event_type == "task.leased":
            if not control.task_has_attempt_budget(task):
                raise ValueError("attempt_budget_exhausted")
            token = int(event["fencing_token"])
            if token <= last_fencing_token:
                raise ValueError("fencing_token_not_monotonic")
            allocated_token = control.allocate_next_fencing_token(task)
            if allocated_token != token:
                raise ValueError("fencing_token_allocation_mismatch")
            attempts_started += 1
            expected_attempt = f"{task['task_id']}-attempt-{attempts_started}"
            if event["attempt_id"] != expected_attempt:
                raise ValueError("attempt_id_mismatch")
            task.update(
                {
                    "state": control.STATE_LEASED,
                    "attempt": attempts_started,
                    "attempt_id": event["attempt_id"],
                    "lease_owner": event["lease_owner"],
                    "lease_until": event["lease_until"],
                }
            )
            active_fencing_token = token
            last_fencing_token = token
            last_attempt_id = event["attempt_id"]
            continue
        if event_type == "task.heartbeat":
            assert_fence(control, task, event, active_fencing_token)
            task["state"] = control.STATE_RUNNING
            task["lease_until"] = event["lease_until"]
            continue
        if event_type == "task.lease_expired":
            assert_fence(control, task, event, active_fencing_token)
            active_fencing_token = None
            task["state"] = (
                control.STATE_QUEUED
                if control.task_has_attempt_budget(task)
                else control.STATE_DEAD
            )
            continue
        if event_type == "task.completion_rejected":
            reason = control.lease_fence_error(task, lease_body(event))
            if reason != event["reason"]:
                raise ValueError("stale_completion_reason_mismatch")
            if event.get("fencing_token") == active_fencing_token and reason is None:
                raise ValueError("matching_completion_was_rejected")
            rejected_stale_completions += 1
            continue
        if event_type == "task.completed":
            assert_fence(control, task, event, active_fencing_token)
            body = {
                **event,
                "node_id": event["lease_owner"].split(":", 1)[0],
                "agent_id": event["lease_owner"].split(":", 1)[1],
            }
            evidence, verifier = control.verify_task_completion(
                task,
                event["result"],
                body,
                event["result_reference"],
            )
            if verifier["verdict"] != "passed":
                raise ValueError(
                    f"completion_verifier_failed:{','.join(verifier['failed_checks'])}"
                )
            if event["result_sha256"] != evidence["result_sha256"]:
                raise ValueError("result_sha256_mismatch")
            if event["binding_sha256"] != evidence["binding_sha256"]:
                raise ValueError("binding_sha256_mismatch")
            declared_verifier = event["verifier"]
            if (
                declared_verifier["schema_version"]
                != control.COMPLETION_VERIFIER_SCHEMA
                or declared_verifier["verifier"] != "control-plane/home"
                or declared_verifier["independent"] is not True
                or declared_verifier["verdict"] != "passed"
                or declared_verifier["fencing_token"] != event["fencing_token"]
                or declared_verifier["result_sha256"] != evidence["result_sha256"]
                or declared_verifier["binding_sha256"] != evidence["binding_sha256"]
            ):
                raise ValueError("declared_verifier_mismatch")
            task["state"] = control.STATE_COMPLETED
            result_reference = event["result_reference"]
            result_sha256 = evidence["result_sha256"]
            binding_sha256 = evidence["binding_sha256"]
            completion_fencing_token = evidence["fencing_token"]
            verifier_verdict = verifier["verdict"]
            active_fencing_token = None
            continue
        raise ValueError(f"unsupported_event:{event_type}")

    events = fixture["events"]
    return {
        "schema_version": "kolibri.task-shadow-summary.v1",
        "mode": "shadow_parity",
        "authoritative": False,
        "authority": "python-control-plane",
        "task_id": task["task_id"],
        "trace_id": fixture["trace_id"],
        "state": task["state"],
        "attempts_started": attempts_started,
        "max_attempts": task["max_attempts"],
        "last_attempt_id": last_attempt_id,
        "event_count": len(events),
        "last_sequence": events[-1]["sequence"] if events else 0,
        "rejected_stale_completions": rejected_stale_completions,
        "result_reference": result_reference,
        "result_sha256": result_sha256,
        "binding_sha256": binding_sha256,
        "completion_fencing_token": completion_fencing_token,
        "verifier_verdict": verifier_verdict,
        "trace_sha256": control.canonical_json_sha256(events),
    }


def assert_fence(
    control: Any,
    task: dict[str, Any],
    event: dict[str, Any],
    active_fencing_token: int | None,
) -> None:
    reason = control.lease_fence_error(task, lease_body(event))
    if reason is not None:
        raise ValueError(reason)
    if event.get("fencing_token") != active_fencing_token:
        raise ValueError("fencing_token_mismatch")


def lease_body(event: dict[str, Any]) -> dict[str, Any]:
    body = dict(event)
    lease_owner = str(event.get("lease_owner") or "")
    node_id, separator, agent_id = lease_owner.partition(":")
    if separator:
        body.setdefault("node_id", node_id)
        body.setdefault("agent_id", agent_id)
    return body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--assert-expected", action="store_true")
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    summary = replay(fixture)
    if args.assert_expected and summary != fixture.get("expected_summary"):
        raise ValueError("python_summary_mismatch")
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
