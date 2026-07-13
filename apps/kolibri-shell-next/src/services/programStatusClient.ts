export type ProgramAvailability = "live" | "partial" | "stale" | "unavailable";
export type ProgramGateStatus = "completed" | "in_progress" | "blocked" | "not_started";

export interface ProgramGateProgress {
  completed: number;
  inProgress: number;
  blocked: number;
  notStarted: number;
  total: number;
  completedRatio: number;
}

export interface ProgramGate {
  gate: number;
  id: string;
  name: string;
  status: ProgramGateStatus;
  blockers: string[];
  nextAction: string;
  evidenceIds: string[];
  updatedAt: string;
}

export interface ProgramStatusSnapshot {
  availability: Exclude<ProgramAvailability, "unavailable">;
  sourceFreshness: "live" | "stale";
  source: "program-ledger/home";
  asOf: string;
  observedAt: string;
  ageSeconds: number;
  sourceSha256: string;
  sourceCommit: string;
  overallStatus: string;
  progress: ProgramGateProgress;
  gates: ProgramGate[];
}

export interface ProgramStatusClient {
  load(signal: AbortSignal): Promise<ProgramStatusSnapshot>;
}

export class ProgramStatusClientError extends Error {
  constructor(
    readonly status: number,
    readonly reason: string,
  ) {
    super(reason);
    this.name = "ProgramStatusClientError";
  }
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ProgramStatusClientError(502, `${label}_invalid`);
  }
  return value as Record<string, unknown>;
}

function text(value: unknown, label: string): string {
  if (typeof value !== "string" || !value) throw new ProgramStatusClientError(502, `${label}_invalid`);
  return value;
}

function count(value: unknown, label: string): number {
  if (!Number.isInteger(value) || (value as number) < 0) {
    throw new ProgramStatusClientError(502, `${label}_invalid`);
  }
  return value as number;
}

function stringList(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new ProgramStatusClientError(502, `${label}_invalid`);
  }
  return value as string[];
}

function gate(value: unknown): ProgramGate {
  const wire = record(value, "program_gate");
  const status = text(wire.status, "program_gate_status");
  if (!(["completed", "in_progress", "blocked", "not_started"] as string[]).includes(status)) {
    throw new ProgramStatusClientError(502, "program_gate_status_invalid");
  }
  return {
    gate: count(wire.gate, "program_gate_number"),
    id: text(wire.id, "program_gate_id"),
    name: text(wire.name, "program_gate_name"),
    status: status as ProgramGateStatus,
    blockers: stringList(wire.blockers, "program_gate_blockers"),
    nextAction: text(wire.next_action, "program_gate_next_action"),
    evidenceIds: stringList(wire.evidence_ids, "program_gate_evidence"),
    updatedAt: text(wire.updated_at, "program_gate_updated_at"),
  };
}

export function programStatusFromWire(value: unknown): ProgramStatusSnapshot {
  const wire = record(value, "program_status");
  if (wire.schema_version !== "kolibri.wallboard.program-status.v1") {
    throw new ProgramStatusClientError(502, "program_status_schema_invalid");
  }
  const availability = text(wire.availability, "program_status_availability");
  if (!(["live", "partial", "stale"] as string[]).includes(availability)) {
    throw new ProgramStatusClientError(502, "program_status_availability_invalid");
  }
  const freshness = text(wire.source_freshness, "program_status_freshness");
  if (!(["live", "stale"] as string[]).includes(freshness)) {
    throw new ProgramStatusClientError(502, "program_status_freshness_invalid");
  }
  if (wire.source !== "program-ledger/home") {
    throw new ProgramStatusClientError(502, "program_status_source_invalid");
  }
  const progress = record(wire.gate_progress, "program_gate_progress");
  const completed = count(progress.completed, "program_gate_completed");
  const inProgress = count(progress.in_progress, "program_gate_in_progress");
  const blocked = count(progress.blocked, "program_gate_blocked");
  const notStarted = count(progress.not_started, "program_gate_not_started");
  const total = count(progress.total, "program_gate_total");
  if (completed + inProgress + blocked + notStarted !== total) {
    throw new ProgramStatusClientError(502, "program_gate_progress_invalid");
  }
  if (typeof progress.completed_ratio !== "number" || progress.completed_ratio < 0 || progress.completed_ratio > 1) {
    throw new ProgramStatusClientError(502, "program_gate_ratio_invalid");
  }
  if (!Array.isArray(wire.gates)) throw new ProgramStatusClientError(502, "program_gates_invalid");
  return {
    availability: availability as ProgramStatusSnapshot["availability"],
    sourceFreshness: freshness as ProgramStatusSnapshot["sourceFreshness"],
    source: "program-ledger/home",
    asOf: text(wire.as_of, "program_status_as_of"),
    observedAt: text(wire.observed_at, "program_status_observed_at"),
    ageSeconds: count(wire.age_seconds, "program_status_age"),
    sourceSha256: text(wire.source_sha256, "program_status_sha256"),
    sourceCommit: text(wire.source_commit, "program_status_commit"),
    overallStatus: text(wire.overall_status, "program_overall_status"),
    progress: {
      completed,
      inProgress,
      blocked,
      notStarted,
      total,
      completedRatio: progress.completed_ratio,
    },
    gates: wire.gates.map(gate),
  };
}

async function responseReason(response: Response): Promise<string> {
  try {
    const payload = record(await response.json(), "program_status_error");
    const reason = payload.reason ?? payload.detail;
    return typeof reason === "string" && reason ? reason : `program_status_http_${response.status}`;
  } catch {
    return `program_status_http_${response.status}`;
  }
}

export function createProgramStatusClient(): ProgramStatusClient {
  return {
    async load(signal) {
      const response = await fetch("/v1/program/status", {
        method: "GET",
        credentials: "include",
        headers: { Accept: "application/json" },
        signal,
      });
      if (!response.ok) {
        throw new ProgramStatusClientError(response.status, await responseReason(response));
      }
      return programStatusFromWire(await response.json());
    },
  };
}
