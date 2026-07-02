#!/usr/bin/env python3
"""Read-only release queue accelerator helpers.

The accelerator intentionally uses `git ls-remote` evidence because some
factory nodes do not have `gh` or authenticated GitHub metadata available.
Pull refs remain visible after PRs merge, so this helper does not infer open
state from ref presence alone.
"""

import argparse
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


PULL_REF_RE = re.compile(r"^([0-9a-f]{40})\s+refs/pull/(\d+)/head$")
HEAD_REF_RE = re.compile(r"^([0-9a-f]{40})\s+refs/heads/main$")


@dataclass(frozen=True)
class PullRef:
    pr: int
    sha: str


@dataclass(frozen=True)
class QueueSnapshot:
    main_sha: str | None
    pull_refs: tuple[PullRef, ...]


def parse_ls_remote(text: str) -> QueueSnapshot:
    main_sha: str | None = None
    pull_refs: list[PullRef] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if match := HEAD_REF_RE.match(line):
            main_sha = match.group(1)
            continue
        if match := PULL_REF_RE.match(line):
            pull_refs.append(PullRef(pr=int(match.group(2)), sha=match.group(1)))
    pull_refs.sort(key=lambda ref: ref.pr)
    return QueueSnapshot(main_sha=main_sha, pull_refs=tuple(pull_refs))


def fetch_ls_remote(remote: str) -> str:
    proc = subprocess.run(
        ["git", "ls-remote", remote, "refs/heads/main", "refs/pull/*/head"],
        check=True,
        text=True,
        capture_output=True,
    )
    return proc.stdout


def classify_ref(pr: int, known_merged: set[int], priority: set[int]) -> str:
    if pr in known_merged:
        return "merged_or_superseded_ref_visible"
    if pr in priority:
        return "priority_ref_visible_metadata_required"
    return "backlog_ref_visible_metadata_required"


def render_markdown(
    snapshot: QueueSnapshot,
    *,
    source: str,
    known_merged: set[int],
    priority: set[int],
) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for ref in snapshot.pull_refs:
        rows.append(
            "| #{pr} | `{sha}` | `{classification}` | {note} |".format(
                pr=ref.pr,
                sha=ref.sha[:12],
                classification=classify_ref(ref.pr, known_merged, priority),
                note=(
                    "Pull refs can remain visible after merge; require GitHub metadata before owner action."
                    if ref.pr not in known_merged
                    else "Previously recorded as merged in dispatcher evidence; ref visibility is not a blocker."
                ),
            )
        )
    table = "\n".join(rows)
    return f"""# PR Ref Accelerator Matrix

Generated: `{generated_at}`

Source: `{source}`

Main SHA: `{snapshot.main_sha or 'unknown'}`

Pull refs visible: `{len(snapshot.pull_refs)}`

Known merged/superseded refs: `{len([ref for ref in snapshot.pull_refs if ref.pr in known_merged])}`

Priority refs requiring metadata: `{len([ref for ref in snapshot.pull_refs if ref.pr in priority and ref.pr not in known_merged])}`

| PR | Pull ref SHA | Accelerator classification | Release queue note |
| --- | --- | --- | --- |
{table}
"""


def csv_ints(value: str) -> set[int]:
    if not value:
        return set()
    return {int(part.strip()) for part in value.split(",") if part.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--input", help="Read saved git ls-remote output instead of running git.")
    parser.add_argument("--output", help="Write markdown matrix to this path.")
    parser.add_argument("--known-merged", default="")
    parser.add_argument("--priority", default="")
    args = parser.parse_args()

    source = args.input or f"git ls-remote {args.remote} refs/heads/main refs/pull/*/head"
    text = Path(args.input).read_text(encoding="utf-8") if args.input else fetch_ls_remote(args.remote)
    markdown = render_markdown(
        parse_ls_remote(text),
        source=source,
        known_merged=csv_ints(args.known_merged),
        priority=csv_ints(args.priority),
    )
    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
