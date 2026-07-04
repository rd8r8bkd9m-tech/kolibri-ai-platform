# SECURITY_AND_APPROVAL_GATES

## Allowed without new approval

- Read fleet status.
- Read queue status.
- Read PR list when a safe backend/connector is bound.
- Submit read-only diagnostic/docs/review task.
- Collect artifacts.
- Update PR description.
- Create draft PR.

## Approval required

- Merge to `main`.
- Production deploy.
- Redis cleanup.
- Queue rebuild.
- `authorized_keys` changes.
- Secret rotation.
- Billing/provider/server lifecycle.
- Telegram live proof.
- Broad MIMO/FormulaLM rollout.
- Delete branches.
- Retire server.

## Gateway enforcement

The HTTP gateway does not run shell commands, SSH, root commands, git merge, git reset, service restarts, firewall changes, Redis cleanup, or secret rotation. Dangerous action text is returned as an approval request.
