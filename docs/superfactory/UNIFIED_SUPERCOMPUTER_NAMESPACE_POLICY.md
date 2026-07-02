# Unified Supercomputer Namespace Policy

Snapshot: 2026-07-02

## Law

Kolibri AI is operated as one federated supercomputer, not as a pile of
individual servers. Agents should see one logical namespace and one Control
Plane, while physical data stays on the owning node unless a task explicitly
leases or replicates it.

The logical filesystem root is:

```text
/kolibri/nodes
```

The Control Plane exposes it through:

```text
GET /v1/filesystem
GET /v1/fleet/filesystem
```

This is a mesh API namespace, not a single unsafe shared writable disk.

## Access Model

| Layer | Default |
| --- | --- |
| Discovery | allowed factory-wide for trusted agents |
| Search | allowed through Control Plane/Fabric API and node manifests |
| Read | allowed for non-secret project roots, docs, task artifacts and logs |
| Write | task worktree, artifact dir, explicit write_scope or leased node root |
| Secrets | referenced by secret id/capability, raw values are not shared |
| Destructive actions | owner approval unless a pre-approved rollback/canary exists |

## Why This Is Not A Kostyl

The owner should not SSH into servers one by one to make agents understand the
project. Agents query the fabric:

1. `GET /v1/fleet/nodes`
2. `GET /v1/fleet/capabilities`
3. `GET /v1/filesystem`
4. `GET /v1/agents/status/{task_id}`
5. artifact APIs for task outputs

SSH remains a lower-level bootstrap and repair channel only.

## Node Manifest Contract

Every Agent Host heartbeat must publish filesystem metadata:

```json
{
  "filesystem": {
    "mode": "mesh_api_namespace",
    "namespace_prefix": "/kolibri/nodes/server-kfrm",
    "write_policy": "node-local writes only; shared roots require leases",
    "roots": [
      {
        "name": "worktrees",
        "namespace": "/kolibri/nodes/server-kfrm/worktrees",
        "purpose": "task worktrees",
        "exists": true,
        "writable": true
      },
      {
        "name": "artifacts",
        "namespace": "/kolibri/nodes/server-kfrm/artifacts",
        "purpose": "task artifacts and logs",
        "exists": true,
        "writable": true
      }
    ]
  }
}
```

Raw local paths are hidden by default. They may be included only for
authenticated diagnostics using `include_paths=true`.

## Unified Search Behavior

When KFM/MIMO needs information, it should:

1. Search local task context and repository clone.
2. Query `/v1/filesystem` for the namespace map.
3. Query task/artifact APIs for known work results.
4. Route read-only search to the node that owns the namespace root.
5. Ask for a scoped grant only if the needed context is missing or secret.
6. Create repair tasks for nodes missing filesystem manifests.

## Replication Rule

Replication is allowed for project context, docs, task artifacts, memory
packets and indexes. Raw secrets and private keys are not replicated.

Replicated data must include:

- source namespace;
- target namespace;
- checksum or version;
- task_id and trace_id;
- classification;
- expiry or retention policy;
- repair path if sync fails.

## KFM Priority

KFM must receive this policy first because it is the active remote Agent Host
worker for the director task stream. After KFM is configured, it may fan out the
same non-secret policy packet to other fresh Agent Hosts through Control Plane.
