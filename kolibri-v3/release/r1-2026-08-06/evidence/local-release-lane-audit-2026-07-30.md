# Local canonical release-lane audit — 2026-07-30

Scope: source, tests and local immutable-package preview only. Production,
Home, Primary, Nginx and DNS were not changed.

## Decision

`kolibri-v3/deploy/portable` is the only V3 R1 production release lane. The
builder now audits the complete Git commit before reading the V3 subtree.
This prevents an otherwise clean V3 subtree from being packaged while the
same commit also contains a parent-level Home, Primary or bare-metal V3
deployment implementation.

The audit rejects:

- `ops/release/kolibri_v3_*` and `ops/release/kolibri-v3-*` helpers;
- `ops/release/kolibri-v3-baremetal/**`;
- the retired `ops/release/product-agent/**` packaging lane;
- any changed implementation at
  `ops/release_kolibri_v3_product.sh`.

The retired coordinator is allowed only as the byte-exact read-only tombstone
with SHA-256:

```text
97d8fde02789f1ec048d855cc2f252dd6676d3f8c24cb93018c1f060a14062bf
```

Its `status` mode reports `legacy_lane=disabled`. Its former mutating
`build-only` mode exits with code `3` and
`release_error=legacy_split_v3_release_lane_disabled`. The shell syntax and
its bounded state-machine self-test pass.

## Contract evidence

`release-manifest.py audit-repository` reports:

```text
repository_release_lane=ok
release_lane=canonical-portable-only
```

The portable archive and adjacent manifest now bind
`release_lane=canonical-portable-only`, and archive verification requires the
same value.

Synthetic committed fixtures prove that:

- a parent-level Home apply helper aborts the build before an archive exists;
- a changed legacy coordinator aborts the build before an archive exists;
- a legacy backend or alternate in-tree installer remains rejected;
- a standalone repository whose root is `kolibri-v3` remains supported.

Local gates after the change:

```text
portable release contracts: 14/14
complete web/contracts suite: 118/118
TypeScript typecheck: passed
GitHub Actions YAML parse: passed
```

The V3 workflow runs the repository audit explicitly and the archive builder
runs it again. A real immutable RC still requires a clean authorized commit
and remote green CI. Workspace-only legacy helper files are not part of the
candidate commit and must not be executed; if committed, the new guard rejects
the build.

