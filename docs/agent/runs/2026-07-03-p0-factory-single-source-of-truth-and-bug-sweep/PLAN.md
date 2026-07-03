# P0 Factory Source Of Truth Plan

Date: 2026-07-03
Branch: `p0/factory-single-source-of-truth-and-bug-sweep-2026-07-03`

## Goal

Create one technical truth path for Kolibri Factory state:

1. `ops/factory_registry.py` is the static source of truth for canonical nodes, aliases, capabilities, runners, services and ports.
2. Control Plane `/v1/fleet/*` is the runtime source for current node health, freshness, routing, drift and queue diagnostics.
3. Agents answer technical questions from registry plus Fabric API evidence, never from guessed names or guessed ports.

## Execution Plan

1. Add canonical registry helpers with validation and alias/capability matching.
2. Wire Control Plane fleet summary, registry, drift and queue diagnostics endpoints.
3. Preserve current Fabric API surface and add bounded task listing when requested.
4. Add regression tests for aliases, capability aliases, runner safety and diagnostics.
5. Document runtime gaps that still require repair tasks instead of unsafe local fixes.

## Non Goals

- No queue deletion.
- No fake node, runner or capability status.
- No production deploy from this sweep.
- No force push or push to `main`.

