import { ProgramStatusClientError, programStatusFromWire } from "@services/programStatusClient";
import { describe, expect, it } from "vitest";

const wire = {
  schema_version: "kolibri.wallboard.program-status.v1",
  availability: "partial",
  source_freshness: "live",
  source: "program-ledger/home",
  as_of: "2026-07-13T00:17:44Z",
  observed_at: "2026-07-13T00:18:00Z",
  age_seconds: 16,
  source_sha256: `sha256:${"a".repeat(64)}`,
  source_commit: "45eef8aa3ce4a15858cf2284d31bf4da286dbc59",
  overall_status: "in_progress",
  gate_progress: {
    completed: 2,
    in_progress: 3,
    blocked: 3,
    not_started: 3,
    total: 11,
    completed_ratio: 0.1818,
  },
  gates: [{
    gate: 1,
    id: "gate-1",
    name: "Home development authority",
    status: "in_progress",
    blockers: ["provider canary is absent"],
    next_action: "run a fenced provider canary",
    evidence_ids: ["home:clean"],
    updated_at: "2026-07-13T00:17:44Z",
  }],
};

describe("program status wire contract", () => {
  it("maps the owner projection without inventing fleet metrics", () => {
    const snapshot = programStatusFromWire(wire);
    expect(snapshot.availability).toBe("partial");
    expect(snapshot.progress).toEqual({
      completed: 2,
      inProgress: 3,
      blocked: 3,
      notStarted: 3,
      total: 11,
      completedRatio: 0.1818,
    });
    expect(snapshot.gates[0]?.nextAction).toBe("run a fenced provider canary");
    expect(JSON.stringify(snapshot)).not.toContain("online_nodes");
  });

  it("rejects mismatched counts instead of normalizing them", () => {
    expect(() => programStatusFromWire({
      ...wire,
      gate_progress: { ...wire.gate_progress, total: 21 },
    })).toThrowError(ProgramStatusClientError);
  });

  it("rejects unavailable payloads as data snapshots", () => {
    expect(() => programStatusFromWire({
      schema_version: "kolibri.wallboard.program-status.v1",
      availability: "unavailable",
    })).toThrowError(/program_status_availability_invalid/);
  });
});
