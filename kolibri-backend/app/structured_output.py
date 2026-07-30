"""Bounded strict JSON-schema output contract for public AI APIs.

This is intentionally a small, auditable subset rather than a permissive
partial implementation of the full JSON Schema specification.  Unsupported
keywords fail at request validation; provider output is parsed and validated
before it is exposed as a successful structured response.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
import math
import re
from typing import Any


MAX_SCHEMA_BYTES = 32 * 1024
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_DEPTH = 8
MAX_NODES = 256
MAX_PROPERTIES = 128
MAX_ARRAY_ITEMS = 10_000
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_COMMON = {"type", "description", "title", "enum", "const"}
_KEYWORDS = {
    "object": _COMMON | {"properties", "required", "additionalProperties"},
    "array": _COMMON | {"items", "minItems", "maxItems"},
    "string": _COMMON | {"minLength", "maxLength"},
    "number": _COMMON | {"minimum", "maximum"},
    "integer": _COMMON | {"minimum", "maximum"},
    "boolean": _COMMON,
    "null": _COMMON,
}


class StructuredOutputError(ValueError):
    def __init__(self, code: str, *, path: str = "$", message: str | None = None):
        self.code = code
        self.path = path
        self.safe_message = message or code
        super().__init__(f"{code} at {path}")


@dataclass(frozen=True, slots=True)
class StructuredOutputSpec:
    name: str
    schema: dict[str, Any]


def _json_size(value: Any) -> int:
    try:
        return len(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        )
    except (TypeError, ValueError) as exc:
        raise StructuredOutputError("json_schema_not_serializable") from exc


def _bounded_int(value: Any, *, path: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise StructuredOutputError("json_schema_bound_invalid", path=path)
    return value


def _finite_number(value: Any, *, path: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise StructuredOutputError("json_schema_number_invalid", path=path)
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise StructuredOutputError("json_schema_number_invalid", path=path) from exc
    if not parsed.is_finite():
        raise StructuredOutputError("json_schema_number_invalid", path=path)
    return parsed


def validate_schema(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict) or _json_size(schema) > MAX_SCHEMA_BYTES:
        raise StructuredOutputError("json_schema_invalid")
    nodes = 0

    def visit(node: Any, path: str, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if depth > MAX_DEPTH or nodes > MAX_NODES or not isinstance(node, dict):
            raise StructuredOutputError("json_schema_too_complex", path=path)
        schema_type = node.get("type")
        if schema_type not in _KEYWORDS:
            raise StructuredOutputError("json_schema_type_unsupported", path=f"{path}.type")
        unexpected = set(node) - _KEYWORDS[schema_type]
        if unexpected:
            raise StructuredOutputError(
                "json_schema_keyword_unsupported",
                path=f"{path}.{sorted(unexpected)[0]}",
            )
        if "enum" in node:
            enum = node["enum"]
            if not isinstance(enum, list) or not 1 <= len(enum) <= 128 or _json_size(enum) > 16_384:
                raise StructuredOutputError("json_schema_enum_invalid", path=f"{path}.enum")
        if "const" in node:
            _json_size(node["const"])
        if schema_type == "object":
            properties = node.get("properties")
            required = node.get("required")
            if not isinstance(properties, dict) or len(properties) > MAX_PROPERTIES:
                raise StructuredOutputError("json_schema_properties_invalid", path=f"{path}.properties")
            if not all(isinstance(key, str) and 1 <= len(key) <= 128 for key in properties):
                raise StructuredOutputError("json_schema_property_name_invalid", path=f"{path}.properties")
            if not isinstance(required, list) or len(required) != len(set(required)):
                raise StructuredOutputError("json_schema_required_invalid", path=f"{path}.required")
            if set(required) != set(properties):
                raise StructuredOutputError("json_schema_strict_required_mismatch", path=f"{path}.required")
            if node.get("additionalProperties") is not False:
                raise StructuredOutputError(
                    "json_schema_additional_properties_must_be_false",
                    path=f"{path}.additionalProperties",
                )
            for key, child in properties.items():
                visit(child, f"{path}.properties.{key}", depth + 1)
        elif schema_type == "array":
            if "items" not in node:
                raise StructuredOutputError("json_schema_items_required", path=f"{path}.items")
            minimum = _bounded_int(node.get("minItems", 0), path=f"{path}.minItems", maximum=MAX_ARRAY_ITEMS)
            maximum = _bounded_int(node.get("maxItems", MAX_ARRAY_ITEMS), path=f"{path}.maxItems", maximum=MAX_ARRAY_ITEMS)
            if minimum > maximum:
                raise StructuredOutputError("json_schema_bounds_inverted", path=path)
            visit(node["items"], f"{path}.items", depth + 1)
        elif schema_type == "string":
            minimum = _bounded_int(node.get("minLength", 0), path=f"{path}.minLength", maximum=MAX_OUTPUT_BYTES)
            maximum = _bounded_int(node.get("maxLength", MAX_OUTPUT_BYTES), path=f"{path}.maxLength", maximum=MAX_OUTPUT_BYTES)
            if minimum > maximum:
                raise StructuredOutputError("json_schema_bounds_inverted", path=path)
        elif schema_type in {"number", "integer"}:
            minimum = _finite_number(node["minimum"], path=f"{path}.minimum") if "minimum" in node else None
            maximum = _finite_number(node["maximum"], path=f"{path}.maximum") if "maximum" in node else None
            if minimum is not None and maximum is not None and minimum > maximum:
                raise StructuredOutputError("json_schema_bounds_inverted", path=path)

    visit(schema, "$", 0)
    # Detach the validated schema from request-owned mutable data.
    return json.loads(json.dumps(schema, ensure_ascii=False, allow_nan=False))


def _spec(name: Any, schema: Any, strict: Any) -> StructuredOutputSpec:
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise StructuredOutputError("json_schema_name_invalid")
    if strict is not True:
        raise StructuredOutputError("json_schema_strict_required")
    return StructuredOutputSpec(name=name, schema=validate_schema(schema))


def responses_spec(text: Any) -> StructuredOutputSpec | None:
    if text is None:
        return None
    if not isinstance(text, dict):
        raise StructuredOutputError("response_text_format_invalid")
    format_value = text.get("format")
    if not isinstance(format_value, dict) or format_value.get("type") != "json_schema":
        raise StructuredOutputError("response_text_format_unsupported")
    if set(format_value) - {"type", "name", "schema", "strict"}:
        raise StructuredOutputError("response_text_format_invalid")
    return _spec(format_value.get("name"), format_value.get("schema"), format_value.get("strict"))


def chat_spec(response_format: Any) -> StructuredOutputSpec | None:
    if response_format is None:
        return None
    if not isinstance(response_format, dict) or response_format.get("type") != "json_schema":
        raise StructuredOutputError("response_format_unsupported")
    if set(response_format) - {"type", "json_schema"}:
        raise StructuredOutputError("response_format_invalid")
    value = response_format.get("json_schema")
    if not isinstance(value, dict) or set(value) - {"name", "schema", "strict"}:
        raise StructuredOutputError("response_format_invalid")
    return _spec(value.get("name"), value.get("schema"), value.get("strict"))


def instruction(spec: StructuredOutputSpec) -> str:
    schema = json.dumps(spec.schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (
        "Верни только один JSON-документ без Markdown, пояснений и code fence. "
        f"Он обязан строго соответствовать схеме {spec.name}: {schema}. "
        "Не добавляй поля, которых нет в properties."
    )


def _same_json(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    return left == right


def validate_value(value: Any, schema: dict[str, Any], *, path: str = "$") -> None:
    if "enum" in schema and not any(_same_json(value, candidate) for candidate in schema["enum"]):
        raise StructuredOutputError("structured_output_enum_mismatch", path=path)
    if "const" in schema and not _same_json(value, schema["const"]):
        raise StructuredOutputError("structured_output_const_mismatch", path=path)
    schema_type = schema["type"]
    if schema_type == "null":
        valid = value is None
    elif schema_type == "boolean":
        valid = isinstance(value, bool)
    elif schema_type == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif schema_type == "number":
        valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    elif schema_type == "string":
        valid = isinstance(value, str)
    elif schema_type == "array":
        valid = isinstance(value, list)
    else:
        valid = isinstance(value, dict)
    if not valid:
        raise StructuredOutputError("structured_output_type_mismatch", path=path)

    if schema_type == "object":
        expected = set(schema["properties"])
        actual = set(value)
        if actual != expected:
            raise StructuredOutputError("structured_output_properties_mismatch", path=path)
        for key, child in schema["properties"].items():
            validate_value(value[key], child, path=f"{path}.{key}")
    elif schema_type == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", MAX_ARRAY_ITEMS):
            raise StructuredOutputError("structured_output_array_length", path=path)
        for index, item in enumerate(value):
            validate_value(item, schema["items"], path=f"{path}[{index}]")
    elif schema_type == "string":
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", MAX_OUTPUT_BYTES):
            raise StructuredOutputError("structured_output_string_length", path=path)
    elif schema_type in {"number", "integer"}:
        numeric = Decimal(str(value))
        if "minimum" in schema and numeric < Decimal(str(schema["minimum"])):
            raise StructuredOutputError("structured_output_number_minimum", path=path)
        if "maximum" in schema and numeric > Decimal(str(schema["maximum"])):
            raise StructuredOutputError("structured_output_number_maximum", path=path)


def parse_and_validate(raw: str, spec: StructuredOutputSpec) -> tuple[str, Any]:
    if not isinstance(raw, str) or not raw.strip() or len(raw.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise StructuredOutputError("structured_output_size_invalid")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StructuredOutputError("structured_output_invalid_json") from exc
    validate_value(value, spec.schema)
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return canonical, value


__all__ = [
    "StructuredOutputError",
    "StructuredOutputSpec",
    "chat_spec",
    "instruction",
    "parse_and_validate",
    "responses_spec",
    "validate_schema",
    "validate_value",
]
