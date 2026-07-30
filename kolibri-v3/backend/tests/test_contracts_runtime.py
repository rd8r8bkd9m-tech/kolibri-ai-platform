from __future__ import annotations

from typing import Any, Mapping

from app.provider_execution import _generated_contracts


def _violation_codes(
    value: Any,
    schema: Mapping[str, Any],
) -> list[str]:
    runtime = _generated_contracts()
    violations: list[Any] = []
    runtime._collect(value, schema, schema, "/", violations)
    return [violation.code for violation in violations]


def test_contains_defaults_to_at_least_one_match() -> None:
    schema = {
        "type": "array",
        "contains": {"const": "display"},
    }

    assert _violation_codes(["audio", "display"], schema) == []
    assert _violation_codes(["audio", "speech"], schema) == ["contains"]
    assert _violation_codes([], schema) == ["contains"]


def test_contains_honors_explicit_match_count_limits() -> None:
    schema = {
        "type": "array",
        "contains": {"const": "display"},
        "minContains": 2,
        "maxContains": 3,
    }

    assert _violation_codes(["display", "display"], schema) == []
    assert _violation_codes(["display"], schema) == ["minContains"]
    assert _violation_codes(["display"] * 4, schema) == ["maxContains"]


def test_exclusive_minimum_rejects_the_boundary() -> None:
    schema = {
        "type": "number",
        "exclusiveMinimum": 0,
    }

    assert _violation_codes(0.1, schema) == []
    assert _violation_codes(0, schema) == ["exclusiveMinimum"]
    assert _violation_codes(-0.1, schema) == ["exclusiveMinimum"]


def test_object_property_count_limits_are_inclusive() -> None:
    schema = {
        "type": "object",
        "minProperties": 2,
        "maxProperties": 3,
    }

    assert _violation_codes({"one": 1, "two": 2}, schema) == []
    assert _violation_codes(
        {"one": 1, "two": 2, "three": 3},
        schema,
    ) == []
    assert _violation_codes({"one": 1}, schema) == ["minProperties"]
    assert _violation_codes(
        {"one": 1, "two": 2, "three": 3, "four": 4},
        schema,
    ) == ["maxProperties"]
