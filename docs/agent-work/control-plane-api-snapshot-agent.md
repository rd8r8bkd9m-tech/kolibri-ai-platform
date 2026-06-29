# Machine-readable snapshot API Control Plane и Agent Host

Документ фиксирует фактический контракт из `ops/factory_control.py` и `ops/agent_host.py` на 2026-06-29. Runtime-код не менялся. Основной блок ниже предназначен для машинного чтения: парсер может извлечь fenced-блок `yaml` с корневым ключом `api_snapshot`.

```yaml
api_snapshot:
  id: "kolibri_factory_control_plane_agent_host"
  snapshot_version: 1
  language: "ru"
  source_date: "2026-06-29"
  source_files:
    - path: "ops/factory_control.py"
      role: "control_plane_http_api"
    - path: "ops/agent_host.py"
      role: "agent_host_client_runtime"

  implementation:
    control_plane:
      server: "http.server.ThreadingHTTPServer"
      handler: "Handler"
      server_version: "KolibriFactoryControl/0.1"
      transport: "HTTP JSON"
      response_content_type: "application/json"
      request_body_parser: "json.loads(raw_body) when Content-Length > 0; otherwise {}"
      auth: "not implemented in source files"
      persistence: "Redis via minimal RESP client"
      redis_namespace_env: "FACTORY_NAMESPACE"
      redis_namespace_default: "kolibri_factory"
      default_bind_env: "FACTORY_BIND"
      default_bind: "127.0.0.1"
      default_port_env: "FACTORY_PORT"
      default_port: 9101
      error_wrapper: "unexpected exceptions return HTTP 500 {error: control_plane_error, detail}"
      validation_note: "schema validation is minimal; missing required keys can surface as control_plane_error"
    agent_host:
      client: "urllib.request"
      failover: "tries --control-urls/KOLIBRI_FACTORY_CONTROL_URLS in order and remembers the last successful URL"
      default_control_url: "http://10.99.0.2:9101"
      default_capabilities: "read_only_probe,generic_implementation,implementation,remote_implementation_runner_ready,review,image_generation,mesh_node"
      default_permission_packs: ["full_autonomy"]
      default_work_root: "/var/lib/kolibri-agent/worktrees"
      default_artifact_root: "/var/lib/kolibri-agent/artifacts"
      default_heartbeat_interval_seconds: 10
      default_lease_refresh_seconds: 20
      default_max_inflight: 1

  constants:
    lease_duration_seconds:
      env: "FACTORY_LEASE_DURATION"
      default: 60
    task_heartbeat_stale_after_seconds:
      env: "FACTORY_TASK_HEARTBEAT_STALE_AFTER"
      default_expression: "FACTORY_LEASE_DURATION * 2"
    max_retries:
      env: "FACTORY_MAX_RETRIES"
      default: 3
    node_stale_after_seconds:
      env: "FACTORY_NODE_STALE_AFTER"
      default: 120
    default_task_list_limit:
      env: "FACTORY_DEFAULT_TASK_LIST_LIMIT"
      default: 200
    max_task_list_limit:
      env: "FACTORY_MAX_TASK_LIST_LIMIT"
      default: 500
    max_task_summary_scan:
      env: "FACTORY_MAX_TASK_SUMMARY_SCAN"
      default: 2000
    lease_expiring_soon_seconds:
      env: "FACTORY_LEASE_EXPIRING_SOON_SECONDS"
      default: 30

  task_states:
    queued:
      terminal: false
      active: false
      leased_index: false
      meaning: "создана задача и поставлена в Redis queue"
    leased:
      terminal: false
      active: true
      leased_index: true
      meaning: "Control Plane выдал lease Agent Host"
    running:
      terminal: false
      active: true
      leased_index: true
      meaning: "Agent Host прислал task heartbeat во время исполнения"
    waiting_review:
      terminal: false
      active: true
      leased_index: false
      meaning: "implementation завершился, но create_review_on_complete=true и PR URL еще не приложен"
    review:
      terminal: false
      active: true
      leased_index: true
      meaning: "review task создан/ожидает или исполняется как review"
    completed:
      terminal: true
      active: false
      leased_index: false
      meaning: "успешное завершение"
    failed:
      terminal: true
      active: false
      leased_index: false
      meaning: "финальная ошибка без дальнейшего retry"
    cancelled:
      terminal: true
      active: false
      leased_index: false
      meaning: "задача отменена через cancel endpoint"
    retry_scheduled:
      terminal: false
      active: false
      leased_index: false
      meaning: "промежуточное состояние перед возвратом в queued"
    dead_letter:
      terminal: true
      active: false
      leased_index: false
      meaning: "lease/stuck retry budget исчерпан"

  permission_packs:
    read_only: ["read_repo", "read_system", "write_artifacts"]
    ai_chat: ["ai_runner", "write_artifacts"]
    media_generation: ["ai_runner", "network", "write_artifacts"]
    implementation: ["read_repo", "write_worktree", "run_tests", "network", "git_push", "write_artifacts"]
    review: ["read_repo", "run_tests", "network", "github_review", "write_artifacts"]
    full_autonomy:
      - "ai_runner"
      - "git_push"
      - "github_review"
      - "network"
      - "read_repo"
      - "run_tests"
      - "shell"
      - "spawn_subagents"
      - "write_artifacts"
      - "write_worktree"

  compatibility:
    control_plane_required_capability_aliases:
      remote_implementation_runner_ready: ["implementation", "generic_implementation"]
    control_plane_runner_kind_aliases:
      remote_implementation_runner_ready: "generic_implementation"
    agent_host_runner_kind_aliases:
      remote_implementation_runner_ready: "generic_implementation"
      product_implementation: "generic_implementation"
    autonomous_task_kinds: ["owner_remote_task", "generic_implementation"]
    deliverable_required_kinds:
      - "owner_remote_task"
      - "generic_implementation"
      - "remote_implementation_runner_ready"

  schemas:
    task_envelope_input:
      type: "object"
      required_by_api: []
      generated_defaults:
        task_id: "KOL-TASK-<12 hex chars> when omitted"
        idempotency_key: "task_id when omitted"
        kind: "read_only_probe when omitted"
        max_retries: "FACTORY_MAX_RETRIES when omitted"
      commonly_required_by_runners:
        generic_implementation:
          any_of_text_fields: ["goal", "objective", "task", "message", "prompt"]
        telegram_chat_response:
          required: ["message"]
        telegram_image_generation:
          any_of_text_fields: ["prompt", "message", "objective"]
        review_pr:
          required: ["branch"]
      fields:
        task_id: {type: "string", required: false}
        idempotency_key: {type: "string", required: false}
        kind: {type: "string", required: false}
        max_retries: {type: "integer", required: false}
        permission_pack: {type: "string", required: false}
        autonomy_pack: {type: "string", required: false, alias_for: "permission_pack"}
        required_permissions: {type: "array|string", required: false}
        target_node: {type: "string", required: false}
        required_node: {type: "string", required: false, alias_for: "target_node"}
        allowed_nodes: {type: "array", required: false}
        required_capability: {type: "string", required: false}
        create_review_on_complete: {type: "boolean", required: false}
        review_task_id: {type: "string", required: false}
        review_node: {type: "string", required: false, default: "new"}
        review_max_retries: {type: "integer", required: false}
        branch: {type: "string", required: false}
        base_ref: {type: "string", required: false, default: "origin/main"}
        runner: {type: "string", required: false, enum_hint: ["mimo", "codex"]}
        push: {type: "boolean", required: false, default: true}
        verification_commands: {type: "array|string", required: false}
        acceptance: {type: "array|string", required: false}
        acceptance_criteria: {type: "array|string", required: false, alias_for: "acceptance"}
        source: {type: "object|string", required: false}

    normalized_task:
      type: "object"
      fields:
        task_id: {type: "string"}
        idempotency_key: {type: "string"}
        kind: {type: "string"}
        permission_pack: {type: "string|null"}
        required_permissions: {type: "array[string]"}
        state: {type: "string", enum_ref: "task_states"}
        attempt: {type: "integer"}
        max_retries: {type: "integer"}
        attempt_id: {type: "string|null"}
        lease_owner: {type: "string|null", format: "<node_id>:<agent_id>"}
        lease_until: {type: "number|null", units: "epoch seconds"}
        heartbeat_at: {type: "string|null", format: "datetime iso8601"}
        result_reference: {type: "string|null"}
        result: {type: "object|null"}
        error_type: {type: "string|null"}
        error: {type: "string|null"}
        created_at: {type: "string", format: "datetime iso8601"}
        updated_at: {type: "string", format: "datetime iso8601"}
        envelope: {type: "object", schema_ref: "task_envelope_input"}
        attempt_history: {type: "array", required: false}
        granted_permissions: {type: "array[string]", required: false}
        pid: {type: "integer|null", required: false}
        worktree: {type: "string|null", required: false}
        branch: {type: "string|null", required: false}
        log_paths: {type: "object|null", required: false}

    node_register_request:
      type: "object"
      required: ["node_id"]
      fields:
        node_id: {type: "string"}
        hostname: {type: "string|null"}
        agent_id: {type: "string|null"}
        pid: {type: "integer|null"}
        capabilities: {type: "array|string", default: []}
        permissions: {type: "array|string", default: []}
        permission_packs: {type: "array|string", default: []}
        cpu: {type: "integer|null"}
        ram: {type: "object"}
        disk: {type: "object"}

    node_heartbeat_request:
      type: "object"
      required: []
      fields:
        node_id: {type: "string", required: false, note: "Agent Host sends it, but Control Plane uses {node_id} from path"}
        hostname: {type: "string|null"}
        agent_id: {type: "string|null"}
        pid: {type: "integer|null"}
        capabilities: {type: "array|string", default: []}
        permissions: {type: "array|string", default: []}
        permission_packs: {type: "array|string", default: []}
        active_task: {type: "string|null"}
        cpu: {type: "integer|null"}
        ram: {type: "object"}
        disk: {type: "object"}

    node_card:
      type: "object"
      fields:
        node_id: {type: "string"}
        hostname: {type: "string|null"}
        capabilities: {type: "array|string"}
        permissions: {type: "array[string]"}
        permission_packs: {type: "array[string]"}
        health: {type: "string", enum_hint: ["online", "stale"]}
        heartbeat_at: {type: "string", format: "datetime iso8601"}
        heartbeat_age_seconds: {type: "number|null", read_only: true}
        fresh: {type: "boolean", read_only: true}
        draining: {type: "boolean", read_only: true}
        active_task: {type: "string|null", required: false}
        active_task_state: {type: "string|null", read_only: true, required: false}
        active_task_terminal: {type: "boolean", read_only: true, required: false}
        pid: {type: "integer|null"}
        cpu: {type: "integer|null"}
        ram: {type: "object"}
        disk: {type: "object"}
        agent_id: {type: "string|null"}

    lease_request:
      type: "object"
      required: ["node_id"]
      fields:
        node_id: {type: "string"}
        agent_id: {type: "string|null", default: "node_id"}
        capabilities: {type: "array|string"}
        permissions: {type: "array|string"}
        permission_packs: {type: "array|string"}

    task_heartbeat_request:
      type: "object"
      fields:
        state: {type: "string", default: "running"}
        pid: {type: "integer|null"}
        worktree: {type: "string|null"}
        branch: {type: "string|null"}
        log_paths:
          type: "object"
          fields:
            stdout: {type: "string"}
            stderr: {type: "string"}

    task_complete_request:
      type: "object"
      fields:
        result_reference: {type: "string|null", default: "result.result_path"}
        result: {type: "object"}
      deliverable_gate_for_autonomous_tasks:
        skipped_when_idempotency_key_prefix: "telegram-chat:"
        required:
          - "result_reference exists"
          - "result.changed_files non-empty OR result.commit OR result.pull_request_url OR result.pr_url"
          - "result.checks non-empty"
        failure_http_status: 422
        failure_error: "deliverable_gate_failed"
        failure_detail_codes: ["missing_result_reference", "missing_code_delta", "missing_checks"]

    task_fail_request:
      type: "object"
      fields:
        error_type: {type: "string", default: "runtime_error"}
        error: {type: "string|null"}
        result: {type: "object|null"}
        result_reference: {type: "string|null"}
        retry: {type: "boolean", default: true}

    task_annotate_request:
      type: "object"
      fields:
        result: {type: "object", merge_into_existing_result: true}
        result_reference: {type: "string|null", default: "result.result_path or existing result_reference"}

    agent_message:
      type: "object"
      generated_defaults:
        message_id: "MSG-<16 hex chars>"
        sender: "unknown"
        recipients: ["all"]
        kind: "status"
        body: ""
        artifacts: []
        created_at: "server time"
      fields:
        message_id: {type: "string"}
        sender: {type: "string", input_alias: "from"}
        recipients: {type: "array[string]", input_alias: "to"}
        kind: {type: "string"}
        topic: {type: "string|null"}
        task_id: {type: "string|null"}
        body: {type: "string", input_alias: "message"}
        artifacts: {type: "array[object]"}
        created_at: {type: "string", format: "datetime iso8601"}

    agent_host_result_common:
      type: "object"
      fields:
        node_id: {type: "string"}
        hostname: {type: "string"}
        task_id: {type: "string"}
        agent_id: {type: "string"}
        attempt_id: {type: "string|null"}
        pid: {type: "integer"}
        heartbeat_at: {type: "string|null", format: "datetime iso8601"}
        worktree: {type: "string|null"}
        branch: {type: "string|null"}
        log_paths: {type: "object", fields: {stdout: {type: "string"}, stderr: {type: "string"}}}
        result_path: {type: "string"}
        status: {type: "string"}
        kind: {type: "string|null"}

    agent_host_success_result_variants:
      read_only_probe:
        extends: "agent_host_result_common"
        status: "completed"
        extra_fields: ["message"]
      orchestrator_chat_response:
        extends: "agent_host_result_common"
        status: "completed"
        extra_fields: ["response"]
      telegram_image_generation:
        extends: "agent_host_result_common"
        status: "completed"
        extra_fields: ["prompt", "caption", "response", "image_path", "image_mime_type"]
        optional_fields: ["image_b64"]
      generic_implementation:
        extends: "agent_host_result_common"
        status: "completed"
        extra_fields:
          - "base_ref"
          - "commit"
          - "pushed"
          - "needs_central_pr"
          - "runner"
          - "response"
          - "changed_files"
          - "checks"
          - "permission_packs"
          - "permissions"
      implementation_smoke_tasks:
        extends: "agent_host_result_common"
        status: "completed"
        extra_fields: ["commit", "pull_request_url", "needs_central_pr", "changed_files", "checks"]
      review_pr:
        extends: "agent_host_result_common"
        status_enum: ["APPROVED", "CHANGES_REQUESTED"]
        extra_fields: ["pull_request_url", "github_review", "changed_files", "findings"]

    agent_host_failure_result:
      type: "object"
      fields:
        node_id: {type: "string"}
        hostname: {type: "string"}
        task_id: {type: "string"}
        agent_id: {type: "string"}
        attempt_id: {type: "string"}
        pid: {type: "integer"}
        status: {type: "string", const: "failed"}
        error_type: {type: "string"}
        error: {type: "string"}
        log_paths: {type: "object"}
        stdout_tail: {type: "string"}
        stderr_tail: {type: "string"}
        completed_at: {type: "string", format: "datetime iso8601"}

    artifact_manifest:
      type: "array"
      file_name: "artifact-manifest.json"
      item:
        path: {type: "string"}
        sha256: {type: "string"}
        bytes: {type: "integer"}

  endpoints:
    - id: "health"
      method: "GET"
      path: "/health"
      aliases: ["/v1/health"]
      request: {query: {}, body: null}
      responses:
        "200":
          schema:
            status: "ok"
            redis: "PING response"
            queue_backend: "redis"
            time: "datetime iso8601"
        "500": {error: "control_plane_error"}

    - id: "list_nodes"
      method: "GET"
      path: "/v1/nodes"
      request: {query: {}, body: null}
      response_200:
        nodes: "array[node_card]"
        summary:
          registered_nodes: "integer"
          canonical_nodes: "integer"
          fresh_nodes: "integer"
          fresh_non_draining_nodes: "integer"
          fresh_canonical_nodes: "integer"
          fresh_canonical_generic_implementation_nodes: "integer"
          mesh_shadow_duplicates: "integer"
          mesh_shadow_duplicate_nodes: "array[{node_id, shadows}]"
          duplicate_hostname_groups: "integer"
          duplicate_hostnames: "object[hostname -> array[node_id]]"
      notes:
        - "fresh=false when heartbeat_age_seconds is absent or greater than FACTORY_NODE_STALE_AFTER"
        - "health is forced to stale in decorated response when node is not fresh"

    - id: "register_node"
      method: "POST"
      path: "/v1/nodes/register"
      request_body_schema_ref: "node_register_request"
      response_200_schema_ref: "node_card"
      side_effects:
        - "stores node:<node_id>"
        - "adds node_id to node_ids set"
        - "sets health=online and heartbeat_at=server time"

    - id: "node_heartbeat"
      method: "POST"
      path: "/v1/nodes/{node_id}/heartbeat"
      request_body_schema_ref: "node_heartbeat_request"
      response_200_schema_ref: "node_card"
      side_effects:
        - "merges request body into existing node card"
        - "normalizes permissions and permission_packs with parse_list"
        - "sets health=online and heartbeat_at=server time"

    - id: "set_node_drain"
      method: "POST"
      path: "/v1/nodes/{node_id}/drain"
      request_body:
        drain: {type: "boolean", default: true}
      response_200:
        node_id: "string"
        draining: "boolean"
      side_effects:
        - "when draining=true sets drain:<node_id>"
        - "when draining=false deletes drain:<node_id>"
        - "drained node receives HTTP 204 from lease endpoint"

    - id: "create_task"
      method: "POST"
      path: "/v1/tasks"
      request_body_schema_ref: "task_envelope_input"
      response_201_schema_ref: "normalized_task"
      idempotency:
        key: "idempotency_key"
        behavior: "returns existing task when key already points to a loadable task"
      side_effects:
        - "stores task"
        - "adds task_id to task_ids set"
        - "sets idempotency:<idempotency_key>"
        - "pushes task_id to queue"

    - id: "list_tasks"
      method: "GET"
      path: "/v1/tasks"
      query:
        state: {type: "string|null", enum_ref: "task_states"}
        summary: {type: "boolean-string", accepted_true: ["1", "true", "yes"], default: false}
        compact: {type: "boolean-string", accepted_true: ["1", "true", "yes"], default: false}
        limit: {type: "integer", default: 200, max: 500}
        offset: {type: "integer", default: 0, min: 0}
      response_modes:
        summary_and_compact:
          when: "summary=true and compact=true"
          schema:
            summary: "task summary over compact task listing"
            queue_length: "integer"
            queue: "array[task_id]"
            tasks: "array[compact_task]"
        summary_only:
          when: "summary=true and compact=false"
          schema:
            summary: "summarize_tasks(tasks)"
            queue_length: "integer"
            limits: "pagination/scan metadata"
        default:
          schema:
            tasks: "array[normalized_task|compact_task]"
            queue: "array[task_id]"
            queue_length: "integer"
            queue_truncated: "boolean"
            limits: "pagination/scan metadata"
      compact_task_fields:
        - "task_id"
        - "kind"
        - "runner_kind"
        - "state"
        - "target_node"
        - "required_capability"
        - "permission_pack"
        - "required_permissions"
        - "attempt"
        - "max_retries"
        - "lease_owner"
        - "lease_until"
        - "error_type"
        - "error"
        - "result_reference"
        - "created_at"
        - "updated_at"

    - id: "get_task"
      method: "GET"
      path: "/v1/tasks/{task_id}"
      response_200_schema_ref: "normalized_task"
      response_404: {error: "task_not_found", task_id: "string"}

    - id: "list_task_failures"
      method: "GET"
      path: "/v1/tasks/failures"
      query:
        error_type: {type: "string", default: "deliverable_gate_failed"}
        limit: {type: "integer", default: 50, max: 500}
      response_200:
        error_type: "string"
        total: "integer"
        returned: "integer"
        truncated: "boolean"
        tasks: "array[compact_task]"

    - id: "lease_task"
      method: "POST"
      path: "/v1/tasks/lease"
      request_body_schema_ref: "lease_request"
      responses:
        "200": {schema_ref: "normalized_task"}
        "204": {meaning: "no compatible task or node is draining"}
      pre_actions:
        - "runs requeue_expired_leases() before scanning queue"
      compatibility_rules:
        - "target_node/required_node must match node_id when present"
        - "allowed_nodes must include node_id when present"
        - "required_capability must be present or compatible through alias map"
        - "required_permissions must be subset of node permissions unless node has '*'"
      lease_mutations:
        state: "leased"
        attempt: "increments by 1"
        attempt_id: "<task_id>-attempt-<attempt>"
        lease_owner: "<node_id>:<agent_id>"
        lease_until: "now + FACTORY_LEASE_DURATION"
        heartbeat_at: "server time"
        granted_permissions: "intersection of task required permissions and node permissions, or all required when node has '*'"

    - id: "task_heartbeat"
      method: "POST"
      path: "/v1/tasks/{task_id}/heartbeat"
      request_body_schema_ref: "task_heartbeat_request"
      response_200_schema_ref: "normalized_task"
      response_404: {error: "task_not_found", task_id: "string"}
      behavior:
        non_terminal_task:
          state: "body.state or running"
          heartbeat_at: "server time"
          lease_until: "now + FACTORY_LEASE_DURATION"
          updated_fields: ["pid", "worktree", "branch", "log_paths"]
        terminal_task:
          state: "unchanged"
          response: "current task"

    - id: "complete_task"
      method: "POST"
      path: "/v1/tasks/{task_id}/complete"
      request_body_schema_ref: "task_complete_request"
      responses:
        "200":
          schema:
            task: "normalized_task"
            review_task: "normalized_task|null"
        "404": {error: "task_not_found", task_id: "string"}
        "422":
          error: "deliverable_gate_failed"
          detail: "deliverable_gate_failed:<comma-separated detail codes>"
          task: "failed normalized_task"
      success_mutations:
        state: "completed when no review needed or PR URL exists; otherwise waiting_review"
        result: "body.result or body"
        result_reference: "body.result_reference or result.result_path"
        heartbeat_at: "server time"
        lease_until: null
        error_type: null
        error: null
        attempt_history_status: "completed"
      review_creation:
        condition: "create_review_on_complete=true and result.pull_request_url/pr_url exists"
        review_kind: "review_pr"
        review_state: "review"
        review_target_node_default: "new"

    - id: "annotate_task"
      method: "POST"
      path: "/v1/tasks/{task_id}/annotate"
      request_body_schema_ref: "task_annotate_request"
      responses:
        "200":
          schema:
            task: "normalized_task"
            review_task: "normalized_task|null"
        "404": {error: "task_not_found", task_id: "string"}
      behavior:
        - "merges body.result or body into existing task.result"
        - "updates result_reference"
        - "if task.state=waiting_review and PR URL appears, moves task to completed and creates review task"

    - id: "fail_task"
      method: "POST"
      path: "/v1/tasks/{task_id}/fail"
      request_body_schema_ref: "task_fail_request"
      response_200_schema_ref: "normalized_task"
      response_404: {error: "task_not_found", task_id: "string"}
      behavior:
        - "stores error_type, error, result, result_reference"
        - "clears lease_until"
        - "appends attempt_history status=failed"
        - "if attempt < max_retries and retry=true, transitions retry_scheduled then queued and enqueues"
        - "otherwise transitions failed"

    - id: "cancel_task"
      method: "POST"
      path: "/v1/tasks/{task_id}/cancel"
      request_body: {}
      response_200_schema_ref: "normalized_task"
      response_404: {error: "task_not_found", task_id: "string"}
      behavior:
        - "removes task_id from queue"
        - "sets state=cancelled"
        - "sets cancel_requested_at"
        - "clears lease_until"

    - id: "reap_expired_leases"
      method: "POST"
      path: "/v1/tasks/reap-expired"
      request_body:
        limit: {type: "integer|null"}
      response_200:
        task_total: "integer"
        lease_index_total: "integer"
        scan_limit: "integer|null"
        scan_truncated: "boolean"
        checked: "integer"
        expired: "integer"
        requeued: "array[task_id]"
        dead_lettered: "array[task_id]"
        skipped: "array[object]"
        requeued_total: "integer"
        dead_lettered_total: "integer"
        skipped_total: "integer"
      behavior:
        - "checks leased/running/review tasks from lease index"
        - "when lease_until expired, sets error_type=lease_expired"
        - "if attempt < max_retries, transitions retry_scheduled then queued and enqueues"
        - "otherwise transitions dead_letter and pushes task_id to dead_letter list"

    - id: "sweep_stuck_tasks"
      method: "POST"
      path: "/v1/tasks/sweep-stuck"
      request_body:
        limit: {type: "integer|null"}
        stale_after_seconds: {type: "integer|null", default: "FACTORY_TASK_HEARTBEAT_STALE_AFTER"}
      response_200:
        task_total: "integer"
        lease_index_total: "integer"
        scan_limit: "integer|null"
        stale_after_seconds: "integer"
        scan_truncated: "boolean"
        checked: "integer"
        stuck: "integer"
        requeued: "array[{task_id, heartbeat_age_seconds}]"
        dead_lettered: "array[{task_id, heartbeat_age_seconds}]"
        skipped: "array[object]"
        requeued_total: "integer"
        dead_lettered_total: "integer"
        skipped_total: "integer"
      behavior:
        - "checks leased/running/review tasks"
        - "missing or invalid heartbeat_at is skipped with reason=missing_or_invalid_heartbeat"
        - "stale heartbeat sets error_type=stuck_no_heartbeat"
        - "retry/dead_letter behavior mirrors reap_expired_leases"

    - id: "rebuild_task_indexes"
      method: "POST"
      path: "/v1/tasks/rebuild-indexes"
      request_body:
        limit: {type: "integer|null"}
      response_200:
        indexed: "integer"
        missing: "integer"
        states: "object[state -> count]"
        limited: "boolean"
        limit: "integer|null"

    - id: "publish_agent_message"
      method: "POST"
      path: "/v1/agent-messages"
      request_body_schema_ref: "agent_message"
      response_201_schema_ref: "agent_message"
      behavior:
        - "normalizes sender/from, recipients/to, body/message"
        - "publishes to all plus every recipient"
        - "each feed is trimmed to last 500 messages"

    - id: "list_agent_messages"
      method: "GET"
      path: "/v1/agent-messages"
      query:
        target: {type: "string", default: "all"}
        limit: {type: "integer", default: 50}
      response_200:
        target: "string"
        messages: "array[agent_message]"

  http_errors:
    not_found:
      status: 404
      body: {error: "not_found", path: "string"}
      when: "unknown GET/POST path"
    task_not_found:
      status: 404
      body: {error: "task_not_found", task_id: "string"}
      when: "task-specific endpoint references missing task"
    deliverable_gate_failed:
      status: 422
      body_fields: ["error", "detail", "task"]
      when: "complete endpoint lacks required autonomous-task evidence"
    control_plane_error:
      status: 500
      body: {error: "control_plane_error", detail: "string"}
      when: "uncaught exception, JSON parse error, missing required key, Redis error, or type conversion error"

  task_error_types:
    deliverable_gate_failed:
      producer: "Control Plane /complete"
      terminal_state: "failed"
      retry_behavior: "no automatic retry in /complete gate path"
      detail_codes: ["missing_result_reference", "missing_code_delta", "missing_checks"]
    lease_expired:
      producer: "Control Plane requeue_expired_leases"
      state_behavior: "retry_scheduled -> queued when retry budget remains; dead_letter when exhausted"
    stuck_no_heartbeat:
      producer: "Control Plane sweep_stuck_tasks"
      state_behavior: "retry_scheduled -> queued when retry budget remains; dead_letter when exhausted"
    runner_empty_response:
      producer: "Agent Host classify_runner_exception"
      state_behavior: "sent to /fail; retry=true when attempt < max_retries"
    runner_unavailable:
      producer: "Agent Host classify_runner_exception"
      state_behavior: "sent to /fail; retry=true when attempt < max_retries"
    runtime_error:
      producer: "Agent Host classify_runner_exception default, /fail default"
      state_behavior: "sent to /fail; retry=true when attempt < max_retries"

  operational_skip_reasons:
    invalid_lease_until:
      producer: "requeue_expired_leases"
    missing_or_invalid_heartbeat:
      producer: "sweep_stuck_tasks"

  lifecycle:
    transitions:
      - from: null
        to: "queued"
        trigger: "POST /v1/tasks"
      - from: "queued"
        to: "leased"
        trigger: "POST /v1/tasks/lease returns compatible task"
      - from: "review"
        to: "leased"
        trigger: "POST /v1/tasks/lease can lease review-state tasks from queue"
      - from: "leased"
        to: "running"
        trigger: "POST /v1/tasks/{task_id}/heartbeat with state omitted or running"
      - from: "leased|running|review"
        to: "leased|running|review"
        trigger: "task heartbeat extends lease_until"
      - from: "leased|running|review"
        to: "completed"
        trigger: "POST /v1/tasks/{task_id}/complete when no review is required or PR URL exists"
      - from: "leased|running|review"
        to: "waiting_review"
        trigger: "complete with create_review_on_complete=true and no PR URL"
      - from: "waiting_review"
        to: "completed"
        trigger: "POST /v1/tasks/{task_id}/annotate adds pull_request_url/pr_url"
      - from: "running|leased|review"
        to: "retry_scheduled"
        trigger: "POST /v1/tasks/{task_id}/fail with retry=true and attempt < max_retries"
      - from: "retry_scheduled"
        to: "queued"
        trigger: "same fail/reap/sweep code path after saving retry_scheduled"
      - from: "running|leased|review"
        to: "failed"
        trigger: "POST /v1/tasks/{task_id}/fail when retry=false or retry budget exhausted"
      - from: "running|leased|review"
        to: "dead_letter"
        trigger: "reap/sweep detects expired/stuck task with exhausted retry budget"
      - from: "queued|leased|running|review|waiting_review"
        to: "cancelled"
        trigger: "POST /v1/tasks/{task_id}/cancel"

  agent_host_control_plane_calls:
    startup:
      - endpoint: "POST /v1/nodes/register"
        body_schema_ref: "node_register_request"
    main_loop:
      - endpoint: "POST /v1/nodes/{node_id}/heartbeat"
        cadence_seconds_default: 10
      - endpoint: "POST /v1/tasks/lease"
        body_schema_ref: "lease_request"
      - endpoint: "POST /v1/agent-messages"
        kinds: ["task_leased", "task_started", "task_completed", "task_failed"]
    during_task:
      - endpoint: "POST /v1/tasks/{task_id}/heartbeat"
        cadence_seconds_default: 20
        purpose: "refresh lease while commands/runners execute"
      - endpoint: "POST /v1/tasks/{task_id}/complete"
        when: "runner returns result"
      - endpoint: "POST /v1/tasks/{task_id}/fail"
        when: "runner or command raises"

  artifact_contract:
    location: "Agent Host node-local artifact_root/<task_id>/<attempt_id>/"
    control_plane_visibility: "stores result payload and result_reference path; does not read artifact files"
    files_written_by_agent_host:
      - "result.json"
      - "artifact-manifest.json"
      - "stdout.log"
      - "stderr.log"
      - "generic-prompt.txt for generic implementation tasks"
    result_reference_default: "absolute path to result.json on Agent Host"
```

## Короткая интерпретация

Главный удалённый контракт остаётся remote-first: задача входит через `POST /v1/tasks`, Agent Host получает её только через lease, а результат возвращает как JSON payload плюс ссылку `result_reference` на node-local artifact. Control Plane хранит состояние, индексы, очередь, lease и сообщения агентов, но не читает содержимое рабочих деревьев или artifact-директорий узла.

Самые важные интеграционные ограничения:

- `POST /v1/tasks/lease` возвращает `204`, если подходящей задачи нет или node draining; Agent Host трактует это как `None`.
- `lease_until` хранится как epoch seconds, а `heartbeat_at` как ISO datetime string.
- Для autonomous implementation задач `/complete` требует evidence: `result_reference`, code delta (`changed_files` или commit/PR URL) и непустые `checks`.
- Ошибки контрактно делятся на HTTP error body (`not_found`, `task_not_found`, `control_plane_error`, `deliverable_gate_failed`) и task-level `error_type` (`runtime_error`, `runner_unavailable`, `runner_empty_response`, `lease_expired`, `stuck_no_heartbeat`, `deliverable_gate_failed`).
- `waiting_review` не входит в lease-index, но входит в active summary; перевод в `completed` происходит через `/annotate`, когда появляется `pull_request_url` или `pr_url`.
