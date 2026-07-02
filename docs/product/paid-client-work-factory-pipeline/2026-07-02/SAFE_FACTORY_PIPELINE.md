# Safe Paid-Client Factory Pipeline

Status: production contract for paid-client work intake and internal factory
routing.

This pipeline lets Kolibri Factory prepare paid-client work safely:

1. Intake records the client alias, request summary, repository, deliverables,
   base ref and non-secret quote basis.
2. Quote generation produces a draft only. It is not sent to the client and it
   cannot request payment.
3. Branch and task creation are internal factory actions gated by explicit owner
   approval through `owner_approved_for_internal_tasks=true`.
4. Implementation runs as `owner_remote_task` on a scoped branch, with review
   task creation enabled.
5. Deliverable packaging creates artifacts, verification notes and an
   owner-reviewed client reply draft.
6. Public client messages, final delivery, invoices, payment requests and
   charges remain blocked until owner approval outside the automated pipeline.

## Control Plane

Endpoint:

```text
POST /v1/client-work/pipeline
```

Required fields:

```json
{
  "client_alias": "Acme Client",
  "request_summary": "Implement scoped paid-client work",
  "repo_slug": "kolibri-ai-platform"
}
```

Without `owner_approved_for_internal_tasks=true`, the endpoint returns the full
pipeline as a canonical blocked response so the owner can review the quote,
branch and task envelopes.

With `owner_approved_for_internal_tasks=true`, the endpoint enqueues internal
tasks only. It still sets `public_action_allowed=false` and
`money_action_allowed=false` on every task.

## Dispatcher

Generate a local safe plan:

```bash
ops/kolibri-dispatch client-work-plan --file intake.json
```

Create the pipeline through the Control Plane after owner approval for internal
work:

```bash
ops/kolibri-dispatch client-work-create --file intake.json --approve-internal-tasks
```

## Safety Rules

- Agents may draft client-facing text, but must not send it.
- Agents may draft quotes, but must not invoice, charge, request payment or make
  financial commitments.
- Agents must not promise dates, refunds, legal terms or tax positions without
  owner confirmation.
- Agents must redact secrets, credentials and private infrastructure details.
- Scope changes, disputes, refunds and unclear commercial commitments escalate
  to the owner.
- No push to `main`, no force push, and no auto-merge.

## Artifact Contract

Each paid-client run should retain:

- intake JSON;
- quote draft;
- branch and task envelope list;
- implementation artifacts and test output;
- review result;
- deliverable package;
- owner-approved client reply text, if approved.
