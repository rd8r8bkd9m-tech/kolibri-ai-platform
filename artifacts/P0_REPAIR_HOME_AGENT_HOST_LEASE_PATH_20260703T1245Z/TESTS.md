# TESTS.md — Repair Home Agent Host Lease Path

## Tests Run
```
python3 -m pytest -q --ignore=backend/tests/test_estimate_document_pdf_engines.py
# 164 passed in 28.05s
```

## Tests Written (inline verification)
- Home node `agent_host_api` path present in fabric catalog
- `compatible(owner_remote_task, home, runner:mimo, generic_implementation)` returns True
- `compatible` rejects wrong `target_node`
- `compatible` rejects missing `required_capability`
- `runner_capability_names("mimo")` correctness

## No Regressions
All 164 existing tests pass. The single excluded test (`test_estimate_document_pdf_engines.py`) fails due to a pre-existing missing `reportlab` dependency unrelated to this change.
