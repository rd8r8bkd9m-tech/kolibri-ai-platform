"""Focused truth-contract tests for the Home Control Plane portal adapter."""

import asyncio

import httpx
import pytest

from app.control_plane import ControlPlaneUnavailable, HomeControlPlaneAdapter


def _adapter(handler) -> HomeControlPlaneAdapter:
    return HomeControlPlaneAdapter(
        base_url="http://home-control.invalid",
        timeout_seconds=0.5,
        transport=httpx.MockTransport(handler),
    )


def test_nodes_are_mapped_from_live_control_plane_with_truth():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/nodes"
        assert request.url.params["scope"] == "active"
        return httpx.Response(
            200,
            json={
                "nodes": [
                    {
                        "node_id": "home",
                        "hostname": "plastilin",
                        "mesh_ip": "10.99.0.1",
                        "health": "online",
                        "reported_health": "online",
                        "freshness": "fresh",
                        "heartbeat_at": "2026-07-13T06:45:19+00:00",
                        "heartbeat_age_seconds": 9,
                        "registered": True,
                        "schedulable": True,
                        "draining": False,
                        "agent_id": "home-agent-host",
                        "active_task": "TASK-1",
                        "cpu": 6,
                        "ram": {"MemAvailable": "3000 kB", "MemTotal": "12000 kB"},
                        "disk": {"used": 25, "total": 100},
                        "capabilities": ["runner:mimo"],
                        "runners": {"mimo": {"status": "available"}},
                    }
                ],
                "counts": {"fresh": 1, "stale": 0, "total": 1},
                "membership": {"canonical_total": 21, "registered_total": 21},
                "pagination": {"total_indexed": 21},
            },
        )

    result = asyncio.run(
        _adapter(handler).list_nodes(page=1, page_size=50, status=None)
    )

    assert result["total"] == 21
    assert result["truth"]["availability"] == "live"
    assert result["truth"]["source"] == "home_control_plane"
    node = result["items"][0]
    assert node["id"] == "home"
    assert node["status"] == "healthy"
    assert node["ram_percent"] == "75.0"
    assert node["disk_percent"] == "25.0"
    assert node["cpu_percent"] == "unavailable"
    assert node["capabilities"]["metrics_availability"]["cpu_percent"] == "unavailable"
    assert node["capabilities"]["_truth"]["availability"] == "live"
    assert node["agent_count"] == 1
    assert node["task_count"] == 1


def test_stale_node_is_explicit_and_never_reported_healthy():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "nodes": [{
                    "node_id": "agent01",
                    "hostname": "agent01",
                    "health": "online",
                    "freshness": "stale",
                    "registered": True,
                    "schedulable": False,
                    "capabilities": [],
                }],
                "counts": {"fresh": 0, "stale": 1, "total": 1},
                "membership": {"canonical_total": 21},
                "pagination": {"total_indexed": 21},
            },
        )

    result = asyncio.run(
        _adapter(handler).list_nodes(page=1, page_size=50, status=None)
    )

    assert result["truth"]["availability"] == "stale"
    assert result["items"][0]["status"] == "offline"
    assert result["items"][0]["capabilities"]["_truth"]["availability"] == "stale"


def test_agents_are_derived_from_agent_hosts_without_seeded_roles():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/nodes"
        return httpx.Response(
            200,
            json={
                "nodes": [{
                    "node_id": "agent01",
                    "agent_id": "agent01-agent-host",
                    "hostname": "worker-01",
                    "health": "online",
                    "freshness": "fresh",
                    "heartbeat_at": "2026-07-13T06:45:19+00:00",
                    "heartbeat_age_seconds": 4,
                    "registered": True,
                    "schedulable": True,
                    "active_task": "TASK-LIVE",
                    "capabilities": ["implementation", "runner:mimo"],
                    "runners": {
                        "mimo": {
                            "status": "available",
                            "model": "mimo/mimo-auto",
                            "path": "/private/runtime/path",
                        },
                    },
                }],
                "counts": {"fresh": 1, "stale": 0, "total": 1},
                "membership": {"canonical_total": 21},
                "pagination": {"total_indexed": 21},
            },
        )

    result = asyncio.run(
        _adapter(handler).list_agents(page=1, page_size=50, status=None)
    )

    assert result["total"] == 21
    assert result["truth"]["derivation"] == "one_agent_host_per_active_node"
    agent = result["items"][0]
    assert agent["id"] == "agent01-agent-host"
    assert agent["role"] == "agent_host"
    assert agent["status"] == "active"
    assert agent["current_task"] == "TASK-LIVE"
    assert agent["progress"] == 0
    assert agent["capabilities"]["progress_availability"] == "unavailable"
    assert agent["capabilities"]["_truth"]["availability"] == "live"
    assert agent["capabilities"]["runners"]["mimo"] == {
        "status": "available",
        "model": "mimo/mimo-auto",
    }
    assert "path" not in agent["capabilities"]["runners"]["mimo"]


def test_agent_without_active_task_is_idle_not_active():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "nodes": [{
                    "node_id": "agent02",
                    "agent_id": "agent02-agent-host",
                    "health": "online",
                    "freshness": "fresh",
                    "heartbeat_at": "2026-07-13T06:45:19+00:00",
                    "registered": True,
                    "schedulable": True,
                    "active_task": None,
                }],
                "counts": {"fresh": 1, "stale": 0, "total": 1},
                "membership": {"canonical_total": 21},
                "pagination": {"total_indexed": 21},
            },
        )

    result = asyncio.run(
        _adapter(handler).list_agents(page=1, page_size=50, status=None)
    )

    agent = result["items"][0]
    assert agent["status"] == "idle"
    assert agent["current_task"] is None
    assert agent["capabilities"]["_truth"]["activity_source"] == "none"


def test_tasks_map_home_states_and_preserve_verifier_truth():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/tasks"
        return httpx.Response(
            200,
            json={
                "tasks": [{
                    "task_id": "TASK-42",
                    "state": "dead_letter",
                    "attempt": 2,
                    "lease_owner": "agent01:mimo",
                    "created_at": "2026-07-13T06:00:00+00:00",
                    "updated_at": "2026-07-13T06:01:00+00:00",
                    "truth_gate": {"verdict": "false", "confidence": "high"},
                    "result_reference": None,
                    "envelope": {
                        "objective": "Проверить сборку",
                        "target_node": "agent01",
                        "priority": "P0",
                        "max_retries": 2,
                    },
                }],
                "queue_total": 0,
                "pagination": {"total_indexed": 424},
            },
        )

    result = asyncio.run(
        _adapter(handler).list_tasks(page=1, page_size=20, state=None)
    )

    assert result["total"] == 424
    assert result["truth"]["availability"] == "live"
    task = result["items"][0]
    assert task["id"] == "TASK-42"
    assert task["workflow_id"] == "Проверить сборку"
    assert task["state"] == "failed"
    assert task["priority"] == 5
    assert task["attempts"] == 2
    assert task["node_id"] == "agent01"
    assert task["owner_agent_id"] == "mimo"
    assert task["result"]["_truth"]["truth_gate"]["verdict"] == "false"


def test_bad_status_fails_closed_instead_of_returning_seed_data():
    adapter = _adapter(lambda _: httpx.Response(502, json={"error": "upstream"}))

    with pytest.raises(ControlPlaneUnavailable, match="control_plane_bad_status"):
        asyncio.run(adapter.list_nodes(page=1, page_size=50, status=None))


def test_invalid_contract_fails_closed():
    adapter = _adapter(lambda _: httpx.Response(200, json={"items": []}))

    with pytest.raises(
        ControlPlaneUnavailable,
        match="control_plane_nodes_contract_invalid",
    ):
        asyncio.run(adapter.list_nodes(page=1, page_size=50, status=None))
