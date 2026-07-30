# Kolibri Product Chat v1

This family is the canonical user-facing project, thread, message and durable
run contract. It is derived from Kolibri product invariants; it is not a
renaming of legacy `Project`, OpenAI `Response`, AI SDK messages or A2A
delivery records.

Authority:

- Product/Data Authority owns every record in this family and assigns
  tenant/user identity from the authenticated session.
- Logical Home owns Goal, ProjectCase workflow, tasks, policy, approvals and
  release. Product records may reference those records but never replace them.
- Browser, assistant-ui and AG-UI are consumers/projections. They cannot grant
  authority, advance a durable lifecycle or manufacture a committed event.
- A temporary `LegacyProductChatAdapter` may read legacy records inside the
  Product/Data boundary. Legacy DTOs are never exposed as this wire contract,
  and authoritative dual-write is forbidden.

Core invariants:

1. `project_id` and `thread_id` are distinct identities.
2. A committed message is immutable. Editing creates a new branch lineage.
3. Normal send is atomic: the Product owner commits the user message, run and
   Logical Home outbox command in one transaction.
4. A run is a user-facing durable execution, not a provider response or Home
   task. Retry and HITL resume create new runs.
5. Run events form an immutable ledger ordered by `(run_id, sequence)` and
   survive disconnect, client close and process restart.
6. A delivery cursor is read-only replay position, scoped to authenticated
   tenant/user/thread/run. It is neither a credential nor an A2A cursor.
7. AG-UI projection is rebuildable and lossy. Raw reasoning, raw A2A,
   provider routing and provider response identifiers are forbidden.
8. Artifact references always bind exact
   `(tenant_id, artifact_id, artifact_version, content_hash)`.
9. JSON Schema validates structure. `validator.cjs` validates intrinsic
   lineage, lifecycle, sequence, time and safe-projection semantics. The
   Product owner additionally validates authenticated scope/current versions.
10. Errors use the shared `kolibri.error` envelope.
11. `kolibri.product.text_run_request` is the only browser mutation that may
    create a normal user message and run. Product/Data converts it to a
    `kolibri.product.run.execute.command` inside the shared `kolibri.command`
    envelope. The browser never creates that command and cannot select a
    physical node, runner, authority grant or fallback policy.
12. Run execution status is an internal Logical Home → Product/Data record,
    never a browser command. Legacy
    `kolibri.product.run.execution_status` v1.0 keeps its resolved
    `profile` compatibility field. Universal
    `kolibri.product.run.execution_status.v1_1` carries an opaque bounded
    `runtime_profile` and does not enumerate providers. Successful text is
    bound to an exact SHA-256 and declares `verification_status`. A producing
    agent's fenced completion is `unverified` with `evidence: null`; only a
    separate verifier bound to the same content hash may declare `verified`
    and attach a versioned evidence reference. Failure carries the shared
    canonical `kolibri.error` bound to the opaque execution ID.
13. `kolibri.product.attachment` is the only browser-facing upload record.
    Product/Data assigns its tenant, project, actor, immutable artifact version
    and content hash. During migration it may be backed by the legacy source
    document table only inside Product/Data; the legacy DTO never crosses the
    Product API boundary.
14. Before the first Product run is dispatched, Product/Data sends
    `kolibri.product.goal.initialize.command` to Logical Home with Product
    transport authority only. Logical Home reconstructs its own server-held
    `goal.create` grant, creates the canonical Goal, derives
    `case_{goal_id}`, materializes that ProjectCase and returns
    `kolibri.product.goal.initialization_status`. Product cannot provide a Case
    identifier or a Logical Home credential through this command. Exact replay
    returns the same `initialized` status; a changed effect for the same Goal is
    an idempotency conflict.
15. Provider enrollment is an owner-approved, secretless intent. Product/Data
    persists the exact `kolibri.product.provider.enrollment_intent.command`,
    then a standalone server process may authenticate it to Provider Execution
    Authority. MiMo tokens, Codex login state, raw provider responses,
    filesystem paths and authorization URLs never enter Product/Data or the
    browser. Only a validated
    `kolibri.product.provider.enrollment_status` may mark a connection
    `connected`; a missing endpoint or external login remains fail-closed.
16. `kolibri.product.run.execute.v1_1.command` is the compatible opt-in
    execution-selection extension. Any registered opaque runtime profile may carry
    a preferred model and reasoning effort; an explicit `null`/`null` pair
    means deployment-controlled defaults. Partial null selection is invalid.
    Logical Home resolves and freezes the
    exact pair in the durable task; profiles without a selectable catalog carry
    an explicit `null`/`null` pair and never receive a synthetic model ID.
    Provider Execution Authority
    independently checks both values against its deployment allowlists.
    Reasoning effort identifiers are model-advertised bounded strings, not a
    hard-coded product enum; deployment allowlists remain authoritative. The
    v1.0 payload remains accepted unchanged and continues to use the
    deployment-pinned model without manufacturing a user selection.
17. `kolibri.product.run.execute.v1_2.command` is the owner-only developer
    execution command. Product/Data freezes the opaque `runtime_profile`,
    model, reasoning effort, service tier, workspace reference, access mode,
    sandbox, approval policy and reviewer from authenticated server state.
    The payload always declares `execution_mode: developer` and
    `requester_role: owner`; the command authority must separately carry
    `product.developer.run.execute.request`. Provider names, credentials,
    transport URLs and fallback routing are not fields in this contract.
    Logical Home creates the Task, TaskAttempt, lease/fence,
    AgentAssignment and typed A2A interaction before selecting a registered
    AgentRuntime. Product delivery performs no automatic retry after an
    ambiguous developer-effect failure; exact idempotent status polling
    remains allowed.

HTTP `/api/product/v1` and record `schema_version: 1.0` are independent
version axes. Additive schema evolution requires a declared accepted-version
policy and old/current/malformed/unknown fixtures; breaking semantics require
a new major contract family.
