from __future__ import annotations

import copy
import hashlib
import hmac
import http.client
import importlib.util
import json
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
NODE_ID = "mac-codex-provider-test"
AGENT_ID = "mac-codex-provider-test-agent"
CREDENTIAL_ID = "mac-codex-provider-test-v1"
TOKEN = "test-provider-" + "token-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
WRONG_TOKEN = "wrong-provider-" + "token-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
TASK_ID = "KOL-PROVIDER-auth-http-test"


def load_control():
    name = f"factory_control_external_auth_http_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, ROOT / "ops" / "factory_control.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def compact_json(body: dict[str, Any]) -> bytes:
    return json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def auth_marker(epoch: int = 1) -> dict[str, Any]:
    return {
        "actor_scope": "external_provider_actor",
        "bound_node_id": NODE_ID,
        "credential_id": CREDENTIAL_ID,
        "epoch": epoch,
    }


def external_node(*, marker_epoch: int | None = 1) -> dict[str, Any]:
    node = {
        "node_id": NODE_ID,
        "hostname": "owner-mac",
        "agent_id": AGENT_ID,
        "health": "online",
        "heartbeat_at": "2026-07-11T00:00:00+00:00",
        "labels": {
            "provider": "codex",
            "runtime": "macos_launchagent",
            "physical_node_id": NODE_ID,
        },
        "capabilities": ["codex_provider_broker", "runner:codex"],
        "runners": {},
        "runner_readiness": {},
    }
    if marker_epoch is not None:
        node["external_provider_auth"] = auth_marker(marker_epoch)
    return node


def external_registration_body() -> dict[str, Any]:
    node = external_node(marker_epoch=None)
    node.pop("health")
    node.pop("heartbeat_at")
    return node


def external_heartbeat_body() -> dict[str, Any]:
    return {
        "node_id": NODE_ID,
        "hostname": "owner-mac",
        "agent_id": AGENT_ID,
        "pid": 321,
        "capabilities": ["codex_provider_broker", "runner:codex"],
        "runners": {},
        "runner_readiness": {},
        "labels": {
            "provider": "codex",
            "runtime": "macos_launchagent",
            "physical_node_id": NODE_ID,
        },
    }


def leased_task(*, marker_epoch: int = 1) -> dict[str, Any]:
    return {
        "task_id": TASK_ID,
        "state": "leased",
        "attempt": 1,
        "attempt_id": f"{TASK_ID}-attempt-1",
        "lease_owner": f"{NODE_ID}:{AGENT_ID}",
        "lease_actor_scope": "external_provider_actor",
        "lease_external_auth": auth_marker(marker_epoch),
        "lease_until": time.time() + 60,
        "heartbeat_at": "2026-07-11T00:00:00+00:00",
        "max_attempts": 1,
        "result": None,
        "envelope": {"runner": "codex"},
    }


def task_fence_body() -> dict[str, Any]:
    return {
        "node_id": NODE_ID,
        "agent_id": AGENT_ID,
        "attempt_id": f"{TASK_ID}-attempt-1",
    }


def signed_headers(
    control,
    path: str,
    raw_body: bytes,
    *,
    token: str = TOKEN,
    credential_id: str = CREDENTIAL_ID,
    epoch: int = 1,
    nonce: str | None = None,
    timestamp: int | None = None,
    signed_method: str = "POST",
    signed_path: str | None = None,
    signed_node: str = NODE_ID,
) -> dict[str, str]:
    timestamp_text = str(int(time.time()) if timestamp is None else timestamp)
    nonce = nonce or uuid.uuid4().hex
    body_sha256 = hashlib.sha256(raw_body).hexdigest()
    canonical = "\n".join((
        control.EXTERNAL_PROVIDER_AUTH_HMAC_CONTRACT,
        signed_method,
        signed_path or path,
        body_sha256,
        timestamp_text,
        nonce,
        signed_node,
        credential_id,
        str(epoch),
    ))
    signature = hmac.new(
        hashlib.sha256(token.encode("utf-8")).digest(),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "Authorization": f"Bearer {token}",
        "X-Kolibri-Actor-Timestamp": timestamp_text,
        "X-Kolibri-Actor-Nonce": nonce,
        "X-Kolibri-Actor-Signature": signature,
        "X-Kolibri-Actor-Node": signed_node,
        "X-Kolibri-Actor-Contract": control.EXTERNAL_PROVIDER_AUTH_HMAC_CONTRACT,
        "X-Kolibri-Actor-Credential": credential_id,
        "X-Kolibri-Actor-Epoch": str(epoch),
    }


class NonceRedis:
    def __init__(self) -> None:
        self.nonces: set[str] = set()
        self.node_ids: set[str] = set()
        self.fail_nonce = False
        self._lock = threading.Lock()

    def command(self, *parts):
        if len(parts) >= 2 and parts[0] == "SET" and "NX" in parts:
            with self._lock:
                if self.fail_nonce:
                    raise RuntimeError("redis_nonce_unavailable")
                redis_key = str(parts[1])
                if redis_key in self.nonces:
                    return None
                self.nonces.add(redis_key)
                return "OK"
        if parts[:2] == ("SADD", "kolibri_factory:node_ids"):
            self.node_ids.update(str(item) for item in parts[2:])
            return len(parts) - 2
        if parts and parts[0] == "SADD":
            self.node_ids.update(str(item) for item in parts[2:])
            return len(parts) - 2
        if parts and parts[0] == "GET":
            return None
        raise AssertionError(f"unexpected Redis command: {parts!r}")


class AuthHTTPHarness:
    def __init__(
        self,
        *,
        auth_epoch: int = 1,
        marker_epoch: int | None = 1,
        node_present: bool = True,
        task_marker_epoch: int = 1,
        auth_configured: bool = True,
        physical_node: bool = False,
    ) -> None:
        self.control = load_control()
        self.redis = NonceRedis()
        if auth_configured:
            self.control.configure_external_provider_actor_token_sha256(
                hashlib.sha256(TOKEN.encode("utf-8")).hexdigest(),
                node_id=NODE_ID,
                credential_id=CREDENTIAL_ID,
                epoch=auth_epoch,
            )
        else:
            self.control.configure_external_provider_actor_token_sha256(None)
        if physical_node:
            node = {
                "node_id": NODE_ID,
                "hostname": "physical-worker",
                "agent_id": AGENT_ID,
                "labels": {},
                "capabilities": ["generic_implementation"],
                "health": "online",
            }
        else:
            node = external_node(marker_epoch=marker_epoch)
        self.nodes = {NODE_ID: node} if node_present else {}
        self.tasks = {TASK_ID: leased_task(marker_epoch=task_marker_epoch)}
        self.save_count = 0
        self._lock = threading.Lock()

        control = self.control
        control.redis = self.redis

        def get_json(redis_key: str, default=None):
            node_prefix = f"{control.NAMESPACE}:node:"
            if str(redis_key).startswith(node_prefix):
                node_id = str(redis_key)[len(node_prefix):]
                return copy.deepcopy(self.nodes.get(node_id, default))
            return copy.deepcopy(default)

        def set_json(redis_key: str, value: dict[str, Any]):
            node_prefix = f"{control.NAMESPACE}:node:"
            if str(redis_key).startswith(node_prefix):
                node_id = str(redis_key)[len(node_prefix):]
                with self._lock:
                    self.nodes[node_id] = copy.deepcopy(value)
                    self.save_count += 1
                return
            raise AssertionError(f"unexpected set_json key: {redis_key}")

        def load_task(task_id: str):
            return copy.deepcopy(self.tasks.get(task_id))

        def save_task(task: dict[str, Any]):
            with self._lock:
                self.tasks[str(task["task_id"])] = copy.deepcopy(task)
                self.save_count += 1

        def finish_task(task: dict[str, Any], desired_state: str):
            task["state"] = desired_state
            return task

        control.get_json = get_json
        control.set_json = set_json
        control.load_task = load_task
        control.save_task = save_task
        control.node_membership_annotation = lambda _node_id: {
            "membership_scope": "audit",
            "schedulable": False,
        }
        control.requeue_expired_leases = lambda *_args, **_kwargs: {}
        control.lease_node_eligibility = lambda node_id: {
            "eligible": True,
            "lease_scope": control.EXTERNAL_PROVIDER_ACTOR_SCOPE,
            "provider": "codex",
            "node": copy.deepcopy(self.nodes.get(node_id, external_node())),
        }
        control.queue_ids = lambda: []
        control.truth_gate_on_complete = lambda task, _result: task
        control.enforce_completion_truth_state = finish_task
        control.create_review_task = lambda _task, _result: None
        control.truth_gate_on_fail = lambda task, _error_type, _error: task
        control.mark_node_runner_failure = lambda _task, _body: None
        control.enqueue = lambda _task_id: None

        self.server = control.ThreadingHTTPServer(("127.0.0.1", 0), control.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def snapshot(self) -> dict[str, Any]:
        return {
            "nodes": copy.deepcopy(self.nodes),
            "tasks": copy.deepcopy(self.tasks),
            "save_count": self.save_count,
            "node_ids": set(self.redis.node_ids),
        }

    def post(
        self,
        path: str,
        body: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        raw_body: bytes | None = None,
    ) -> tuple[int, Any]:
        raw = compact_json(body) if raw_body is None else raw_body
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        host, port = self.server.server_address
        connection = http.client.HTTPConnection(host, port, timeout=3)
        connection.request("POST", path, body=raw, headers=request_headers)
        result = connection.getresponse()
        response_body = result.read()
        status = result.status
        connection.close()
        return status, json.loads(response_body) if response_body else None


def endpoint_case(name: str) -> tuple[str, dict[str, Any], int]:
    fence = task_fence_body()
    cases = {
        "register": ("/v1/nodes/register", external_registration_body(), 200),
        "node_heartbeat": (
            f"/v1/nodes/{NODE_ID}/heartbeat", external_heartbeat_body(), 200,
        ),
        "lease": (
            "/v1/tasks/lease",
            {
                "node_id": NODE_ID,
                "agent_id": AGENT_ID,
                "capabilities": ["codex_provider_broker", "runner:codex"],
            },
            204,
        ),
        "task_heartbeat": (
            f"/v1/tasks/{TASK_ID}/heartbeat", {**fence, "state": "running"}, 200,
        ),
        "complete": (
            f"/v1/tasks/{TASK_ID}/complete",
            {
                **fence,
                "result_reference": f"/var/lib/kolibri-agent/{TASK_ID}/result.json",
                "result": {
                    "runner": "codex",
                    "status": "completed",
                    "output": "123",
                    "result_path": f"/var/lib/kolibri-agent/{TASK_ID}/result.json",
                },
            },
            200,
        ),
        "fail": (
            f"/v1/tasks/{TASK_ID}/fail",
            {
                **fence,
                "retry": False,
                "error_type": "provider_unavailable",
                "error": "bounded failure",
                "result": {"runner": "codex"},
            },
            200,
        ),
    }
    return cases[name]


@pytest.mark.parametrize(
    "endpoint",
    ["register", "node_heartbeat", "lease", "task_heartbeat", "complete", "fail"],
)
@pytest.mark.parametrize(
    ("auth_mode", "expected_status", "expected_error"),
    [
        ("missing", 401, "external_provider_actor_auth_required"),
        ("wrong_bearer", 401, "external_provider_actor_auth_invalid"),
        ("wrong_hmac", 401, "external_provider_actor_signature_invalid"),
        ("correct", None, None),
    ],
)
def test_every_external_actor_mutation_requires_bearer_and_wire_hmac(
    endpoint: str,
    auth_mode: str,
    expected_status: int | None,
    expected_error: str | None,
):
    harness = AuthHTTPHarness()
    try:
        path, body, success_status = endpoint_case(endpoint)
        raw = compact_json(body)
        before = harness.snapshot()
        if auth_mode == "missing":
            headers = {}
        elif auth_mode == "wrong_bearer":
            headers = signed_headers(harness.control, path, raw, token=WRONG_TOKEN)
        else:
            headers = signed_headers(harness.control, path, raw)
            if auth_mode == "wrong_hmac":
                headers["X-Kolibri-Actor-Signature"] = "0" * 64
        status, payload = harness.post(path, body, headers=headers, raw_body=raw)
        if auth_mode == "correct":
            assert status == success_status
        else:
            assert status == expected_status
            assert payload == {"error": expected_error}
            assert harness.snapshot() == before
            assert not harness.redis.nonces
        serialized = json.dumps(payload, sort_keys=True)
        assert TOKEN not in serialized
        assert WRONG_TOKEN not in serialized
        assert hashlib.sha256(TOKEN.encode()).hexdigest() not in serialized
    finally:
        harness.close()


def test_nonce_ttl_exceeds_the_full_accepted_clock_window():
    control = load_control()
    assert (
        control.EXTERNAL_PROVIDER_AUTH_NONCE_TTL_SECONDS
        > 2 * control.EXTERNAL_PROVIDER_AUTH_CLOCK_SKEW_SECONDS
    )


@pytest.mark.parametrize("wire_variant", ["whitespace", "unicode_encoding"])
def test_hmac_binds_the_exact_wire_bytes(wire_variant: str):
    harness = AuthHTTPHarness()
    try:
        path = f"/v1/nodes/{NODE_ID}/heartbeat"
        body = {**external_heartbeat_body(), "active_task": "привет"}
        if wire_variant == "whitespace":
            signed_raw = compact_json(body)
            sent_raw = json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True).encode()
        else:
            signed_raw = json.dumps(
                body, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
            ).encode()
            sent_raw = compact_json(body)
        before = harness.snapshot()
        headers = signed_headers(harness.control, path, signed_raw)
        status, payload = harness.post(path, body, headers=headers, raw_body=sent_raw)
        assert status == 401
        assert payload == {"error": "external_provider_actor_signature_invalid"}
        assert harness.snapshot() == before
        assert not harness.redis.nonces
    finally:
        harness.close()


@pytest.mark.parametrize(
    "tamper",
    [
        "method", "path", "body", "node", "contract", "credential", "epoch",
        "timestamp_stale", "timestamp_future", "nonce", "signature",
    ],
)
def test_signed_contract_rejects_each_tampered_binding_without_mutation(tamper: str):
    harness = AuthHTTPHarness()
    try:
        path = f"/v1/nodes/{NODE_ID}/heartbeat"
        body = external_heartbeat_body()
        raw = compact_json(body)
        signed_raw = compact_json({**body, "pid": 999}) if tamper == "body" else raw
        headers = signed_headers(
            harness.control,
            path,
            signed_raw,
            signed_method="GET" if tamper == "method" else "POST",
            signed_path="/v1/nodes/other/heartbeat" if tamper == "path" else path,
            timestamp=(
                int(time.time()) - harness.control.EXTERNAL_PROVIDER_AUTH_CLOCK_SKEW_SECONDS - 1
                if tamper == "timestamp_stale"
                else int(time.time()) + harness.control.EXTERNAL_PROVIDER_AUTH_CLOCK_SKEW_SECONDS + 1
                if tamper == "timestamp_future"
                else None
            ),
        )
        if tamper == "node":
            headers["X-Kolibri-Actor-Node"] = "other-node"
        elif tamper == "contract":
            headers["X-Kolibri-Actor-Contract"] = "kolibri.external-provider-hmac.v0"
        elif tamper == "credential":
            headers["X-Kolibri-Actor-Credential"] = "other-credential"
        elif tamper == "epoch":
            headers["X-Kolibri-Actor-Epoch"] = "0"
        elif tamper == "nonce":
            headers["X-Kolibri-Actor-Nonce"] = "not-a-valid-nonce"
        elif tamper == "signature":
            headers["X-Kolibri-Actor-Signature"] = "f" * 64
        before = harness.snapshot()
        status, payload = harness.post(path, body, headers=headers, raw_body=raw)
        assert status == 401
        assert payload["error"] in {
            "external_provider_actor_signature_required",
            "external_provider_actor_signature_invalid",
        }
        assert harness.snapshot() == before
        assert not harness.redis.nonces
    finally:
        harness.close()


def test_nonce_replay_is_rejected_before_a_second_mutation():
    harness = AuthHTTPHarness()
    try:
        path = f"/v1/nodes/{NODE_ID}/heartbeat"
        body = external_heartbeat_body()
        raw = compact_json(body)
        headers = signed_headers(harness.control, path, raw, nonce="a" * 32)
        first_status, _ = harness.post(path, body, headers=headers, raw_body=raw)
        after_first = harness.snapshot()
        second_status, second = harness.post(path, body, headers=headers, raw_body=raw)
        assert first_status == 200
        assert second_status == 409
        assert second == {"error": "external_provider_actor_replay_rejected"}
        assert harness.snapshot() == after_first
        assert len(harness.redis.nonces) == 1
    finally:
        harness.close()


def test_nonce_reuse_is_rejected_across_different_mutation_endpoints():
    harness = AuthHTTPHarness()
    try:
        nonce = "b" * 32
        heartbeat_path = f"/v1/nodes/{NODE_ID}/heartbeat"
        heartbeat = external_heartbeat_body()
        heartbeat_raw = compact_json(heartbeat)
        first_status, _ = harness.post(
            heartbeat_path,
            heartbeat,
            headers=signed_headers(
                harness.control, heartbeat_path, heartbeat_raw, nonce=nonce,
            ),
            raw_body=heartbeat_raw,
        )
        after_first = harness.snapshot()
        lease_path, lease, _ = endpoint_case("lease")
        lease_raw = compact_json(lease)
        second_status, second = harness.post(
            lease_path,
            lease,
            headers=signed_headers(harness.control, lease_path, lease_raw, nonce=nonce),
            raw_body=lease_raw,
        )
        assert first_status == 200
        assert second_status == 409
        assert second == {"error": "external_provider_actor_replay_rejected"}
        assert harness.snapshot() == after_first
        assert len(harness.redis.nonces) == 1
    finally:
        harness.close()


def test_concurrent_identical_replay_allows_exactly_one_mutation():
    harness = AuthHTTPHarness()
    try:
        path = f"/v1/nodes/{NODE_ID}/heartbeat"
        body = external_heartbeat_body()
        raw = compact_json(body)
        headers = signed_headers(harness.control, path, raw, nonce="c" * 32)
        barrier = threading.Barrier(3)
        outcomes: list[int] = []

        def send() -> None:
            barrier.wait()
            outcomes.append(harness.post(path, body, headers=headers, raw_body=raw)[0])

        workers = [threading.Thread(target=send) for _ in range(2)]
        for worker in workers:
            worker.start()
        barrier.wait()
        for worker in workers:
            worker.join(timeout=3)
        assert sorted(outcomes) == [200, 409]
        assert harness.save_count == 1
        assert len(harness.redis.nonces) == 1
    finally:
        harness.close()


def test_nonce_store_failure_fails_closed_without_business_mutation():
    harness = AuthHTTPHarness()
    try:
        harness.redis.fail_nonce = True
        path = f"/v1/nodes/{NODE_ID}/heartbeat"
        body = external_heartbeat_body()
        raw = compact_json(body)
        before = harness.snapshot()
        status, payload = harness.post(
            path, body, headers=signed_headers(harness.control, path, raw), raw_body=raw,
        )
        assert status == 500
        assert payload["error"] == "control_plane_error"
        assert harness.snapshot() == before
    finally:
        harness.close()


def test_unconfigured_external_auth_fails_closed():
    harness = AuthHTTPHarness(auth_configured=False, node_present=False)
    try:
        path, body, _ = endpoint_case("register")
        before = harness.snapshot()
        status, payload = harness.post(path, body)
        assert status == 503
        assert payload == {"error": "external_provider_actor_auth_unconfigured"}
        assert harness.snapshot() == before
    finally:
        harness.close()


def test_signed_heartbeat_migrates_an_exact_legacy_unmarked_card():
    harness = AuthHTTPHarness(marker_epoch=None)
    try:
        path, body, _ = endpoint_case("node_heartbeat")
        raw = compact_json(body)
        status, payload = harness.post(
            path, body, headers=signed_headers(harness.control, path, raw), raw_body=raw,
        )
        assert status == 200
        assert payload["external_provider_auth"] == auth_marker()
        assert harness.nodes[NODE_ID]["external_provider_auth"] == auth_marker()
    finally:
        harness.close()


@pytest.mark.parametrize(
    ("mutation", "expected_status", "expected_error"),
    [
        ("strip_identity", 409, "external_provider_actor_identity_immutable"),
        ("change_agent", 409, "external_provider_actor_agent_id_immutable"),
        ("inject_marker", 400, "external_provider_actor_identity_payload_invalid"),
    ],
)
def test_heartbeat_cannot_strip_identity_mutate_agent_or_inject_server_marker(
    mutation: str, expected_status: int, expected_error: str,
):
    harness = AuthHTTPHarness()
    try:
        path, body, _ = endpoint_case("node_heartbeat")
        if mutation == "strip_identity":
            body.pop("labels")
        elif mutation == "change_agent":
            body["agent_id"] = "attacker-agent"
        else:
            body["external_provider_auth"] = auth_marker()
        before = harness.snapshot()
        status, payload = harness.post(path, body)
        assert status == expected_status
        assert payload == {"error": expected_error}
        assert harness.snapshot() == before
    finally:
        harness.close()


def test_server_marker_injection_is_rejected_on_registration():
    harness = AuthHTTPHarness(node_present=False)
    try:
        path, body, _ = endpoint_case("register")
        body["external_provider_auth"] = auth_marker()
        before = harness.snapshot()
        status, payload = harness.post(path, body)
        assert status == 400
        assert payload == {"error": "external_provider_actor_server_marker_forbidden"}
        assert harness.snapshot() == before
    finally:
        harness.close()


def test_higher_epoch_registration_rotates_the_server_owned_marker():
    harness = AuthHTTPHarness(auth_epoch=2, marker_epoch=1)
    try:
        path, body, _ = endpoint_case("register")
        raw = compact_json(body)
        status, payload = harness.post(
            path,
            body,
            headers=signed_headers(harness.control, path, raw, epoch=2),
            raw_body=raw,
        )
        assert status == 200
        assert payload["external_provider_auth"] == auth_marker(2)
        assert harness.nodes[NODE_ID]["external_provider_auth"] == auth_marker(2)
    finally:
        harness.close()


def test_non_increasing_configured_epoch_cannot_downgrade_a_bound_card():
    harness = AuthHTTPHarness(auth_epoch=1, marker_epoch=2)
    try:
        path, body, _ = endpoint_case("register")
        raw = compact_json(body)
        before = harness.snapshot()
        status, payload = harness.post(
            path,
            body,
            headers=signed_headers(harness.control, path, raw, epoch=1),
            raw_body=raw,
        )
        assert status == 403
        assert payload == {"error": "external_provider_actor_credential_epoch_invalid"}
        assert harness.snapshot() == before
        assert not harness.redis.nonces
    finally:
        harness.close()


def test_stale_signed_epoch_is_rejected_even_with_the_current_bearer():
    harness = AuthHTTPHarness(auth_epoch=2, marker_epoch=2, task_marker_epoch=2)
    try:
        path, body, _ = endpoint_case("node_heartbeat")
        raw = compact_json(body)
        headers = signed_headers(harness.control, path, raw, epoch=2)
        headers["X-Kolibri-Actor-Epoch"] = "1"
        before = harness.snapshot()
        status, payload = harness.post(path, body, headers=headers, raw_body=raw)
        assert status == 401
        assert payload == {"error": "external_provider_actor_signature_required"}
        assert harness.snapshot() == before
    finally:
        harness.close()


def test_task_lease_marker_fences_mutations_after_runtime_card_loss():
    harness = AuthHTTPHarness(node_present=False)
    try:
        path, body, _ = endpoint_case("task_heartbeat")
        raw = compact_json(body)
        missing_status, missing = harness.post(path, body)
        assert missing_status == 401
        assert missing == {"error": "external_provider_actor_auth_required"}
        status, payload = harness.post(
            path, body, headers=signed_headers(harness.control, path, raw), raw_body=raw,
        )
        assert status == 200
        assert payload["state"] == "running"
        assert NODE_ID not in harness.nodes
    finally:
        harness.close()


def test_stale_task_lease_marker_is_rejected_after_credential_rotation_and_card_loss():
    harness = AuthHTTPHarness(
        auth_epoch=2, marker_epoch=2, node_present=False, task_marker_epoch=1,
    )
    try:
        path, body, _ = endpoint_case("task_heartbeat")
        raw = compact_json(body)
        before = harness.snapshot()
        status, payload = harness.post(
            path,
            body,
            headers=signed_headers(harness.control, path, raw, epoch=2),
            raw_body=raw,
        )
        assert status == 403
        assert payload == {"error": "external_provider_actor_credential_epoch_invalid"}
        assert harness.snapshot() == before
    finally:
        harness.close()


def test_external_provider_task_annotation_is_always_denied():
    harness = AuthHTTPHarness()
    try:
        path = f"/v1/tasks/{TASK_ID}/annotate"
        body = {"result": {"output": "unfenced mutation"}}
        before = harness.snapshot()
        status, payload = harness.post(path, body)
        assert status == 403
        assert payload == {"error": "external_provider_actor_annotate_forbidden"}
        assert harness.snapshot() == before
    finally:
        harness.close()


def test_physical_mesh_node_heartbeat_remains_compatible_without_provider_auth():
    harness = AuthHTTPHarness(physical_node=True)
    try:
        path = f"/v1/nodes/{NODE_ID}/heartbeat"
        body = {
            "node_id": NODE_ID,
            "agent_id": AGENT_ID,
            "capabilities": ["generic_implementation"],
            "labels": {},
        }
        status, payload = harness.post(path, body)
        assert status == 200
        assert payload["node_id"] == NODE_ID
        assert "external_provider_auth" not in payload
        assert not harness.redis.nonces
    finally:
        harness.close()


def test_auth_responses_and_standard_request_logs_never_reflect_secret_material(capsys):
    harness = AuthHTTPHarness()
    try:
        path, body, _ = endpoint_case("node_heartbeat")
        raw = compact_json(body)
        headers = signed_headers(harness.control, path, raw, token=WRONG_TOKEN)
        status, payload = harness.post(path, body, headers=headers, raw_body=raw)
        assert status == 401
        captured = capsys.readouterr()
        visible = json.dumps(payload, sort_keys=True) + captured.out + captured.err
        for forbidden in (
            TOKEN,
            WRONG_TOKEN,
            hashlib.sha256(TOKEN.encode()).hexdigest(),
            hashlib.sha256(WRONG_TOKEN.encode()).hexdigest(),
        ):
            assert forbidden not in visible
    finally:
        harness.close()
