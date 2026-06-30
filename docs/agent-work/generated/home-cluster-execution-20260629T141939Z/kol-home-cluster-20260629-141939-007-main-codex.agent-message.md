# Agent Message

Task `KOL-HOME-CLUSTER-20260629-141939-007-MAIN-CODEX-DELIVERABLE-RETRY` completed for deterministic estimates.

Added a deterministic recalculation fixture and regression test:

- fixture: `backend/tests/fixtures/deterministic_estimate_recalculation.json`
- test: `backend/tests/test_estimate_document_pdf_engines.py::test_estimate_recalculation_matches_deterministic_fixture`

Checks:

- `.venv/bin/python -m pytest backend/tests/test_estimate_document_pdf_engines.py -q` -> `5 passed`
- `.venv/bin/python -m pytest backend/tests tests -q` -> `61 passed`

Risk: fixture intentionally pins current rounding and fingerprint payload; update it alongside any deliberate calculation contract change.
