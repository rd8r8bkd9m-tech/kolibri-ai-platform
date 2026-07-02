# NEXT

1. Convert PR #119 out of draft only after the owner is ready for review.
2. Ensure CI/status contexts run for commit `1aab1a2833965a5e9c70dbe685c9d3e85849f070` and are green.
3. Add or obtain review approval for PR #119.
4. Resolve current primary-candidate Control Plane health issue: HTTP probes time out and lease endpoint logs recent 500s.
5. Relay/push this local docs commit from a write-capable machine, because this server key is read-only.
6. Re-run this release gate.
7. If the gate is `merge_ready` or `merge_ready_after_minor_docs_fix`, perform the reversible primary-candidate-only validation deploy.
8. Run exactly the 3-task heartbeat canary.
9. Keep requeue decision at `no_requeue_needs_more_canary` until canary proof exists.
