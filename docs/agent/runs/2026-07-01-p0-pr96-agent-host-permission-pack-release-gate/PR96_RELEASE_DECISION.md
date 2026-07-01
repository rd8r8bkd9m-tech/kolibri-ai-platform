# PR96 Release Decision

Decision: `merge_ready_after_owner_review`

Basis:

- Scope is narrow: `ops/agent_host.py` and `tests/test_agent_host_permission_contract.py`.
- Server focused tests passed.
- GitHub branch was updated after PR #95.
- Updated head `42625cadb2c0d164e2d82598a8a887d5a9a3d1e1` has GitHub CI success.
- PR #96 is currently mergeable and clean.

Important caveat:

The Control Plane task itself remains `failed_useful...` because it did not create exact canonical artifacts and the server could not read private GitHub CI. This file records the command-node relay and updated GitHub evidence; it is not a claim that the original Control Plane task completed successfully.

Required post-merge gate:

Run the Agent Host permission-contract canary after merge, deploy, and service restart. The canary must prove that read-only/no-push tasks cannot receive or execute write-capable permission packs.
