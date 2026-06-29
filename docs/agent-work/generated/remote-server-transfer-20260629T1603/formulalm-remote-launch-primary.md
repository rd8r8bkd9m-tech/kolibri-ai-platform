# FormulaLM Remote Launch Envelope

```json
{
  "schema": "kolibri.remote_benchmark.launch_envelope.v1",
  "task_id": "KOL-REMOTE-SERVER-TASK-20260629T1603-004-PRIMARY-FORMULALM",
  "created_at_utc": "2026-06-29T16:10:28Z",
  "created_by_role": "autonomous_engineer",
  "purpose": "Prepare a machine-readable launch envelope for a remote Qwen/FormulaLM benchmark without running the model benchmark on Mac hosts.",
  "benchmark": {
    "family": "qwen-formulalm",
    "primary_model": "FormulaLM",
    "comparison_baseline": "Qwen",
    "execution_mode": "remote_server_only",
    "benchmark_execution_requested_by_this_artifact": false
  },
  "eligibility": {
    "eligible_host_os": [
      "Linux"
    ],
    "ineligible_host_os": [
      "Darwin",
      "macOS",
      "Mac OS X"
    ],
    "requires_remote_server": true,
    "requires_gpu_or_declared_cpu_fallback": true,
    "requires_network_isolation_from_owner_mac": true,
    "requires_artifact_directory": "docs/agent-work/generated/remote-server-transfer-20260629T1603/",
    "requires_no_secret_output": true,
    "requires_control_plane_result_reference": true
  },
  "no_mac_guard": {
    "policy": "Do not launch the model benchmark when uname -s is Darwin or when Python platform.system() reports Darwin.",
    "preflight_commands": [
      "test \"$(uname -s)\" != \"Darwin\"",
      "python3 - <<'PY'\nimport platform, sys\nif platform.system() == 'Darwin':\n    raise SystemExit('blocked: FormulaLM benchmark must run on a remote non-Mac server')\nprint(platform.system())\nPY"
    ],
    "blocked_result": {
      "state": "failed",
      "error_type": "ineligible_host_os",
      "retry": false,
      "message": "FormulaLM benchmark launch blocked by no-Mac guard."
    }
  },
  "remote_launch": {
    "target_selector": {
      "preferred_node_role": "remote_inference_or_training_server",
      "allowed_node_ids": [
        "9fts",
        "home",
        "remote-linux-gpu"
      ],
      "disallowed_node_ids": [
        "owner-mac",
        "local-mac"
      ]
    },
    "control_plane_kind": "owner_remote_task",
    "idempotency_key": "formulalm-remote-benchmark-20260629T1603-primary",
    "lease_requirements": {
      "exclusive_gpu": true,
      "heartbeat_required": true,
      "heartbeat_interval_seconds": 30,
      "max_silent_seconds": 180
    },
    "environment_contract": {
      "working_directory": "repo",
      "artifact_root": "docs/agent-work/generated/remote-server-transfer-20260629T1603/",
      "do_not_print": [
        "tokens",
        "private keys",
        "API secrets",
        "SSH private material"
      ],
      "allowed_outputs": [
        "aggregate metrics",
        "sanitized logs",
        "benchmark manifest",
        "result json",
        "hardware summary without secrets"
      ]
    }
  },
  "metrics": {
    "required": [
      {
        "name": "accuracy",
        "type": "number",
        "unit": "ratio",
        "range": [
          0,
          1
        ]
      },
      {
        "name": "exact_match",
        "type": "number",
        "unit": "ratio",
        "range": [
          0,
          1
        ]
      },
      {
        "name": "latency_p50_ms",
        "type": "number",
        "unit": "milliseconds",
        "minimum": 0
      },
      {
        "name": "latency_p95_ms",
        "type": "number",
        "unit": "milliseconds",
        "minimum": 0
      },
      {
        "name": "tokens_per_second",
        "type": "number",
        "unit": "tokens/second",
        "minimum": 0
      },
      {
        "name": "gpu_memory_peak_mb",
        "type": "number",
        "unit": "MiB",
        "minimum": 0
      },
      {
        "name": "error_count",
        "type": "integer",
        "minimum": 0
      }
    ],
    "comparison_keys": [
      "primary_model",
      "comparison_baseline",
      "dataset_id",
      "prompt_template_id",
      "seed",
      "hardware_profile"
    ]
  },
  "artifact_paths": {
    "launch_envelope_markdown": "docs/agent-work/generated/remote-server-transfer-20260629T1603/formulalm-remote-launch-primary.md",
    "fallback_agent_message": "docs/agent-work/generated/remote-server-transfer-20260629T1603/agent-message-fallback.md",
    "result_reference": "docs/agent-work/generated/remote-server-transfer-20260629T1603/result.json",
    "expected_remote_result_json": "docs/agent-work/generated/remote-server-transfer-20260629T1603/formulalm-benchmark-result.json",
    "expected_remote_metrics_json": "docs/agent-work/generated/remote-server-transfer-20260629T1603/formulalm-benchmark-metrics.json",
    "expected_remote_log": "docs/agent-work/generated/remote-server-transfer-20260629T1603/formulalm-benchmark.log",
    "expected_remote_manifest": "docs/agent-work/generated/remote-server-transfer-20260629T1603/artifact-manifest.json"
  },
  "stop_gates": [
    {
      "gate": "host_os",
      "condition": "uname -s == Darwin or platform.system() == Darwin",
      "action": "stop_without_launching_benchmark"
    },
    {
      "gate": "remote_server_missing",
      "condition": "no eligible remote Linux server lease is available",
      "action": "stop_and_report_waiting_for_capacity"
    },
    {
      "gate": "missing_dataset_or_model",
      "condition": "FormulaLM, Qwen baseline, dataset, or tokenizer cannot be resolved on remote server",
      "action": "stop_before_inference"
    },
    {
      "gate": "gpu_memory",
      "condition": "required model memory exceeds available GPU memory and no explicit CPU fallback is approved",
      "action": "stop_before_loading_model"
    },
    {
      "gate": "metric_contract",
      "condition": "required metrics cannot be produced as numeric JSON values",
      "action": "mark_failed_with_contract_error"
    },
    {
      "gate": "artifact_contract",
      "condition": "result_reference or expected artifact paths cannot be written",
      "action": "mark_failed_with_artifact_error"
    }
  ],
  "verification_commands": [
    "test \"$(uname -s)\" != \"Darwin\"",
    "python3 - <<'PY'\nimport json\nfrom pathlib import Path\npath = Path('docs/agent-work/generated/remote-server-transfer-20260629T1603/formulalm-remote-launch-primary.md')\ntext = path.read_text(encoding='utf-8')\nfence = chr(96) * 3\nstart = text.index(fence + 'json') + len(fence + 'json')\nend = text.index('\\n' + fence, start)\nenvelope = json.loads(text[start:end])\nrequired = ['eligibility', 'metrics', 'artifact_paths', 'stop_gates', 'no_mac_guard']\nmissing = [key for key in required if key not in envelope]\nif missing:\n    raise SystemExit(f'missing keys: {missing}')\nassert 'Darwin' in envelope['eligibility']['ineligible_host_os']\nassert envelope['benchmark']['benchmark_execution_requested_by_this_artifact'] is False\nassert envelope['artifact_paths']['result_reference'] == envelope['control_plane_result']['result_reference']\nprint('launch envelope json ok')\nPY",
    "python3 -m compileall -q ops/factory_control.py ops/agent_host.py ops/kolibri-dispatch"
  ],
  "control_plane_result": {
    "result_reference": "docs/agent-work/generated/remote-server-transfer-20260629T1603/result.json",
    "state_on_success": "completed",
    "telegram_fallback": "docs/agent-work/generated/remote-server-transfer-20260629T1603/agent-message-fallback.md"
  }
}
```

## Operator Notes

This artifact is a launch envelope only. It does not start the Qwen/FormulaLM model benchmark, and it must not be used to start the benchmark on a Mac. A downstream launcher should parse the JSON block above, acquire an eligible remote Linux lease, run the no-Mac preflight commands on the execution host, then write the benchmark output to the declared artifact paths.

The Control Plane `result_reference` for this preparation step is `docs/agent-work/generated/remote-server-transfer-20260629T1603/result.json`.
