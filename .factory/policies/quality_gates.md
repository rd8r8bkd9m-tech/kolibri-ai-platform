# Quality Gates

Default local gates:

```bash
python3 -m py_compile backend/main.py backend/auth.py backend/config.py
python3 -m ruff check backend infra scripts --select E,F,W --ignore E501
npm --prefix frontend run build
npm --prefix frontend run lint
cargo test --manifest-path kolibri_nano/Cargo.toml
```

Factory gates:

```bash
python3 -m json.tool .factory/server_inventory.json >/dev/null
python3 -m json.tool .factory/agents/registry.json >/dev/null
python3 -m json.tool .factory/backlog/prioritized.json >/dev/null
python3 .factory/scripts/factory_status.py
python3 .factory/scripts/dispatch_task.py --task .factory/tasks/ready/KOL-CANARY-001.json --dry-run
python3 .factory/scripts/validate_result.py .factory/templates/result_envelope.json
```

For FormulaLM:
- immutable dataset manifest;
- document-level split;
- no train/test leakage;
- validation-only checkpoint choice;
- untouched final test;
- multiple seeds;
- baseline comparison;
- confidence interval;
- checkpoint/config/tokenizer hashes;
- honest negative results.
