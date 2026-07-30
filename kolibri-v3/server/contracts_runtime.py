"""Manifest-verified contract runtime bundled with the Kolibri V3 release.

The release owns both this validator and ``kolibri-v3/contracts``.  No runtime
path may escape the V3 root to borrow generated code from another checkout.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Literal, Mapping


JSON_SAFE_INTEGER_MAX = 9_007_199_254_740_991
RFC3339_DATE_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$",
)
V3_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = V3_ROOT / "contracts" / "v1"
MANIFEST_PATH = V3_ROOT / "contracts" / "generated" / "v1" / "manifest.json"


AuthorityRole = Literal[
    "logical_home_control_plane",
    "product_data_authority",
    "provider_execution_authority",
]


def _canonical_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    )


def _load_registry() -> tuple[
    dict[str, Mapping[str, Any]],
    dict[str, dict[str, Any]],
]:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("V3 contract manifest is unavailable") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_id")
        != "kolibri.generated_contract_package_manifest"
        or manifest.get("schema_version") != "1.0"
        or not isinstance(manifest.get("schemas"), list)
        or manifest.get("schema_count") != len(manifest["schemas"])
    ):
        raise RuntimeError("V3 contract manifest is invalid")

    schemas: dict[str, Mapping[str, Any]] = {}
    specs: dict[str, dict[str, Any]] = {}
    for entry in manifest["schemas"]:
        if not isinstance(entry, dict):
            raise RuntimeError("V3 contract manifest entry is invalid")
        source_path = entry.get("source_path")
        expected_hash = entry.get("sha256")
        expected_uri = entry.get("schema_uri")
        if (
            not isinstance(source_path, str)
            or not source_path.startswith("contracts/v1/")
            or not isinstance(expected_hash, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None
            or not isinstance(expected_uri, str)
        ):
            raise RuntimeError("V3 contract manifest entry is invalid")
        relative = source_path.removeprefix("contracts/v1/")
        schema_path = (CONTRACT_ROOT / relative).resolve()
        if not schema_path.is_relative_to(CONTRACT_ROOT.resolve()):
            raise RuntimeError("V3 contract manifest path escapes release")
        try:
            raw = schema_path.read_bytes()
            schema = json.loads(raw.decode("utf-8", "strict"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("V3 contract schema is unavailable") from exc
        if (
            hashlib.sha256(raw).hexdigest() != expected_hash
            or not isinstance(schema, dict)
            or schema.get("$id") != expected_uri
            or expected_uri in schemas
        ):
            raise RuntimeError("V3 contract schema integrity check failed")
        schemas[expected_uri] = schema

        properties = schema.get("properties")
        if not isinstance(properties, dict):
            continue
        schema_id_property = properties.get("schema_id")
        version_property = properties.get("schema_version")
        schema_id = (
            schema_id_property.get("const")
            if isinstance(schema_id_property, dict)
            else None
        )
        schema_version = (
            version_property.get("const")
            if isinstance(version_property, dict)
            else None
        )
        if isinstance(schema_id, str) and isinstance(schema_version, str):
            if schema_id in specs:
                raise RuntimeError("V3 contract schema ID is duplicated")
            specs[schema_id] = {
                "schema_uri": expected_uri,
                "schema_version": schema_version,
            }

    if (
        len(schemas) != manifest["schema_count"]
        or len(specs) != manifest.get("contract_count")
    ):
        raise RuntimeError("V3 contract registry is incomplete")
    return schemas, specs


SCHEMAS, CONTRACT_SPECS = _load_registry()


@dataclass(frozen=True)
class ContractViolation:
    path: str
    code: str


@dataclass(frozen=True)
class ContractValidationResult:
    ok: bool
    code: str | None
    violations: tuple[ContractViolation, ...]


class ContractValidationError(ValueError):
    def __init__(self, result: ContractValidationResult) -> None:
        self.result = result
        super().__init__(result.code or "contract_validation_failed")


def _pointer(document: Any, fragment: str) -> Any:
    current = document
    if not fragment:
        return current
    if not fragment.startswith("/"):
        raise ValueError("unsupported_schema_pointer")
    for raw in fragment[1:].split("/"):
        current = current[raw.replace("~1", "/").replace("~0", "~")]
    return current


def _resolve(
    ref: str,
    root_schema: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    if ref.startswith("#"):
        return _pointer(root_schema, ref[1:]), root_schema
    uri, _, fragment = ref.partition("#")
    target_root = SCHEMAS[uri]
    return _pointer(target_root, fragment), target_root


def _is_type(value: Any, schema_type: str) -> bool:
    if schema_type == "object":
        return isinstance(value, Mapping)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and abs(value) <= JSON_SAFE_INTEGER_MAX
        )
    if schema_type == "number":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "null":
        return value is None
    return True


def _child_path(path: str, segment: str | int) -> str:
    encoded = str(segment).replace("~", "~0").replace("/", "~1")
    return f"/{encoded}" if path == "/" else f"{path}/{encoded}"


def _collect(
    value: Any,
    schema: Mapping[str, Any],
    root_schema: Mapping[str, Any],
    path: str,
    violations: list[ContractViolation],
    depth: int = 0,
) -> None:
    if depth > 80:
        violations.append(
            ContractViolation(path, "schema_depth_exceeded")
        )
        return
    ref = schema.get("$ref")
    if isinstance(ref, str):
        resolved, resolved_root = _resolve(ref, root_schema)
        _collect(value, resolved, resolved_root, path, violations, depth + 1)
        return

    if "const" in schema and value != schema["const"]:
        violations.append(ContractViolation(path, "const"))
    if "enum" in schema and value not in schema["enum"]:
        violations.append(ContractViolation(path, "enum"))

    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        matches = 0
        for option in one_of:
            candidate: list[ContractViolation] = []
            _collect(value, option, root_schema, path, candidate, depth + 1)
            if not candidate:
                matches += 1
        if matches != 1:
            violations.append(ContractViolation(path, "oneOf"))

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        if not any(_is_type(value, item) for item in schema_type):
            violations.append(ContractViolation(path, "type"))
            return
    elif isinstance(schema_type, str) and not _is_type(value, schema_type):
        violations.append(ContractViolation(path, "type"))
        return

    if isinstance(value, Mapping):
        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        minimum_properties = schema.get("minProperties")
        maximum_properties = schema.get("maxProperties")
        if (
            isinstance(minimum_properties, int)
            and not isinstance(minimum_properties, bool)
            and len(value) < minimum_properties
        ):
            violations.append(ContractViolation(path, "minProperties"))
        if (
            isinstance(maximum_properties, int)
            and not isinstance(maximum_properties, bool)
            and len(value) > maximum_properties
        ):
            violations.append(ContractViolation(path, "maxProperties"))
        for key in required:
            if key not in value:
                violations.append(
                    ContractViolation(_child_path(path, key), "required")
                )
        additional_properties = schema.get("additionalProperties")
        if additional_properties is False:
            for key in value:
                if key not in properties:
                    violations.append(
                        ContractViolation(
                            _child_path(path, key),
                            "additionalProperties",
                        )
                    )
        elif isinstance(additional_properties, Mapping):
            for key, item in value.items():
                if key not in properties:
                    _collect(
                        item,
                        additional_properties,
                        root_schema,
                        _child_path(path, key),
                        violations,
                        depth + 1,
                    )
        for key, child in properties.items():
            if key in value:
                _collect(
                    value[key],
                    child,
                    root_schema,
                    _child_path(path, key),
                    violations,
                    depth + 1,
                )

    if isinstance(value, list):
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        if isinstance(minimum, int) and len(value) < minimum:
            violations.append(ContractViolation(path, "minItems"))
        if isinstance(maximum, int) and len(value) > maximum:
            violations.append(ContractViolation(path, "maxItems"))
        contains = schema.get("contains")
        if isinstance(contains, Mapping):
            match_count = 0
            for index, item in enumerate(value):
                candidate: list[ContractViolation] = []
                _collect(
                    item,
                    contains,
                    root_schema,
                    _child_path(path, index),
                    candidate,
                    depth + 1,
                )
                if not candidate:
                    match_count += 1

            minimum_contains = schema.get("minContains", 1)
            maximum_contains = schema.get("maxContains")
            if (
                isinstance(minimum_contains, int)
                and not isinstance(minimum_contains, bool)
                and match_count < minimum_contains
            ):
                code = (
                    "minContains"
                    if "minContains" in schema
                    else "contains"
                )
                violations.append(ContractViolation(path, code))
            if (
                isinstance(maximum_contains, int)
                and not isinstance(maximum_contains, bool)
                and match_count > maximum_contains
            ):
                violations.append(ContractViolation(path, "maxContains"))
        if schema.get("uniqueItems"):
            encoded = [
                json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                for item in value
            ]
            if len(encoded) != len(set(encoded)):
                violations.append(ContractViolation(path, "uniqueItems"))
        child = schema.get("items")
        if isinstance(child, Mapping):
            for index, item in enumerate(value):
                _collect(
                    item,
                    child,
                    root_schema,
                    _child_path(path, index),
                    violations,
                    depth + 1,
                )

    if isinstance(value, str):
        minimum = schema.get("minLength")
        maximum = schema.get("maxLength")
        if isinstance(minimum, int) and len(value) < minimum:
            violations.append(ContractViolation(path, "minLength"))
        if isinstance(maximum, int) and len(value) > maximum:
            violations.append(ContractViolation(path, "maxLength"))
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            violations.append(ContractViolation(path, "pattern"))
        if schema.get("format") == "date-time":
            try:
                if RFC3339_DATE_TIME.fullmatch(value) is None:
                    raise ValueError
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError
            except ValueError:
                violations.append(ContractViolation(path, "format"))

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        exclusive_minimum = schema.get("exclusiveMinimum")
        if isinstance(minimum, (int, float)) and value < minimum:
            violations.append(ContractViolation(path, "minimum"))
        if isinstance(maximum, (int, float)) and value > maximum:
            violations.append(ContractViolation(path, "maximum"))
        if (
            isinstance(exclusive_minimum, (int, float))
            and not isinstance(exclusive_minimum, bool)
            and value <= exclusive_minimum
        ):
            violations.append(
                ContractViolation(path, "exclusiveMinimum")
            )

    for clause in schema.get("allOf") or []:
        _collect(value, clause, root_schema, path, violations, depth + 1)

    condition = schema.get("if")
    if isinstance(condition, Mapping):
        condition_violations: list[ContractViolation] = []
        _collect(
            value,
            condition,
            root_schema,
            path,
            condition_violations,
            depth + 1,
        )
        branch = (
            schema.get("then")
            if not condition_violations
            else schema.get("else")
        )
        if isinstance(branch, Mapping):
            _collect(
                value,
                branch,
                root_schema,
                path,
                violations,
                depth + 1,
            )


def validate_contract(
    value: Any,
    expected_schema_id: str | None = None,
) -> ContractValidationResult:
    if not isinstance(value, Mapping):
        return ContractValidationResult(
            False,
            "invalid_contract",
            (ContractViolation("/", "type"),),
        )
    schema_id = value.get("schema_id")
    spec = CONTRACT_SPECS.get(schema_id)
    if (
        spec is None
        or (
            expected_schema_id is not None
            and schema_id != expected_schema_id
        )
        or value.get("schema_version") != spec["schema_version"]
    ):
        return ContractValidationResult(
            False,
            "unsupported_schema",
            (
                ContractViolation(
                    "/schema_version",
                    "unsupported_schema",
                ),
            ),
        )
    root_schema = SCHEMAS[spec["schema_uri"]]
    violations: list[ContractViolation] = []
    _collect(value, root_schema, root_schema, "/", violations)
    return ContractValidationResult(
        not violations,
        None if not violations else "invalid_contract",
        tuple(violations),
    )


def parse_contract(
    value: Mapping[str, Any],
    expected_schema_id: str | None = None,
) -> dict[str, Any]:
    result = validate_contract(value, expected_schema_id)
    if not result.ok:
        raise ContractValidationError(result)
    return _canonical_copy(value)


@dataclass(frozen=True)
class ContractBoundaryClient:
    authority_role: AuthorityRole

    def validate_inbound(
        self,
        value: Any,
        expected_schema_id: str | None = None,
    ) -> ContractValidationResult:
        return validate_contract(value, expected_schema_id)

    def prepare_outbound(
        self,
        value: Mapping[str, Any],
        expected_schema_id: str | None = None,
    ) -> dict[str, Any]:
        return parse_contract(value, expected_schema_id)
