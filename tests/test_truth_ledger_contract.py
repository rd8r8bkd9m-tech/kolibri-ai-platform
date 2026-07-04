#!/usr/bin/env python3
"""Tests for truth_ledger.py — Truth Factory contract."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops"))

from truth_ledger import TruthLedger


def test_create_claim():
    ledger = TruthLedger()
    c = ledger.create_claim("T1", "agent-1", "Test claim", "api")
    assert c.claim_id.startswith("C-")
    assert c.status == "proposed"
    assert c.claim == "Test claim"


def test_add_evidence():
    ledger = TruthLedger()
    c = ledger.create_claim("T1", "agent-1", "Test claim", "api")
    e = ledger.add_evidence(c.claim_id, "api_response", "/v1/health", "200 OK")
    assert e.evidence_id.startswith("E-")
    assert e.valid is True
    assert len(ledger.evidence_for_claim(c.claim_id)) == 1


def test_set_verdict():
    ledger = TruthLedger()
    c = ledger.create_claim("T1", "agent-1", "Test claim", "api")
    v = ledger.set_verdict(c.claim_id, "true", "high", "Verified")
    assert v.verdict_id.startswith("V-")
    assert v.verdict == "true"
    assert c.status == "verified"


def test_require_evidence_for_truth():
    ledger = TruthLedger()
    c = ledger.create_claim("T1", "agent-1", "Test claim", "api")
    assert ledger.require_evidence_for_truth(c.claim_id) is False
    ledger.add_evidence(c.claim_id, "api_response", "/v1/health", "200 OK")
    assert ledger.require_evidence_for_truth(c.claim_id) is True


def test_reject_generic_completion():
    ledger = TruthLedger()
    c = ledger.create_claim("T1", "agent-1", "Generic done", "task")
    assert ledger.reject_generic_completion(c.claim_id) is False
    ledger.add_evidence(c.claim_id, "artifact", "/tmp/proof.md", "content")
    assert ledger.reject_generic_completion(c.claim_id) is True


def test_challenge_claim():
    ledger = TruthLedger()
    c1 = ledger.create_claim("T1", "agent-1", "Works", "api")
    c2 = ledger.create_claim("T1", "anti-agent-1", "Does not work", "api")
    ledger.challenge_claim(c1.claim_id, c2.claim_id)
    assert c1.status == "challenged"
    assert c2.claim_id in c1.counterclaims


def test_verdict_updates_claim_status():
    ledger = TruthLedger()
    c = ledger.create_claim("T1", "agent-1", "Test", "api")
    ledger.set_verdict(c.claim_id, "false", "high", "Contradicted")
    assert c.status == "rejected"
    ledger.set_verdict(c.claim_id, "partial", "medium", "Partially true")
    assert c.status == "partial"
    ledger.set_verdict(c.claim_id, "not_proven", "low", "No evidence")
    assert c.status == "not_proven"


def test_export():
    ledger = TruthLedger()
    c = ledger.create_claim("T1", "agent-1", "Test", "api")
    ledger.add_evidence(c.claim_id, "api_response", "/v1/health", "OK")
    ledger.set_verdict(c.claim_id, "true", "high", "Verified")
    data = ledger.export()
    assert len(data["claims"]) == 1
    assert len(data["evidence"]) == 1
    assert len(data["verdicts"]) == 1
