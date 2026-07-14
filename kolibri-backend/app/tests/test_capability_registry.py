from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import capability_registry
from app.capability_registry import (
    CapabilityEvidence,
    CapabilityNotInvocable,
    CapabilityRegistry,
    CapabilitySpec,
    CredentialEvidence,
    InvocationProbe,
    PolicyEvidence,
    ProbeState,
    RendererEvidence,
    RouteEvidence,
    evaluate_capability,
)


NOW = datetime(2026, 7, 14, 10, 0, tzinfo=timezone.utc)
SPEC = CapabilitySpec(
    id="image.generate",
    name="Изображения",
    description="Создание проверенного растрового артефакта.",
    kind="media",
)


def evidence(
    *,
    policy: bool | None = True,
    renderer_registered: bool = True,
    renderer_healthy: bool | None = True,
    credential_present: bool = True,
    credential_source_permitted: bool = True,
    route_configured: bool = True,
    route_permitted: bool = True,
    probe_state: ProbeState = ProbeState.NEVER,
    probe_checked_at: datetime | None = None,
    route_id: str = "codex_cli",
) -> CapabilityEvidence:
    return CapabilityEvidence(
        policy=PolicyEvidence(
            evaluated=policy is not None,
            permitted=policy is True,
            decision_id="decision-1" if policy is not None else None,
            checked_at=NOW,
        ),
        renderer=RendererEvidence(
            renderer_id="image",
            registered=renderer_registered,
            healthy=renderer_healthy,
            checked_at=NOW,
            evidence_id="renderer-check-1",
        ),
        routes=(
            RouteEvidence(
                route_id=route_id,
                configured=route_configured,
                permitted=route_permitted,
                credential=CredentialEvidence(
                    required=True,
                    present=credential_present,
                    source="home_codex_cli_login",
                    source_permitted=credential_source_permitted,
                    checked_at=NOW,
                    evidence_id="credential-check-1",
                ),
                probe=InvocationProbe(
                    state=probe_state,
                    checked_at=probe_checked_at,
                    ttl_seconds=300,
                    evidence_id="invocation-1" if probe_checked_at else None,
                    provider="codex_cli" if probe_checked_at else None,
                    model="account-default" if probe_checked_at else None,
                    error_code="upstream_failed" if probe_state is ProbeState.FAILED else None,
                ),
            ),
        ),
    )


def test_catalog_entry_and_credential_do_not_claim_available_without_invocation():
    result = evaluate_capability(SPEC, evidence(), now=NOW)

    assert result["catalog_listed"] is True
    assert result["status"] == "degraded"
    assert result["invocable"] is False
    assert result["reason"]["code"] == "probe_not_run"
    assert result["source"] == {"type": "runtime_evidence"}


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"policy": None}, "policy_not_evaluated"),
        ({"policy": False}, "policy_denied"),
        ({"renderer_registered": False}, "renderer_missing"),
        ({"renderer_healthy": False}, "renderer_unhealthy"),
        ({"credential_present": False}, "credential_missing"),
        ({"credential_source_permitted": False}, "credential_source_forbidden"),
        ({"route_configured": False}, "route_not_configured"),
        ({"route_permitted": False}, "route_not_permitted"),
    ],
)
def test_hard_gates_fail_closed(changes, reason):
    result = evaluate_capability(SPEC, evidence(**changes), now=NOW)

    assert result["status"] == "unavailable"
    assert result["invocable"] is False
    assert result["reason"]["code"] == reason


def test_fresh_success_is_the_only_available_state():
    result = evaluate_capability(
        SPEC,
        evidence(probe_state=ProbeState.SUCCEEDED, probe_checked_at=NOW - timedelta(seconds=5)),
        now=NOW,
    )

    assert result["status"] == "available"
    assert result["invocable"] is True
    assert result["selected_route_id"] == "codex_cli"
    assert result["reason"]["code"] == "live_invocation"
    assert result["source"] == {"type": "live_invocation"}
    assert "secret" not in str(result).lower()


def test_stale_success_and_unverified_renderer_are_degraded():
    stale = evaluate_capability(
        SPEC,
        evidence(probe_state=ProbeState.SUCCEEDED, probe_checked_at=NOW - timedelta(seconds=301)),
        now=NOW,
    )
    unverified_renderer = evaluate_capability(
        SPEC,
        evidence(
            renderer_healthy=None,
            probe_state=ProbeState.SUCCEEDED,
            probe_checked_at=NOW,
        ),
        now=NOW,
    )

    assert (stale["status"], stale["reason"]["code"]) == ("degraded", "probe_stale")
    assert (unverified_renderer["status"], unverified_renderer["reason"]["code"]) == (
        "degraded",
        "renderer_health_unverified",
    )
    assert unverified_renderer["invocable"] is False


def test_live_fallback_keeps_capability_available_after_primary_failure():
    primary = evidence(
        probe_state=ProbeState.FAILED,
        probe_checked_at=NOW,
        route_id="mimo",
    ).routes[0]
    fallback = evidence(
        probe_state=ProbeState.SUCCEEDED,
        probe_checked_at=NOW - timedelta(seconds=2),
        route_id="codex_cli",
    ).routes[0]
    runtime = evidence()
    runtime = CapabilityEvidence(runtime.policy, runtime.renderer, (primary, fallback))

    result = evaluate_capability(SPEC, runtime, now=NOW)

    assert result["status"] == "available"
    assert result["selected_route_id"] == "codex_cli"
    assert {route["probe"]["state"] for route in result["routes"]} == {"failed", "succeeded"}


def test_all_fresh_invocations_failed_is_unavailable():
    result = evaluate_capability(
        SPEC,
        evidence(probe_state=ProbeState.FAILED, probe_checked_at=NOW),
        now=NOW,
    )

    assert result["status"] == "unavailable"
    assert result["reason"]["code"] == "invocation_failed"


def test_registry_re_evaluates_dynamic_evidence_and_builds_truthful_self_description():
    state = {
        "images": evidence(),
        "research": evidence(
            probe_state=ProbeState.SUCCEEDED,
            probe_checked_at=NOW,
            route_id="openai_web_search",
        ),
    }
    registry = CapabilityRegistry()
    registry.register(SPEC, lambda: state["images"])
    registry.register(
        CapabilitySpec("research.web", "Веб-поиск", "Поиск с источниками.", "research"),
        lambda: state["research"],
    )

    first = registry.self_description(now=NOW)
    assert "Сейчас подтверждено, что я могу: Веб-поиск." in first["content"]
    assert "Ограниченно доступно" in first["content"]
    assert [item["id"] for item in first["capabilities"]["available"]] == ["research.web"]
    assert [item["id"] for item in first["capabilities"]["degraded"]] == ["image.generate"]

    state["images"] = evidence(
        probe_state=ProbeState.SUCCEEDED,
        probe_checked_at=NOW + timedelta(seconds=1),
    )
    second = registry.self_description(now=NOW + timedelta(seconds=1))
    assert {item["id"] for item in second["capabilities"]["available"]} == {
        "image.generate",
        "research.web",
    }
    assert second["capabilities"]["degraded"] == []


def test_evidence_provider_failure_is_sanitised_and_unavailable():
    registry = CapabilityRegistry()

    def broken_provider():
        raise RuntimeError("secret-token-must-not-leak")

    registry.register(SPEC, broken_provider)
    snapshot = registry.snapshot(now=NOW)
    item = snapshot["capabilities"][0]

    assert item["status"] == "unavailable"
    assert item["reason"]["code"] == "evidence_provider_failed"
    assert item["error_type"] == "RuntimeError"
    assert "secret-token-must-not-leak" not in str(snapshot)


def test_duplicate_registration_is_rejected():
    registry = CapabilityRegistry()
    registry.register(SPEC, lambda: evidence())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(SPEC, lambda: evidence())


def test_record_invocation_get_and_assert_invocable_contract():
    registry = CapabilityRegistry()
    registry.register(SPEC, lambda: evidence())

    initial = registry.get(SPEC.id, now=NOW)
    assert initial is not None
    assert initial["status"] == "degraded"
    with pytest.raises(CapabilityNotInvocable) as blocked:
        registry.assert_invocable(SPEC.id, now=NOW)
    assert blocked.value.reason_code == "probe_not_run"

    registry.record_invocation(
        SPEC.id,
        "codex_cli",
        succeeded=True,
        checked_at=NOW,
        evidence_id="cas:sha256:123",
        provider="codex_cli",
        model="account-default",
    )
    available = registry.assert_invocable(SPEC.id, now=NOW)
    assert available["status"] == "available"
    assert available["routes"][0]["probe"]["evidence_id"] == "cas:sha256:123"

    registry.record_invocation(
        SPEC.id,
        "codex_cli",
        succeeded=False,
        checked_at=NOW + timedelta(seconds=1),
        error_code="provider_timeout",
    )
    failed = registry.get(SPEC.id, now=NOW + timedelta(seconds=1))
    assert failed is not None
    assert failed["status"] == "unavailable"
    assert failed["routes"][0]["probe"]["error_code"] == "provider_timeout"


def test_record_invocation_rejects_unknown_capability_and_route():
    registry = CapabilityRegistry()
    registry.register(SPEC, lambda: evidence())

    with pytest.raises(KeyError, match="unknown capability"):
        registry.record_invocation("missing", "codex_cli", succeeded=True, checked_at=NOW)
    with pytest.raises(KeyError, match="unknown route"):
        registry.record_invocation(SPEC.id, "missing", succeeded=True, checked_at=NOW)


def test_module_level_router_api_uses_canonical_registry():
    spec = CapabilitySpec(
        "test.dynamic",
        "Тестовая возможность",
        "Только для проверки canonical API.",
        "test",
    )
    capability_registry.register_capability(spec, lambda: evidence())
    try:
        assert capability_registry.get_capability(spec.id, now=NOW)["status"] == "degraded"
        capability_registry.record_invocation(
            spec.id,
            "codex_cli",
            succeeded=True,
            checked_at=NOW,
            evidence_id="test-proof",
        )
        assert capability_registry.assert_invocable(spec.id, now=NOW)["invocable"] is True
    finally:
        capability_registry.runtime_registry.unregister(spec.id)
