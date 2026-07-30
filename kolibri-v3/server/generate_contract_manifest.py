"""Regenerate the self-contained V3 contract integrity manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


V3_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = V3_ROOT / "contracts" / "v1"
MANIFEST_PATH = V3_ROOT / "contracts" / "generated" / "v1" / "manifest.json"


def _manifest() -> dict[str, Any]:
    schemas: list[dict[str, str]] = []
    contract_count = 0
    for path in sorted(CONTRACT_ROOT.rglob("*.schema.json")):
        raw = path.read_bytes()
        schema = json.loads(raw.decode("utf-8", "strict"))
        schema_uri = schema.get("$id")
        if not isinstance(schema_uri, str):
            raise RuntimeError(f"schema $id is missing: {path}")
        properties = schema.get("properties")
        if (
            isinstance(properties, dict)
            and isinstance(properties.get("schema_id"), dict)
            and isinstance(
                properties["schema_id"].get("const"),
                str,
            )
            and isinstance(properties.get("schema_version"), dict)
            and isinstance(
                properties["schema_version"].get("const"),
                str,
            )
        ):
            contract_count += 1
        schemas.append(
            {
                "schema_uri": schema_uri,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "source_path": (
                    "contracts/v1/"
                    + path.relative_to(CONTRACT_ROOT).as_posix()
                ),
            }
        )
    return {
        "contract_count": contract_count,
        "generator_version": "1.0",
        "outputs": [
            "generated/contracts-v1.ts",
            "server/contracts_runtime.py",
        ],
        "schema_count": len(schemas),
        "schema_id": "kolibri.generated_contract_package_manifest",
        "schema_version": "1.0",
        "schemas": schemas,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = (
        json.dumps(
            _manifest(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    if args.check:
        return (
            0
            if MANIFEST_PATH.is_file()
            and MANIFEST_PATH.read_text(encoding="utf-8") == rendered
            else 1
        )
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
