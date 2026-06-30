# KOL-HOME-CLUSTER-20260629-141939-007-MAIN-CODEX

## Goal

Prepare an artifact-backed deterministic estimate recalculation fixture so future changes can verify exact monetary rounding, audit lines, and recalculation fingerprint stability.

## Implementation Delta

- Added `backend/tests/fixtures/deterministic_estimate_recalculation.json` with a fixed estimate input and expected recalculation outputs.
- Extended `backend/tests/test_estimate_document_pdf_engines.py` with `test_estimate_recalculation_matches_deterministic_fixture`.
- The new test validates exact totals, per-line audit entries, the stable SHA-256 fingerprint, and repeat recalculation equality from the same fixture input.
- No runtime estimate engine behavior was changed.

## Touched Paths

- `backend/tests/fixtures/deterministic_estimate_recalculation.json`
- `backend/tests/test_estimate_document_pdf_engines.py`
- `docs/agent-work/generated/home-cluster-execution-20260629T141939Z/kol-home-cluster-20260629-141939-007-main-codex.md`
- `docs/agent-work/generated/home-cluster-execution-20260629T141939Z/kol-home-cluster-20260629-141939-007-main-codex.agent-message.md`

## Verification Log

- `python3 -m pytest backend/tests/test_estimate_document_pdf_engines.py -q`
  - Result: preflight failed because the base environment did not include `pytest`.
- `python3 -m venv .venv && .venv/bin/python -m pip install -q -r backend/requirements.txt pytest`
  - Result: local ignored verification environment created successfully.
- `.venv/bin/python -m pytest backend/tests/test_estimate_document_pdf_engines.py -q`
  - Result: `5 passed, 1 warning in 2.12s`.
- `.venv/bin/python -m pytest backend/tests tests -q`
  - Result: `61 passed, 1 warning in 7.91s`.

## Risks

- The deterministic fixture pins the current calculation contract. If rounding policy or fingerprint payload intentionally changes, this fixture must be updated in the same change.
- `calculated_at` and `updated_at` remain wall-clock values and are intentionally excluded from exact fixture assertions; the stable contract is totals, line audit payload, and fingerprint.
- Verification produced a ReportLab deprecation warning from a third-party dependency under Python 3.12; no test failed.

## Telegram Summary

Deterministic estimate recalculation fixture prepared. Added a fixed JSON fixture and regression test for exact totals, audit lines, and fingerprint stability. Verification: targeted estimate/PDF suite passed (`5 passed`), full Python suite passed (`61 passed`). Telegram gateway was not available in this session, so a fallback agent-message was written next to this report.

## Result Reference

- Artifact report: `docs/agent-work/generated/home-cluster-execution-20260629T141939Z/kol-home-cluster-20260629-141939-007-main-codex.md`
- Fallback agent-message: `docs/agent-work/generated/home-cluster-execution-20260629T141939Z/kol-home-cluster-20260629-141939-007-main-codex.agent-message.md`
