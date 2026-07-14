"""Leakage-safe deterministic project/source-group splitting."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence


class _DisjointSet:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, index: int) -> int:
        while self.parent[index] != index:
            self.parent[index] = self.parent[self.parent[index]]
            index = self.parent[index]
        return index

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def split_records(
    records: Sequence[Mapping[str, object]], eval_ratio: float
) -> tuple[list[Mapping[str, object]], list[Mapping[str, object]], dict[str, object]]:
    if not 0 < eval_ratio < 1:
        raise ValueError("eval_ratio must be between 0 and 1")
    if not records:
        return [], [], {"component_count": 0, "project_overlap": [], "source_group_overlap": []}

    dsu = _DisjointSet(len(records))
    project_owner: dict[object, int] = {}
    source_group_owner: dict[object, int] = {}
    for index, record in enumerate(records):
        project_id = record["project_id"]
        source_group_id = record["source_group_id"]
        if project_id in project_owner:
            dsu.union(index, project_owner[project_id])
        else:
            project_owner[project_id] = index
        if source_group_id in source_group_owner:
            dsu.union(index, source_group_owner[source_group_id])
        else:
            source_group_owner[source_group_id] = index

    components: dict[int, list[int]] = defaultdict(list)
    for index in range(len(records)):
        components[dsu.find(index)].append(index)

    ranked: list[tuple[str, list[int]]] = []
    for indexes in components.values():
        identity = "\n".join(
            sorted(
                {
                    *(f"project:{records[index]['project_id']}" for index in indexes),
                    *(
                        f"source-group:{records[index]['source_group_id']}"
                        for index in indexes
                    ),
                }
            )
        )
        ranked.append((hashlib.sha256(identity.encode("utf-8")).hexdigest(), indexes))
    ranked.sort(key=lambda item: item[0])

    eval_roots: set[int] = set()
    threshold = int(eval_ratio * 10_000)
    for rank, (digest, _) in enumerate(ranked):
        if int(digest[:8], 16) % 10_000 < threshold:
            eval_roots.add(rank)
    if len(ranked) >= 2 and not eval_roots:
        eval_roots.add(0)
    if len(ranked) >= 2 and len(eval_roots) == len(ranked):
        eval_roots.remove(len(ranked) - 1)

    train: list[Mapping[str, object]] = []
    evaluation: list[Mapping[str, object]] = []
    for rank, (_, indexes) in enumerate(ranked):
        destination = evaluation if rank in eval_roots else train
        destination.extend(records[index] for index in indexes)
    train.sort(key=lambda item: str(item["record_id"]))
    evaluation.sort(key=lambda item: str(item["record_id"]))

    train_projects = {record["project_id"] for record in train}
    eval_projects = {record["project_id"] for record in evaluation}
    train_groups = {record["source_group_id"] for record in train}
    eval_groups = {record["source_group_id"] for record in evaluation}
    report = {
        "component_count": len(ranked),
        "project_overlap": sorted(train_projects & eval_projects),
        "source_group_overlap": sorted(train_groups & eval_groups),
    }
    return train, evaluation, report
