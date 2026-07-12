from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_agent_host():
    spec = importlib.util.spec_from_file_location(
        "agent_host_native_search_test", ROOT / "ops" / "agent_host.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_args(tmp_path: Path) -> argparse.Namespace:
    manifest = tmp_path / "mesh-peers.json"
    manifest.write_text(
        json.dumps({"peers": [{"node_id": "home", "mesh_ip": "10.99.0.1"}]}),
        encoding="utf-8",
    )
    return argparse.Namespace(
        control_url="http://10.99.0.1:9101",
        mesh_membership_manifest=str(manifest),
        node_id="worker-native-search",
        agent_id="agent-native-search",
        capabilities="generic_implementation",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
    )


def factory_codex_task() -> dict:
    return {
        "task_id": "FACTORY-CODEX-NATIVE-SEARCH",
        "kind": "owner_remote_task",
        "attempt": 1,
        "attempt_id": "attempt-native-search-1",
        "fencing_token": 41,
        "envelope": {
            "kind": "owner_remote_task",
            "runner": "codex",
            "objective": "Find current regional construction prices.",
            "constraints": {"read_only": True},
            "write_scope": [],
            "source": {
                "kind": "kolibri_provider_gateway",
                "control_plane": "home",
                "response_id": "resp-native-search",
            },
        },
    }


def _event(kind: str, query: str, *, result: dict | None = None) -> str:
    item = {
        "type": "web_search",
        "id": "search-1",
        "action": "search",
        "query": query,
    }
    if result is not None:
        item["result"] = result
    return json.dumps({"type": kind, "item": item}, ensure_ascii=False)


def test_live_codex_event_shape_becomes_hash_only_fence_bound_result(
    tmp_path: Path, monkeypatch,
) -> None:
    agent_host = load_agent_host()
    monkeypatch.setattr(
        agent_host,
        "resolve_home_control_plane_url",
        lambda *_args, **_kwargs: "http://127.0.0.1:9101",
    )
    monkeypatch.setattr(
        agent_host.shutil,
        "which",
        lambda name: "/usr/local/bin/codex" if name == "codex" else None,
    )
    monkeypatch.setattr(
        agent_host.AgentHost,
        "detect_codex_runner_status",
        lambda _self, path: {
            "status": "available",
            "path": path,
            "login_status": "authenticated",
            "probe": {"model": "gpt-5.5", "sandbox": "read-only", "status": "passed"},
        },
    )
    raw_query = "private current-price query must never persist"
    raw_body = "private native search body must never persist"

    class Host(agent_host.AgentHost):
        def post(self, _path, body):
            return body

        def run_command(
            self, command, cwd, stdout_path, stderr_path, task, branch, logs,
            env=None, command_label=None, stdin_path=None,
        ):
            del self, cwd, task, branch, logs, env, command_label
            assert command[:3] == ["/usr/local/bin/codex", "--search", "exec"]
            assert command[command.index("--sandbox") + 1] == "read-only"
            assert stdin_path is not None
            stdout_path.write_text(
                "\n".join((
                    _event("item.started", raw_query),
                    _event("item.completed", raw_query, result={"body": raw_body}),
                    json.dumps({
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "SAFE CODEX RESULT"},
                    }),
                )) + "\n",
                encoding="utf-8",
            )
            stderr_path.write_text("", encoding="utf-8")

    task = factory_codex_task()
    host = Host(make_args(tmp_path))
    result = host.run_owner_remote_task(task)

    query_sha256 = hashlib.sha256(raw_query.encode()).hexdigest()
    response_sha256 = hashlib.sha256(b"SAFE CODEX RESULT").hexdigest()
    evidence = result["native_web_search_evidence"]
    assert evidence["schema_version"] == "kolibri.native-web-search-evidence.v1"
    assert evidence["tool"] == "web_search"
    assert evidence["event_count"] == 2
    assert evidence["completed_event_count"] == 1
    assert evidence["query_count"] == 1
    assert evidence["query_sha256"] == [query_sha256]
    assert evidence["response_sha256"] == response_sha256
    assert len(evidence["evidence_sha256"]) == 64
    assert len(evidence["binding_sha256"]) == 64
    assert result["fencing_token"] == 41

    artifact_dir = (
        tmp_path / "artifacts" / task["task_id"] / task["attempt_id"]
    )
    persisted = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (artifact_dir / "stdout.log", artifact_dir / "result.json")
    )
    assert raw_query not in persisted
    assert raw_body not in persisted
    assert query_sha256 in (artifact_dir / "stdout.log").read_text(encoding="utf-8")

    changed_fence = dict(task)
    changed_fence["fencing_token"] = 42
    rebound = host._bind_native_web_search_evidence(
        {
            key: value
            for key, value in evidence.items()
            if key not in {"response_sha256", "binding_sha256"}
        },
        response_text="SAFE CODEX RESULT",
        task=changed_fence,
    )
    assert rebound["binding_sha256"] != evidence["binding_sha256"]


def test_native_search_requires_query_bound_completed_event(tmp_path: Path) -> None:
    agent_host = load_agent_host()
    path = tmp_path / "started-only.jsonl"
    path.write_text(
        _event("item.started", "current price") + "\n"
        + json.dumps({
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "answer"},
        }) + "\n",
        encoding="utf-8",
    )

    payload = agent_host.AgentHost.parse_json_response_payload(path)

    assert payload["response"] == "answer"
    assert "native_web_search_evidence" not in payload


def test_native_search_query_limit_fails_closed(tmp_path: Path) -> None:
    agent_host = load_agent_host()
    path = tmp_path / "too-many-queries.jsonl"
    rows: list[str] = []
    for index in range(agent_host.MAX_NATIVE_WEB_SEARCH_QUERIES + 1):
        query = f"current price query {index}"
        item = {"type": "web_search", "id": f"search-{index}", "query": query}
        rows.append(json.dumps({"type": "item.completed", "item": item}))
    rows.append(json.dumps({
        "type": "item.completed",
        "item": {"type": "agent_message", "text": "answer"},
    }))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    with pytest.raises(
        agent_host.NativeWebSearchEvidenceError,
        match="native_web_search_query_limit_exceeded",
    ):
        agent_host.AgentHost.parse_json_response_payload(path)


def test_mimo_response_only_still_rejects_web_search_event(tmp_path: Path) -> None:
    agent_host = load_agent_host()
    path = tmp_path / "mimo-web-search.jsonl"
    path.write_text(
        _event("item.completed", "must stay forbidden") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        agent_host.ResponseOnlyToolEventError,
        match="mimo_response_only_tool_event:web_search",
    ):
        agent_host.AgentHost.parse_json_response_payload(
            path,
            forbid_tool_events=True,
        )
