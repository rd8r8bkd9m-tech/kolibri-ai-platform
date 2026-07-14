"""Focused truth-contract tests for the Home Control Plane portal adapter."""

import asyncio

import httpx
import pytest

from app.control_plane import ControlPlaneUnavailable, HomeControlPlaneAdapter


RESULT_SHA256 = "a" * 64
BINDING_SHA256 = "b" * 64


def _proof_response(*rows: dict) -> httpx.Response:
    return httpx.Response(200, json={
        "schema_version": "kolibri.fleet-capability-proof.v1",
        "status": "complete" if rows else "incomplete",
        "source": "control-plane/home",
        "observed_at": "2026-07-13T06:46:00+00:00",
        "summary": {
            "canonical_total": len(rows),
            "strict_verified_total": sum(
                1
                for row in rows
                if row.get("strict_verified_completion", {}).get("proven") is True
            ),
        },
        "nodes": list(rows),
    })


def _verified_proof(node_id: str, task_id: str = "TASK-VERIFIED") -> dict:
    return {
        "node_id": node_id,
        "strict_verified_completion": {
            "proven": True,
            "task_id": task_id,
            "kind": "read_only_probe",
            "attempt_id": "attempt-1",
            "completed_at": "2026-07-13T06:45:50+00:00",
            "result_sha256": RESULT_SHA256,
            "binding_sha256": BINDING_SHA256,
            "verifier": "control-plane/home",
            "verifier_schema": "kolibri.control-plane-completion-verifier.v1",
        },
    }


def _unverified_proof(node_id: str) -> dict:
    return {
        "node_id": node_id,
        "strict_verified_completion": {
            "proven": False,
            "task_id": None,
            "result_sha256": None,
            "binding_sha256": None,
            "verifier": None,
        },
    }


def _adapter(handler) -> HomeControlPlaneAdapter:
    return HomeControlPlaneAdapter(
        base_url="http://home-control.invalid",
        timeout_seconds=0.5,
        transport=httpx.MockTransport(handler),
    )


def test_nodes_are_mapped_from_live_control_plane_with_truth():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/runtime/fleet-proof":
            return _proof_response(_verified_proof("home", "TASK-1"))
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
    assert node["status"] == "connected"
    assert node["connection"] == {
        "status": "online",
        "connected": True,
        "reported_health": "online",
        "source": "node_health_report",
    }
    assert node["freshness"]["fresh"] is True
    assert node["execution"]["active"] is True
    assert node["execution"]["executable"] is True
    assert node["verification"]["verified"] is True
    evidence = node["verification"]["last_successful_task"]
    assert evidence["task_id"] == "TASK-1"
    assert evidence["result_sha256"] == RESULT_SHA256
    assert evidence["binding_sha256"] == BINDING_SHA256
    assert node["ram_percent"] == "75.0"
    assert node["disk_percent"] == "25.0"
    assert node["cpu_percent"] == "unavailable"
    assert node["capabilities"]["metrics_availability"]["cpu_percent"] == "unavailable"
    assert node["capabilities"]["_truth"]["availability"] == "live"
    assert node["agent_count"] == 1
    assert node["task_count"] == 1


def test_stale_node_is_explicit_and_never_reported_healthy():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/runtime/fleet-proof":
            return _proof_response(_unverified_proof("agent01"))
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
    node = result["items"][0]
    assert node["status"] == "connected"
    assert node["connection"]["connected"] is True
    assert node["freshness"]["status"] == "stale"
    assert node["execution"]["executable"] is False
    assert node["execution"]["active"] is False
    assert node["verification"]["verified"] is False
    assert node["capabilities"]["_truth"]["availability"] == "stale"


def test_agents_are_derived_from_agent_hosts_without_seeded_roles():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/runtime/fleet-proof":
            return _proof_response(_verified_proof("agent01", "TASK-LIVE"))
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
    assert agent["progress"] is None
    assert agent["capabilities"]["progress_availability"] == "unavailable"
    assert agent["execution"]["active"] is True
    assert agent["execution"]["executable"] is True
    assert agent["verification"]["verified"] is True
    assert agent["capabilities"]["_truth"]["availability"] == "live"
    assert agent["capabilities"]["runners"]["mimo"] == {
        "status": "available",
        "model": "mimo/mimo-auto",
    }
    assert "path" not in agent["capabilities"]["runners"]["mimo"]


def test_agent_without_active_task_is_idle_not_active():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/runtime/fleet-proof":
            return _proof_response(_unverified_proof("agent02"))
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
    assert agent["execution"]["active"] is False
    assert agent["verification"]["verified"] is False
    assert agent["capabilities"]["_truth"]["activity_source"] == "none"


def test_runner_catalog_membership_is_not_executable_or_verified_when_blocked():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/runtime/fleet-proof":
            return _proof_response(_unverified_proof("agent03"))
        return httpx.Response(200, json={
            "nodes": [{
                "node_id": "agent03",
                "agent_id": "agent03-agent-host",
                "hostname": "worker-03",
                "health": "online",
                "reported_health": "online",
                "freshness": "fresh",
                "heartbeat_at": "2026-07-13T06:45:19+00:00",
                "registered": True,
                "schedulable": True,
                "active_task": None,
                "capabilities": ["runner:mimo"],
                "runners": {
                    "mimo": {
                        "status": "blocked",
                        "error_type": "provider_risk_control",
                    },
                },
            }],
            "counts": {"fresh": 1, "stale": 0, "total": 1},
            "membership": {"canonical_total": 21},
            "pagination": {"total_indexed": 21},
        })

    result = asyncio.run(
        _adapter(handler).list_nodes(page=1, page_size=50, status=None)
    )

    node = result["items"][0]
    assert node["connection"]["connected"] is True
    assert node["freshness"]["fresh"] is True
    assert node["execution"]["blocked"] is True
    assert node["execution"]["executable"] is False
    assert node["execution"]["active"] is False
    assert node["verification"]["verified"] is False
    assert node["capabilities"]["execution"] == [{
        "name": "runner:mimo",
        "runner": "mimo",
        "runner_status": "blocked",
        "executable": False,
        "reasons": ["runner_blocked"],
    }]


def test_missing_fleet_proof_is_unavailable_not_a_fake_unverified_zero():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/runtime/fleet-proof":
            return httpx.Response(404, json={"error": "not_found"})
        return httpx.Response(200, json={
            "nodes": [{
                "node_id": "home",
                "health": "online",
                "freshness": "fresh",
                "registered": True,
                "schedulable": True,
                "capabilities": ["read_only_probe"],
            }],
            "counts": {"fresh": 1, "stale": 0, "total": 1},
            "membership": {"canonical_total": 1},
            "pagination": {"total_indexed": 1},
        })

    result = asyncio.run(
        _adapter(handler).list_nodes(page=1, page_size=50, status=None)
    )

    assert result["truth"]["verification"]["availability"] == "unavailable"
    verification = result["items"][0]["verification"]
    assert verification["status"] == "unavailable"
    assert verification["last_successful_task"] is None


def test_quarantined_membership_and_untrusted_verifier_never_become_working():
    forged = _verified_proof("worker-missing")
    forged["strict_verified_completion"]["verifier"] = "worker/self"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/runtime/fleet-proof":
            return _proof_response(forged)
        return httpx.Response(200, json={
            "nodes": [{
                "node_id": "worker-missing",
                "hostname": "worker-missing",
                "health": "quarantined",
                "reported_health": "missing",
                "freshness": "stale",
                "registered": False,
                "schedulable": False,
                "active_task": None,
                "quarantine_reason": "missing_agent_host_registration",
                "capabilities": [],
            }],
            "counts": {"fresh": 0, "stale": 1, "total": 1},
            "membership": {"canonical_total": 1, "registered_total": 0},
            "pagination": {"total_indexed": 1},
        })

    result = asyncio.run(
        _adapter(handler).list_nodes(page=1, page_size=50, status=None)
    )

    node = result["items"][0]
    assert node["status"] == "quarantined"
    assert node["connection"]["connected"] is False
    assert node["freshness"]["fresh"] is False
    assert node["execution"]["active"] is False
    assert node["execution"]["executable"] is False
    assert node["execution"]["quarantined"] is True
    assert node["verification"]["verified"] is False
    assert node["verification"]["last_successful_task"] is None


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


def test_cluster_stats_are_paginated_from_home_without_seed_rows():
    def task(task_id: str, state: str) -> dict:
        return {
            "task_id": task_id,
            "state": state,
            "attempt": 1,
            "created_at": "2026-07-13T06:00:00+00:00",
            "updated_at": "2026-07-13T06:01:00+00:00",
            "envelope": {"objective": task_id},
        }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/runtime/fleet-proof":
            return _proof_response(
                _verified_proof("home", "T-running"),
                _unverified_proof("agent01"),
            )
        if request.url.path == "/v1/nodes":
            return httpx.Response(200, json={
                "nodes": [
                    {
                        "node_id": "home", "hostname": "home", "health": "online",
                        "freshness": "fresh", "registered": True, "schedulable": True,
                        "agent_id": "home-agent", "active_task": "T-running",
                        "capabilities": ["read_only_probe"],
                        "cpu_percent": 20, "ram": {"MemAvailable": "75 kB", "MemTotal": "100 kB"},
                        "disk": {"used": 50, "total": 100},
                    },
                    {
                        "node_id": "agent01", "hostname": "agent01", "health": "online",
                        "freshness": "fresh", "registered": True, "schedulable": True,
                        "agent_id": "agent01-agent", "active_task": None,
                        "capabilities": ["read_only_probe"],
                        "cpu_percent": 40, "ram": {"MemAvailable": "50 kB", "MemTotal": "100 kB"},
                        "disk": {"used": 70, "total": 100},
                    },
                ],
                "counts": {"fresh": 2, "stale": 0, "total": 2},
                "membership": {"canonical_total": 2},
                "pagination": {"total_indexed": 2},
            })
        assert request.url.path == "/v1/tasks"
        offset = int(request.url.params["offset"])
        if offset == 0:
            values = [task(f"T-{index}", "completed") for index in range(250)]
        else:
            values = [task("T-queued", "queued")]
        return httpx.Response(200, json={
            "tasks": values,
            "queue_total": 1,
            "pagination": {
                "limit": 250, "offset": offset, "returned": len(values), "total_indexed": 251,
            },
        })

    result = asyncio.run(_adapter(handler).cluster_stats())

    assert result["nodes"] == {
        "membership_total": 2,
        "connected": 2,
        "fresh": 2,
        "capability_executable": 2,
        "active": 1,
        "verified": 1,
        "blocked": 0,
        "quarantined": 0,
        "stale": 0,
        "total": 2,
        "healthy": 1,
        "degraded": 1,
        "offline": 0,
    }
    assert result["agents"] == {
        "membership_total": 2,
        "active": 1,
        "idle": 1,
        "paused": 0,
        "executable": 2,
        "verified": 1,
    }
    assert result["tasks"]["total"] == 251
    assert result["tasks"]["completed"] == 250
    assert result["tasks"]["queued"] == 1
    assert result["resources"] == {"avg_cpu": 30.0, "avg_ram": 37.5, "avg_disk": 60.0}
    assert result["truth"]["source"] == "home_control_plane"
    assert result["truth"]["availability"] == "live"
    assert result["truth"]["task_pages"] == 2
    assert result["truth"]["verification"]["availability"] == "live"


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
