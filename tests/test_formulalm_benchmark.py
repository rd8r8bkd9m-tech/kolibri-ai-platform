from __future__ import annotations

from scripts import formulalm_benchmark as bench


def test_formula_consistent_requires_audit_and_totals() -> None:
    payload = {
        "totals": {
            "labor": "100.00",
            "materials": "50.00",
            "subtotal": "150.00",
            "overhead": "10.50",
            "tax": "0.00",
            "grand_total": "160.50",
        },
        "calculation_audit": [{"formula": "labor + materials + overhead + tax"}],
    }

    assert bench.formula_consistent(payload) is True


def test_summarize_reports_h1_h5_metrics() -> None:
    records = [
        {
            "case_id": "case-a",
            "mode": "baseline",
            "valid_json": False,
            "exact_total": False,
            "formula_consistent": False,
            "parse_error": True,
            "runtime_error": False,
            "manual_fix_required": True,
            "latency_ms": 100,
            "output_hash": "a",
        },
        {
            "case_id": "case-a",
            "mode": "formulalm",
            "valid_json": True,
            "exact_total": True,
            "formula_consistent": True,
            "parse_error": False,
            "runtime_error": False,
            "manual_fix_required": False,
            "latency_ms": 80,
            "output_hash": "b",
        },
    ]

    summary = bench.summarize(records)

    assert summary["baseline"]["parse_error_rate"] == 1.0
    assert summary["baseline"]["manual_fix_count"] == 1
    assert summary["formulalm"]["formula_consistency_rate"] == 1.0
    assert summary["formulalm"]["unique_output_hashes_per_case"] == {"case-a": 1}
    assert summary["formulalm"]["latency_p50_ms"] == 80
    assert summary["formulalm"]["latency_p95_ms"] == 80


def test_decide_verdict_blocks_on_p1_runtime_blocker() -> None:
    assert bench.decide_verdict({}, [{"severity": "P1", "category": "missing_model_runtime"}]) == "blocked"
