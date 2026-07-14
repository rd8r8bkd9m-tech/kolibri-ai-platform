"""CLI for signed, explicitly unapproved FormulaLM local candidates."""

from __future__ import annotations

import argparse
import json
import sys

from .pipeline import (
    CorpusBuildError,
    build_local_candidate,
    verify_local_candidate,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m packages.formulalm_estimate_corpus",
        description=(
            "Prepare an integrity-signed local FormulaLM estimate candidate. "
            "This does not authorize model training."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser(
        "build-local-candidate",
        help="build a signed, training-ineligible local candidate",
    )
    build.add_argument("--input", required=True, help="local source JSONL snapshot")
    build.add_argument("--output", required=True, help="new empty output directory")
    build.add_argument(
        "--candidate-signing-key",
        required=True,
        help="OpenSSH private key matching the fixed candidate-builder trust root",
    )
    build.add_argument("--eval-ratio", type=float, default=0.2)
    build.add_argument("--max-records", type=int, default=10_000)

    verify = subparsers.add_parser(
        "verify-local-candidate",
        help="verify signature, manifest and candidate artifacts",
    )
    verify.add_argument("--manifest", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "build-local-candidate":
            result = build_local_candidate(
                args.input,
                args.output,
                signing_key=args.candidate_signing_key,
                eval_ratio=args.eval_ratio,
                max_records=args.max_records,
            )
            payload = {"status": "pass", **result.as_dict()}
        else:
            payload = verify_local_candidate(args.manifest)
    except CorpusBuildError as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if payload.get("status") == "pass" else 2


if __name__ == "__main__":
    sys.exit(main())
