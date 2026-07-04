#!/usr/bin/env python3
"""Kolibri Truth Factory — Claims, Evidence, and Verdict ledgers.

Lightweight implementation for tracking truth in the factory.
No external dependencies — stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Literal


VerdictType = Literal["true", "false", "partial", "not_proven", "blocked", "stale", "degraded"]
ConfidenceLevel = Literal["high", "medium", "low"]
ClaimStatus = Literal["proposed", "challenged", "verified", "rejected", "partial", "not_proven"]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class Claim:
    claim_id: str
    task_id: str
    made_by: str
    claim: str
    scope: str
    status: ClaimStatus = "proposed"
    evidence: list[str] = field(default_factory=list)
    counterclaims: list[str] = field(default_factory=list)
    verdict: str = ""
    confidence: str = "low"
    next_action: str = ""
    created_at: str = field(default_factory=_now)


@dataclass
class Evidence:
    evidence_id: str
    claim_id: str
    type: str
    source: str
    timestamp: str = field(default_factory=_now)
    content_hash: str = ""
    summary: str = ""
    redacted: bool = True
    path: str = ""
    valid: bool = True


@dataclass
class Verdict:
    verdict_id: str
    claim_id: str
    verdict: VerdictType
    confidence: ConfidenceLevel
    evidence: list[str] = field(default_factory=list)
    reasoning: str = ""
    next_action: str = ""
    owner_summary: str = ""
    created_at: str = field(default_factory=_now)


class TruthLedger:
    """Manages claims, evidence, and verdicts."""

    def __init__(self) -> None:
        self._claims: dict[str, Claim] = {}
        self._evidence: dict[str, Evidence] = {}
        self._verdicts: dict[str, Verdict] = {}

    # ── Claims ─────────────────────────────────────────────────────────

    def create_claim(
        self, task_id: str, made_by: str, claim: str, scope: str
    ) -> Claim:
        c = Claim(
            claim_id=_id("C"),
            task_id=task_id,
            made_by=made_by,
            claim=claim,
            scope=scope,
        )
        self._claims[c.claim_id] = c
        return c

    def challenge_claim(self, claim_id: str, counterclaim_id: str) -> None:
        c = self._claims.get(claim_id)
        if c:
            c.status = "challenged"
            c.counterclaims.append(counterclaim_id)

    def get_claim(self, claim_id: str) -> Claim | None:
        return self._claims.get(claim_id)

    def all_claims(self) -> list[Claim]:
        return list(self._claims.values())

    # ── Evidence ───────────────────────────────────────────────────────

    def add_evidence(
        self,
        claim_id: str,
        type: str,
        source: str,
        summary: str = "",
        path: str = "",
        content: str = "",
    ) -> Evidence:
        e = Evidence(
            evidence_id=_id("E"),
            claim_id=claim_id,
            type=type,
            source=source,
            summary=summary,
            path=path,
            content_hash=_sha256(content) if content else "",
        )
        self._evidence[e.evidence_id] = e
        c = self._claims.get(claim_id)
        if c:
            c.evidence.append(e.evidence_id)
            if c.status == "proposed":
                c.status = "challenged"
        return e

    def get_evidence(self, evidence_id: str) -> Evidence | None:
        return self._evidence.get(evidence_id)

    def evidence_for_claim(self, claim_id: str) -> list[Evidence]:
        return [e for e in self._evidence.values() if e.claim_id == claim_id]

    # ── Verdicts ───────────────────────────────────────────────────────

    def set_verdict(
        self,
        claim_id: str,
        verdict: VerdictType,
        confidence: ConfidenceLevel,
        reasoning: str = "",
        next_action: str = "",
        owner_summary: str = "",
    ) -> Verdict:
        v = Verdict(
            verdict_id=_id("V"),
            claim_id=claim_id,
            verdict=verdict,
            confidence=confidence,
            reasoning=reasoning,
            next_action=next_action,
            owner_summary=owner_summary,
        )
        self._verdicts[v.verdict_id] = v
        c = self._claims.get(claim_id)
        if c:
            c.verdict = verdict
            c.confidence = confidence
            if verdict == "true":
                c.status = "verified"
            elif verdict in ("false", "rejected"):
                c.status = "rejected"
            elif verdict == "partial":
                c.status = "partial"
            elif verdict == "not_proven":
                c.status = "not_proven"
        return v

    def get_verdict(self, verdict_id: str) -> Verdict | None:
        return self._verdicts.get(verdict_id)

    def verdicts_for_claim(self, claim_id: str) -> list[Verdict]:
        return [v for v in self._verdicts.values() if v.claim_id == claim_id]

    # ── Gates ──────────────────────────────────────────────────────────

    def require_evidence_for_truth(self, claim_id: str) -> bool:
        """Reject if claim has no evidence."""
        c = self._claims.get(claim_id)
        if not c:
            return False
        return len(c.evidence) > 0

    def reject_generic_completion(self, claim_id: str) -> bool:
        """Reject if claim is generic completion without artifact."""
        c = self._claims.get(claim_id)
        if not c:
            return True
        evidence = self.evidence_for_claim(claim_id)
        has_artifact = any(e.type == "artifact" for e in evidence)
        has_api = any(e.type == "api_response" for e in evidence)
        return has_artifact or has_api

    # ── Export ─────────────────────────────────────────────────────────

    def export(self) -> dict:
        return {
            "claims": [asdict(c) for c in self._claims.values()],
            "evidence": [asdict(e) for e in self._evidence.values()],
            "verdicts": [asdict(v) for v in self._verdicts.values()],
        }

    def to_json(self) -> str:
        return json.dumps(self.export(), indent=2, default=str)


if __name__ == "__main__":
    ledger = TruthLedger()

    # Example: Start Factory claim
    c = ledger.create_claim("KOL-TASK-ca9353c8620e", "proposer", "Start Factory works", "api")
    ledger.add_evidence(c.claim_id, "api_response", "POST /v1/tasks", "201 Created")
    ledger.add_evidence(c.claim_id, "artifact", "/tmp/PROOF.md", "221 bytes, content-bearing")
    ledger.set_verdict(c.claim_id, "partial", "high", "9/10 conditions met", "deliver owner summary")

    print(f"Claims: {len(ledger.all_claims())}")
    print(f"Evidence: {len(ledger.evidence_for_claim(c.claim_id))}")
    print(f"Verdicts: {len(ledger.verdicts_for_claim(c.claim_id))}")
