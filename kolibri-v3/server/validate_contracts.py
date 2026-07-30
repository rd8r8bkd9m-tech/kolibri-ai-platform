#!/usr/bin/env python3
"""Validate every V1 JSON schema and its valid/invalid examples."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema.validators import validator_for
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1] / "contracts" / "v1"


def load_contracts() -> tuple[
    dict[Path, dict[str, object]],
    dict[str, dict[str, object]],
    dict[str, tuple[Path, dict[str, object]]],
]:
    schemas_by_path: dict[Path, dict[str, object]] = {}
    schemas_by_uri: dict[str, dict[str, object]] = {}
    schemas_by_logical_id: dict[str, tuple[Path, dict[str, object]]] = {}
    for path in sorted(ROOT.rglob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        validator_for(schema).check_schema(schema)
        uri = schema.get("$id")
        if not isinstance(uri, str) or not uri:
            raise ValueError(f"{path}: schema has no non-empty $id")
        if uri in schemas_by_uri:
            raise ValueError(f"{path}: duplicate schema $id {uri!r}")
        logical_id = (
            schema.get("properties", {})
            .get("schema_id", {})  # type: ignore[union-attr]
            .get("const")  # type: ignore[union-attr]
        )
        if logical_id is not None:
            if not isinstance(logical_id, str):
                raise ValueError(f"{path}: logical schema_id is not a string")
            if logical_id in schemas_by_logical_id:
                raise ValueError(
                    f"{path}: duplicate logical schema_id {logical_id!r}"
                )
            schemas_by_logical_id[logical_id] = (path, schema)
        schemas_by_path[path] = schema
        schemas_by_uri[uri] = schema
    if not schemas_by_path:
        raise ValueError("no JSON schemas found under contracts/v1")
    return schemas_by_path, schemas_by_uri, schemas_by_logical_id


def schema_for_example(
    path: Path,
    instance: object,
    *,
    schemas_by_path: dict[Path, dict[str, object]],
    schemas_by_logical_id: dict[str, tuple[Path, dict[str, object]]],
    registry: Registry,
) -> tuple[Path, dict[str, object]]:
    logical_id = instance.get("schema_id") if isinstance(instance, dict) else None
    if isinstance(logical_id, str) and logical_id in schemas_by_logical_id:
        return schemas_by_logical_id[logical_id]

    name = path.stem
    if name.startswith("valid-"):
        name = name.removeprefix("valid-")
    elif name.startswith("invalid-"):
        invalid_name = name.removeprefix("invalid-")
        domain_candidates = [
            (schema_path, schema)
            for schema_path, schema in schemas_by_path.items()
            if schema_path.parent == path.parent.parent
        ]
        prefix_matches = [
            (schema_path, schema)
            for schema_path, schema in domain_candidates
            if (
                invalid_name == schema_path.name.removesuffix(".schema.json")
                or invalid_name.startswith(
                    schema_path.name.removesuffix(".schema.json") + "-"
                )
            )
        ]
        if prefix_matches:
            return max(prefix_matches, key=lambda item: len(item[0].name))
        aliases = {"command": "command-envelope.schema.json"}
        alias = invalid_name.split("-", 1)[0]
        alias_name = aliases.get(alias)
        if alias_name is not None:
            alias_path = path.parent.parent / alias_name
            if alias_path in schemas_by_path:
                return alias_path, schemas_by_path[alias_path]
        raise ValueError(
            f"{path}: cannot determine target schema for invalid fixture"
        )

    direct_path = path.parent.parent / f"{name}.schema.json"
    if direct_path in schemas_by_path:
        return direct_path, schemas_by_path[direct_path]
    satisfying: list[tuple[Path, dict[str, object]]] = []
    for schema_path, schema in schemas_by_path.items():
        validator_class = validator_for(schema)
        validator = validator_class(
            schema,
            registry=registry,
            format_checker=validator_class.FORMAT_CHECKER,
        )
        if not list(validator.iter_errors(instance)):
            satisfying.append((schema_path, schema))
    if len(satisfying) == 1:
        return satisfying[0]
    domain_schemas = [
        (schema_path, schema)
        for schema_path, schema in schemas_by_path.items()
        if schema_path.parent == path.parent.parent
    ]
    if len(domain_schemas) == 1:
        return domain_schemas[0]
    raise ValueError(
        f"{path}: cannot determine target schema; "
        "add schema_id or a same-name schema"
    )


def main() -> None:
    schemas_by_path, schemas_by_uri, schemas_by_logical_id = load_contracts()
    example_paths = sorted(ROOT.rglob("examples/*.json"))
    if not example_paths:
        raise ValueError("no JSON examples found under contracts/v1")
    registry = Registry().with_resources(
        (uri, Resource.from_contents(schema))
        for uri, schema in schemas_by_uri.items()
    )
    valid_count = 0
    invalid_count = 0
    for path in example_paths:
        instance = json.loads(path.read_text(encoding="utf-8"))
        schema_path, schema = schema_for_example(
            path,
            instance,
            schemas_by_path=schemas_by_path,
            schemas_by_logical_id=schemas_by_logical_id,
            registry=registry,
        )
        validator_class = validator_for(schema)
        validator = validator_class(
            schema,
            registry=registry,
            format_checker=validator_class.FORMAT_CHECKER,
        )
        errors = sorted(
            validator.iter_errors(instance),
            key=lambda error: [str(part) for part in error.absolute_path],
        )
        if path.name.startswith("invalid-"):
            if not errors:
                raise ValueError(
                    f"{path}: invalid fixture satisfies {schema_path}"
                )
            invalid_count += 1
            continue
        if errors:
            details = "; ".join(
                f"{list(error.absolute_path)}: {error.message}"
                for error in errors[:5]
            )
            raise ValueError(
                f"{path}: does not satisfy {schema_path}: {details}"
            )
        valid_count += 1
    print(
        f"validated {len(schemas_by_path)} schemas, "
        f"{valid_count} valid examples, and "
        f"{invalid_count} intentionally invalid examples"
    )


if __name__ == "__main__":
    main()

