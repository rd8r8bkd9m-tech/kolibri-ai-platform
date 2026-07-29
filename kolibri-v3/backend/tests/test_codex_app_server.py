from __future__ import annotations

import json
from pathlib import Path
import sys

from app.codex_app_server import (
    CodexAppServerRuntime,
    _AUTHENTICATED_PREVIEW_MODELS,
)


FAKE_APP_SERVER = r"""
import json
from pathlib import Path
import sys

log_path = Path(sys.argv[1])
thread_number = 0
turn_number = 0

def emit(value):
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")), flush=True)

def record(value):
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")

emit({"timestamp": "ignored-log-line", "level": "INFO"})
for line in sys.stdin:
    value = json.loads(line)
    method = value.get("method")
    if method:
        record({"method": method, "params": value.get("params")})
    request_id = value.get("id")
    if method == "initialize":
        emit({"id": request_id, "result": {"userAgent": "fake"}})
    elif method == "initialized":
        continue
    elif method == "account/read":
        emit({
            "id": request_id,
            "result": {
                "account": {"type": "apiKey"},
                "requiresOpenaiAuth": True,
            },
        })
    elif method == "thread/start":
        thread_number += 1
        emit({
            "id": request_id,
            "result": {
                "thread": {"id": f"thread-{thread_number}"},
                "model": "fake",
            },
        })
    elif method == "turn/start":
        turn_number += 1
        turn_id = f"turn-{turn_number}"
        prompt = value["params"]["input"][0]["text"]
        result_text = json.dumps(
            {"received": prompt},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        emit({
            "id": request_id,
            "result": {
                "turn": {
                    "id": turn_id,
                    "items": [],
                    "status": "inProgress",
                }
            },
        })
        command_item = {
            "id": f"command-{turn_number}",
            "type": "commandExecution",
            "command": "pwd",
            "cwd": value["params"]["threadId"],
            "status": "inProgress",
        }
        emit({
            "method": "item/started",
            "params": {
                "threadId": value["params"]["threadId"],
                "turnId": turn_id,
                "item": command_item,
            },
        })
        emit({
            "method": "item/completed",
            "params": {
                "threadId": value["params"]["threadId"],
                "turnId": turn_id,
                "completedAtMs": 1,
                "item": {
                    **command_item,
                    "status": "completed",
                    "exitCode": 0,
                    "durationMs": 1,
                },
            },
        })
        emit({
            "method": "item/agentMessage/delta",
            "params": {
                "threadId": value["params"]["threadId"],
                "turnId": turn_id,
                "itemId": f"item-{turn_number}",
                "delta": result_text,
            },
        })
        emit({
            "method": "item/completed",
            "params": {
                "threadId": value["params"]["threadId"],
                "turnId": turn_id,
                "completedAtMs": 1,
                "item": {
                    "id": f"item-{turn_number}",
                    "type": "agentMessage",
                    "phase": "final_answer",
                    "text": result_text,
                },
            },
        })
        emit({
            "method": "turn/completed",
            "params": {
                "threadId": value["params"]["threadId"],
                "turn": {
                    "id": turn_id,
                    "items": [],
                    "status": "completed",
                    "error": None,
                },
            },
        })
"""


def _runtime(tmp_path: Path) -> tuple[CodexAppServerRuntime, Path]:
    script = tmp_path / "fake_app_server.py"
    log = tmp_path / "protocol.jsonl"
    script.write_text(FAKE_APP_SERVER, encoding="utf-8")
    return (
        CodexAppServerRuntime(
            runtime_root=tmp_path / "runtime",
            command=(sys.executable, "-u", str(script), str(log)),
            model="fake-model",
            effort="none",
        ),
        log,
    )


def _complete(
    runtime: CodexAppServerRuntime,
    *,
    tenant_id: str,
    product_thread_id: str,
    initial_prompt: str,
    followup_prompt: str,
    on_delta=None,
    execution_profile: str = "default",
    model: str | None = None,
    effort: str | None = None,
    service_tier: str | None = None,
    on_activity=None,
    workspace_root: Path | None = None,
    sandbox: str = "read-only",
    approval_policy: str = "never",
    approvals_reviewer: str | None = None,
) -> dict[str, str]:
    value = runtime.complete(
        tenant_id=tenant_id,
        product_thread_id=product_thread_id,
        initial_prompt=initial_prompt,
        followup_prompt=followup_prompt,
        output_schema={"type": "object"},
        instructions="Return JSON only.",
        timeout=5,
        on_delta=on_delta,
        execution_profile=execution_profile,
        model=model,
        effort=effort,
        service_tier=service_tier,
        on_activity=on_activity,
        workspace_root=workspace_root,
        sandbox=sandbox,
        approval_policy=approval_policy,
        approvals_reviewer=approvals_reviewer,
    )
    return json.loads(value)


def test_live_catalog_empty_or_invalid_tiers_override_preview_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime = CodexAppServerRuntime(
        runtime_root=tmp_path / "runtime",
        command=("fake-codex",),
    )
    monkeypatch.setattr(runtime, "start", lambda: None)
    monkeypatch.setattr(
        runtime,
        "_require_account",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        runtime,
        "_list_bundled_models",
        lambda **_kwargs: (),
    )
    monkeypatch.setattr(
        runtime,
        "_request",
        lambda *_args, **_kwargs: {
            "data": [
                {
                    "model": "gpt-5.6-sol",
                    "displayName": "GPT-5.6 Sol",
                    "description": "Live authority.",
                    "defaultReasoningEffort": "low",
                    "supportedReasoningEfforts": [
                        {
                            "reasoningEffort": "low",
                            "description": "Fast",
                        }
                    ],
                    "serviceTiers": [
                        {
                            "id": "Priority.Fast",
                            "name": "Invalid",
                            "description": "Must be filtered.",
                        }
                    ],
                }
            ]
        },
    )

    models = runtime.list_models(timeout=1.0)

    selected = next(model for model in models if model.id == "gpt-5.6-sol")
    assert selected.description == "Live authority."
    assert selected.service_tiers == ()


def test_bundled_catalog_exposes_executable_gpt_56_variants(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime = CodexAppServerRuntime(
        runtime_root=tmp_path / "runtime",
        command=("codex", "app-server", "--stdio"),
    )
    calls: list[tuple[str, ...]] = []
    payload = {
        "models": [
            {
                "slug": "gpt-5.6-sol",
                "display_name": "GPT-5.6-Sol",
                "description": "Latest frontier agentic coding model.",
                "default_reasoning_level": "low",
                "supported_reasoning_levels": [
                    {"effort": "low", "description": "Fast"},
                    {"effort": "ultra", "description": "Delegated"},
                ],
                "visibility": "list",
                "supported_in_api": True,
                "service_tiers": [
                    {
                        "id": "priority",
                        "name": "Fast",
                        "description": "1.5x speed, increased usage",
                    }
                ],
                "upgrade": None,
            },
            {
                "slug": "gpt-5.6-luna",
                "display_name": "GPT-5.6-Luna",
                "description": "Fast and affordable agentic coding model.",
                "default_reasoning_level": "medium",
                "supported_reasoning_levels": [
                    {"effort": "low", "description": "Fast"},
                    {"effort": "medium", "description": "Balanced"},
                    {"effort": "max", "description": "Maximum"},
                ],
                "visibility": "list",
                "supported_in_api": True,
                "service_tiers": [],
                "upgrade": None,
            },
            {
                "slug": "hidden-model",
                "display_name": "Hidden",
                "description": "",
                "default_reasoning_level": "low",
                "supported_reasoning_levels": [
                    {"effort": "low", "description": ""},
                ],
                "visibility": "hide",
                "supported_in_api": True,
            },
        ]
    }

    class Completed:
        returncode = 0
        stdout = json.dumps(payload)

    def fake_run(command, **_kwargs):
        calls.append(tuple(command))
        return Completed()

    monkeypatch.setattr(
        "app.codex_app_server.subprocess.run",
        fake_run,
    )

    models = runtime._list_bundled_models(timeout=1.0)
    assert [model.id for model in models] == [
        "gpt-5.6-sol",
        "gpt-5.6-luna",
    ]
    assert models[0].supported_reasoning_efforts[-1][0] == "ultra"
    assert models[0].service_tiers == (
        ("priority", "Fast", "1.5x speed, increased usage"),
    )
    assert [item[0] for item in models[1].supported_reasoning_efforts] == [
        "low",
        "medium",
        "max",
    ]
    assert runtime._list_bundled_models(timeout=1.0) is models
    assert calls == [("codex", "debug", "models", "--bundled")]


def test_authenticated_preview_catalog_includes_all_gpt_56_variants() -> None:
    assert [
        (model.id, model.default_reasoning_effort)
        for model in _AUTHENTICATED_PREVIEW_MODELS
    ] == [
        ("gpt-5.6-sol", "low"),
        ("gpt-5.6-terra", "medium"),
        ("gpt-5.6-luna", "medium"),
    ]
    assert [
        effort
        for effort, _description in
        _AUTHENTICATED_PREVIEW_MODELS[0].supported_reasoning_efforts
    ] == ["low", "medium", "high", "xhigh", "max", "ultra"]
    assert [
        effort
        for effort, _description in
        _AUTHENTICATED_PREVIEW_MODELS[2].supported_reasoning_efforts
    ] == ["low", "medium", "high", "xhigh", "max"]
    assert all(
        model.service_tiers
        == (("priority", "Fast", "1.5x speed, increased usage"),)
        for model in _AUTHENTICATED_PREVIEW_MODELS
    )


def test_subprocess_environment_forwards_only_bounded_proxy_configuration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime = CodexAppServerRuntime(
        runtime_root=tmp_path / "runtime",
        command=("codex", "app-server", "--stdio"),
    )
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:11081")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-forwarded")

    environment = runtime._subprocess_environment()

    assert environment["HTTPS_PROXY"] == "http://127.0.0.1:11081"
    assert environment["NO_PROXY"] == "127.0.0.1,localhost"
    assert "OPENAI_API_KEY" not in environment


def test_developer_turn_uses_workspace_write_and_streams_activity(
    tmp_path: Path,
) -> None:
    runtime, log = _runtime(tmp_path)
    activities: list[tuple[str, dict[str, object]]] = []
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    try:
        assert _complete(
            runtime,
            tenant_id="tenant-owner",
            product_thread_id="chat-developer",
            initial_prompt="inspect repository",
            followup_prompt="inspect repository",
            execution_profile="developer",
            on_activity=lambda phase, item: activities.append((phase, item)),
            workspace_root=workspace,
            sandbox="workspace-write",
            approval_policy="on-request",
            approvals_reviewer="auto_review",
        ) == {"received": "inspect repository"}
    finally:
        runtime.stop()

    records = [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
    ]
    [thread_start] = [
        record for record in records if record["method"] == "thread/start"
    ]
    assert thread_start["params"]["cwd"] == str(workspace)
    assert thread_start["params"]["sandbox"] == "workspace-write"
    assert thread_start["params"]["approvalPolicy"] == "on-request"
    assert thread_start["params"]["approvalsReviewer"] == "auto_review"
    assert thread_start["params"]["runtimeWorkspaceRoots"] == [str(workspace)]
    assert "environments" not in thread_start["params"]
    assert [phase for phase, _item in activities] == [
        "started",
        "completed",
    ]
    assert all(
        item["type"] == "commandExecution" for _phase, item in activities
    )
    [turn_start] = [
        record for record in records if record["method"] == "turn/start"
    ]
    assert turn_start["params"]["approvalPolicy"] == "on-request"
    assert turn_start["params"]["approvalsReviewer"] == "auto_review"


def test_one_process_reuses_one_ephemeral_thread_per_product_chat(
    tmp_path: Path,
) -> None:
    runtime, log = _runtime(tmp_path)
    try:
        runtime.start()
        assert runtime.is_running
        assert _complete(
            runtime,
            tenant_id="tenant-a",
            product_thread_id="chat-a",
            initial_prompt="full history A",
            followup_prompt="latest A1",
        ) == {"received": "full history A"}
        assert _complete(
            runtime,
            tenant_id="tenant-a",
            product_thread_id="chat-a",
            initial_prompt="must not be repeated",
            followup_prompt="latest A2",
        ) == {"received": "latest A2"}
        assert _complete(
            runtime,
            tenant_id="tenant-a",
            product_thread_id="chat-b",
            initial_prompt="full history B",
            followup_prompt="latest B1",
        ) == {"received": "full history B"}
    finally:
        runtime.stop()

    records = [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
    ]
    methods = [record["method"] for record in records]
    assert methods.count("initialize") == 1
    assert methods.count("thread/start") == 2
    assert methods.count("turn/start") == 3
    assert methods.count("account/read") == 1
    thread_starts = [
        record["params"]
        for record in records
        if record["method"] == "thread/start"
    ]
    assert all(params["ephemeral"] is True for params in thread_starts)
    assert all(params["approvalPolicy"] == "never" for params in thread_starts)
    assert all(params["sandbox"] == "read-only" for params in thread_starts)
    assert all(params["dynamicTools"] == [] for params in thread_starts)


def test_turn_deltas_are_forwarded_without_waiting_for_completion(
    tmp_path: Path,
) -> None:
    runtime, _log = _runtime(tmp_path)
    deltas: list[str] = []
    try:
        result = _complete(
            runtime,
            tenant_id="tenant-a",
            product_thread_id="chat-stream",
            initial_prompt="stream me",
            followup_prompt="latest",
            on_delta=deltas.append,
        )
    finally:
        runtime.stop()

    assert result == {"received": "stream me"}
    assert "".join(deltas) == '{"received":"stream me"}'


def test_execution_profiles_keep_chat_and_estimate_threads_separate(
    tmp_path: Path,
) -> None:
    runtime, log = _runtime(tmp_path)
    try:
        for profile in ("chat", "estimate", "chat"):
            _complete(
                runtime,
                tenant_id="tenant-a",
                product_thread_id="shared-product-thread",
                initial_prompt=f"initial {profile}",
                followup_prompt=f"followup {profile}",
                execution_profile=profile,
                model="fast" if profile == "chat" else "quality",
                effort="none" if profile == "chat" else "low",
            )
    finally:
        runtime.stop()

    records = [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
    ]
    starts = [
        record["params"]
        for record in records
        if record["method"] == "thread/start"
    ]
    assert [item["model"] for item in starts] == ["fast", "quality"]
    turns = [
        record["params"]
        for record in records
        if record["method"] == "turn/start"
    ]
    assert [item["effort"] for item in turns] == ["none", "low", "none"]
    assert turns[0]["threadId"] == turns[2]["threadId"]
    assert turns[0]["threadId"] != turns[1]["threadId"]


def test_service_tier_is_sent_and_isolates_cached_threads(
    tmp_path: Path,
) -> None:
    runtime, log = _runtime(tmp_path)
    try:
        for service_tier in ("priority", "priority", None):
            _complete(
                runtime,
                tenant_id="tenant-a",
                product_thread_id="tiered-product-thread",
                initial_prompt=f"initial {service_tier}",
                followup_prompt=f"followup {service_tier}",
                execution_profile="chat",
                model="tiered-model",
                effort="high",
                service_tier=service_tier,
            )
    finally:
        runtime.stop()

    records = [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
    ]
    starts = [
        record["params"]
        for record in records
        if record["method"] == "thread/start"
    ]
    assert len(starts) == 2
    assert starts[0]["serviceTier"] == "priority"
    assert "serviceTier" not in starts[1]
    turns = [
        record["params"]
        for record in records
        if record["method"] == "turn/start"
    ]
    assert [item.get("serviceTier") for item in turns] == [
        "priority",
        "priority",
        None,
    ]
    assert turns[0]["threadId"] == turns[1]["threadId"]
    assert turns[0]["threadId"] != turns[2]["threadId"]


def test_access_policy_isolates_cached_developer_threads(
    tmp_path: Path,
) -> None:
    runtime, log = _runtime(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    try:
        _complete(
            runtime,
            tenant_id="tenant-owner",
            product_thread_id="developer-thread",
            initial_prompt="auto",
            followup_prompt="auto",
            execution_profile="developer",
            workspace_root=workspace,
            sandbox="workspace-write",
            approval_policy="on-request",
            approvals_reviewer="auto_review",
        )
        _complete(
            runtime,
            tenant_id="tenant-owner",
            product_thread_id="developer-thread",
            initial_prompt="full",
            followup_prompt="full",
            execution_profile="developer",
            workspace_root=workspace,
            sandbox="danger-full-access",
            approval_policy="never",
        )
    finally:
        runtime.stop()

    records = [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
    ]
    starts = [
        record["params"]
        for record in records
        if record["method"] == "thread/start"
    ]
    assert len(starts) == 2
    assert [
        (
            item["sandbox"],
            item["approvalPolicy"],
            item.get("approvalsReviewer"),
        )
        for item in starts
    ] == [
        ("workspace-write", "on-request", "auto_review"),
        ("danger-full-access", "never", None),
    ]


def test_stopped_runtime_can_start_a_fresh_single_process(
    tmp_path: Path,
) -> None:
    runtime, log = _runtime(tmp_path)
    runtime.start()
    runtime.stop()
    assert not runtime.is_running

    try:
        assert _complete(
            runtime,
            tenant_id="tenant-a",
            product_thread_id="chat-a",
            initial_prompt="restored history",
            followup_prompt="latest",
        ) == {"received": "restored history"}
    finally:
        runtime.stop()

    records = [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
    ]
    assert sum(
        record["method"] == "initialize" for record in records
    ) == 2
