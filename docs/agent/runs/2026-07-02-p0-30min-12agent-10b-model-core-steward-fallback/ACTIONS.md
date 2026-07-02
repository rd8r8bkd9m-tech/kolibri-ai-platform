# Actions

- Added `kolibri-10b-core` to the Factory Control model catalog as a safe Fabric model candidate.
- Added `model_registry()` to derive model node status, fallback nodes, route status, and repair tasks from registered fleet nodes.
- Updated `/v1/models` to return the richer registry envelope while keeping generation endpoints as safe stubs.
- Added focused tests for online and blocked model-node registry behavior.

