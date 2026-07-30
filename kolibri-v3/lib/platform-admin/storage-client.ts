"use client";

import { withCsrfHeader } from "@/lib/csrf";
import {
  boundedText,
  integer,
  isRecord,
} from "@/lib/platform-admin/client";

const MAX_RESPONSE_BYTES = 2 * 1_024 * 1_024;
const SAFE_PROJECT = /^[A-Za-z0-9][A-Za-z0-9._~-]{2,159}$/;
const SAFE_PREVIEW = /^spv_[0-9a-f]{32}$/;
const SAFE_OPERATION = /^sop_[0-9a-f]{32}$/;
const SAFE_QUARANTINE = /^sqn_[0-9a-f]{32}$/;
const SAFE_AUDIT = /^saudit_[0-9a-f]{32}$/;
const SAFE_DIGEST = /^[0-9a-f]{64}$/;
const SAFE_VALUE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$/;
const SAFE_ERROR_CODE = /^[a-z][a-z0-9_.:-]{2,127}$/;
const MAX_BYTES = Number.MAX_SAFE_INTEGER;
const PROTECTED_SCOPES = [
  "active-release",
  "current-symlink",
  "primary-database",
  "durable-volumes",
  "agent-runtime-state",
] as const;

export type StorageNodeId = "home" | "primary";
export type StorageCleanupCategory =
  | "build"
  | "cache"
  | "log"
  | "stopped-container"
  | "project-quarantine";
export type StorageOperationKind =
  | "cleanup"
  | "quarantine"
  | "restore"
  | "purge";
export type StorageConfirmation =
  | "CLEANUP"
  | "QUARANTINE"
  | "RESTORE"
  | "PURGE";
export type StorageProtectionScope = (typeof PROTECTED_SCOPES)[number];

export type StorageCapacitySegment = {
  kind: "root-lv" | "vg-unallocated";
  displayName: string;
  displaySize: string;
  capacityBytes: number;
  readOnly: true;
};

export type StorageCategory = {
  category: StorageCleanupCategory;
  reclaimableBytes: number;
  itemCount: number;
  oldestItemAt: number | null;
};

export type StorageProjectCandidate = {
  projectId: string;
  displayName: string;
  sizeBytes: number;
  lastModifiedAt: number;
};

export type StorageQuarantine = {
  id: string;
  nodeId: StorageNodeId;
  projectId: string;
  status: "retained" | "purge-eligible" | "restored" | "purged";
  sizeBytes: number;
  quarantinedAt: number;
  purgeEligibleAt: number;
  purgedAt: number | null;
  restoredAt: number | null;
};

export type StorageNode = {
  id: StorageNodeId;
  displayName: "Home" | "Primary";
  executorStatus: "ready" | "unavailable" | "error";
  executeEnabled: boolean;
  errorCode: string | null;
  capacityBytes: number | null;
  usedBytes: number | null;
  freeBytes: number | null;
  scannedAt: number | null;
  generation: string | null;
  policyDigest: string | null;
  blockedItemCount: number;
  capacitySource: "live-executor" | "configured-record";
  capacityObservedAt: number | null;
  categories: StorageCategory[];
  capacitySegments: StorageCapacitySegment[];
  projectCandidates: StorageProjectCandidate[];
  quarantines: StorageQuarantine[];
  protectedScopes: StorageProtectionScope[];
};

export type StoragePreview = {
  id: string;
  nodeId: StorageNodeId;
  category: StorageCleanupCategory;
  operationKind: StorageOperationKind;
  projectId: string | null;
  quarantineId: string | null;
  candidateCount: number;
  reclaimableBytes: number;
  protectedItemCount: 0;
  protectedScopes: StorageProtectionScope[];
  confirmation: StorageConfirmation;
  expiresAt: number;
  createdAt: number;
  replayed: boolean;
};

export type StorageOperation = {
  id: string;
  previewId: string;
  nodeId: StorageNodeId;
  category: StorageCleanupCategory;
  operationKind: StorageOperationKind;
  status: "pending" | "succeeded" | "failed";
  affectedItemCount: number;
  reclaimedBytes: number;
  quarantineId: string | null;
  errorCode: string | null;
  createdAt: number;
  completedAt: number | null;
  replayed: boolean;
  reconciled: boolean;
};

export type StorageAuditEvent = {
  id: string;
  action:
    | "storage.preview.created"
    | "storage.operation.succeeded"
    | "storage.operation.failed";
  nodeId: StorageNodeId;
  category: StorageCleanupCategory;
  operationKind: StorageOperationKind;
  targetRef: string;
  previewId: string;
  operationId: string | null;
  createdAt: number;
};

export type StorageSnapshot = {
  nodes: StorageNode[];
  recentOperations: StorageOperation[];
  audit: StorageAuditEvent[];
};

export type StoragePreviewInput =
  | {
      nodeId: StorageNodeId;
      category: Exclude<
        StorageCleanupCategory,
        "project-quarantine"
      >;
      operationKind: "cleanup";
    }
  | {
      nodeId: StorageNodeId;
      category: "project-quarantine";
      operationKind: "quarantine";
      projectId: string;
    }
  | {
      nodeId: StorageNodeId;
      category: "project-quarantine";
      operationKind: "restore" | "purge";
      quarantineId: string;
    };

export class StorageAdminRequestError extends Error {
  constructor(
    readonly code: string,
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "StorageAdminRequestError";
  }
}

const nodeId = (value: unknown): StorageNodeId | null =>
  value === "home" || value === "primary" ? value : null;

const category = (value: unknown): StorageCleanupCategory | null =>
  [
    "build",
    "cache",
    "log",
    "stopped-container",
    "project-quarantine",
  ].includes(String(value))
    ? (value as StorageCleanupCategory)
    : null;

const operationKind = (value: unknown): StorageOperationKind | null =>
  ["cleanup", "quarantine", "restore", "purge"].includes(String(value))
    ? (value as StorageOperationKind)
    : null;

const nullableInteger = (value: unknown) =>
  value === null ? null : integer(value, 0, MAX_BYTES);

const nullableSafe = (value: unknown, pattern: RegExp, maximum: number) => {
  if (value === null) return null;
  const parsed = boundedText(value, maximum);
  return parsed && pattern.test(parsed) ? parsed : undefined;
};

const parseScopes = (value: unknown): StorageProtectionScope[] | null => {
  if (
    !Array.isArray(value) ||
    value.length !== PROTECTED_SCOPES.length ||
    new Set(value).size !== PROTECTED_SCOPES.length ||
    PROTECTED_SCOPES.some((scope) => !value.includes(scope))
  ) {
    return null;
  }
  return [...PROTECTED_SCOPES];
};

function parseCapacitySegment(
  value: unknown,
): StorageCapacitySegment | null {
  if (!isRecord(value)) return null;
  const displayName = boundedText(value.displayName, 120);
  const displaySize = boundedText(value.displaySize, 32);
  const capacityBytes = integer(value.capacityBytes, 0, MAX_BYTES);
  if (
    !["root-lv", "vg-unallocated"].includes(String(value.kind)) ||
    !displayName ||
    !displaySize ||
    capacityBytes === null ||
    value.readOnly !== true
  ) {
    return null;
  }
  return {
    kind: value.kind as StorageCapacitySegment["kind"],
    displayName,
    displaySize,
    capacityBytes,
    readOnly: true,
  };
}

function parseCategory(value: unknown): StorageCategory | null {
  if (!isRecord(value)) return null;
  const parsedCategory = category(value.category);
  const reclaimableBytes = integer(value.reclaimableBytes, 0, MAX_BYTES);
  const itemCount = integer(value.itemCount, 0, 1_000_000_000);
  const oldestItemAt = nullableInteger(value.oldestItemAt);
  if (
    !parsedCategory ||
    reclaimableBytes === null ||
    itemCount === null ||
    oldestItemAt === undefined
  ) {
    return null;
  }
  return {
    category: parsedCategory,
    reclaimableBytes,
    itemCount,
    oldestItemAt,
  };
}

function parseProject(value: unknown): StorageProjectCandidate | null {
  if (!isRecord(value)) return null;
  const projectId = boundedText(value.projectId, 160);
  const displayName = boundedText(value.displayName, 120);
  const sizeBytes = integer(value.sizeBytes, 0, MAX_BYTES);
  const lastModifiedAt = integer(value.lastModifiedAt, 0, MAX_BYTES);
  if (
    !projectId ||
    !SAFE_PROJECT.test(projectId) ||
    !displayName ||
    sizeBytes === null ||
    lastModifiedAt === null
  ) {
    return null;
  }
  return { projectId, displayName, sizeBytes, lastModifiedAt };
}

function parseQuarantine(value: unknown): StorageQuarantine | null {
  if (!isRecord(value)) return null;
  const id = boundedText(value.id, 36);
  const parsedNode = nodeId(value.nodeId);
  const projectId = boundedText(value.projectId, 160);
  const sizeBytes = integer(value.sizeBytes, 0, MAX_BYTES);
  const quarantinedAt = integer(value.quarantinedAt, 0, MAX_BYTES);
  const purgeEligibleAt = integer(value.purgeEligibleAt, 0, MAX_BYTES);
  const purgedAt = nullableInteger(value.purgedAt);
  const restoredAt = nullableInteger(value.restoredAt);
  if (
    !id ||
    !SAFE_QUARANTINE.test(id) ||
    !parsedNode ||
    !projectId ||
    !SAFE_PROJECT.test(projectId) ||
    !["retained", "purge-eligible", "restored", "purged"].includes(
      String(value.status),
    ) ||
    sizeBytes === null ||
    quarantinedAt === null ||
    purgeEligibleAt === null ||
    purgedAt === undefined ||
    restoredAt === undefined ||
    (value.status === "purged" &&
      (purgedAt === null || restoredAt !== null)) ||
    (value.status === "restored" &&
      (restoredAt === null || purgedAt !== null)) ||
    (["retained", "purge-eligible"].includes(String(value.status)) &&
      (purgedAt !== null || restoredAt !== null))
  ) {
    return null;
  }
  return {
    id,
    nodeId: parsedNode,
    projectId,
    status: value.status as StorageQuarantine["status"],
    sizeBytes,
    quarantinedAt,
    purgeEligibleAt,
    purgedAt,
    restoredAt,
  };
}

function parseNode(value: unknown): StorageNode | null {
  if (
    !isRecord(value) ||
    !Array.isArray(value.categories) ||
    !Array.isArray(value.capacitySegments) ||
    !Array.isArray(value.projectCandidates) ||
    !Array.isArray(value.quarantines) ||
    value.categories.length > 5 ||
    value.capacitySegments.length > 2 ||
    value.projectCandidates.length > 100 ||
    value.quarantines.length > 200
  ) {
    return null;
  }
  const id = nodeId(value.id);
  const categories = value.categories.map(parseCategory);
  const capacitySegments = value.capacitySegments.map(parseCapacitySegment);
  const projects = value.projectCandidates.map(parseProject);
  const quarantines = value.quarantines.map(parseQuarantine);
  const scopes = parseScopes(value.protectedScopes);
  const errorCode = nullableSafe(value.errorCode, SAFE_VALUE, 192);
  const generation = nullableSafe(value.generation, SAFE_VALUE, 128);
  const policyDigest = nullableSafe(value.policyDigest, SAFE_DIGEST, 64);
  const blockedItemCount = integer(
    value.blockedItemCount,
    0,
    1_000_000_000,
  );
  const capacityBytes = nullableInteger(value.capacityBytes);
  const usedBytes = nullableInteger(value.usedBytes);
  const freeBytes = nullableInteger(value.freeBytes);
  const scannedAt = nullableInteger(value.scannedAt);
  const capacityObservedAt = nullableInteger(value.capacityObservedAt);
  const ready = value.executorStatus === "ready";
  if (
    !id ||
    value.displayName !== (id === "home" ? "Home" : "Primary") ||
    !["ready", "unavailable", "error"].includes(
      String(value.executorStatus),
    ) ||
    typeof value.executeEnabled !== "boolean" ||
    !["live-executor", "configured-record"].includes(
      String(value.capacitySource),
    ) ||
    (value.executeEnabled === true &&
      (value.executorStatus !== "ready" ||
        value.capacitySource !== "live-executor")) ||
    errorCode === undefined ||
    generation === undefined ||
    policyDigest === undefined ||
    blockedItemCount === null ||
    capacityBytes === undefined ||
    usedBytes === undefined ||
    freeBytes === undefined ||
    scannedAt === undefined ||
    capacityObservedAt === undefined ||
    categories.some((item) => item === null) ||
    capacitySegments.some((item) => item === null) ||
    projects.some((item) => item === null) ||
    quarantines.some((item) => item === null) ||
    !scopes ||
    new Set(categories.map((item) => item?.category)).size !==
      categories.length ||
    new Set(projects.map((item) => item?.projectId)).size !==
      projects.length ||
    new Set(quarantines.map((item) => item?.id)).size !==
      quarantines.length ||
    quarantines.some((item) => item?.nodeId !== id) ||
    (id === "home" && capacitySegments.length !== 2) ||
    (id === "primary" && capacitySegments.length !== 0) ||
    (ready &&
      (value.capacitySource !== "live-executor" ||
        capacityBytes === null ||
        usedBytes === null ||
        freeBytes === null ||
        scannedAt === null ||
        generation === null ||
        policyDigest === null ||
        capacityObservedAt === null)) ||
    (!ready &&
      (value.executeEnabled ||
        value.capacitySource !== "configured-record" ||
        capacityBytes !== null ||
        usedBytes !== null ||
        freeBytes !== null ||
        scannedAt !== null ||
        generation !== null ||
        policyDigest !== null ||
        capacityObservedAt !== null))
  ) {
    return null;
  }
  return {
    id,
    displayName: id === "home" ? "Home" : "Primary",
    executorStatus: value.executorStatus as StorageNode["executorStatus"],
    executeEnabled: value.executeEnabled,
    errorCode,
    capacityBytes,
    usedBytes,
    freeBytes,
    scannedAt,
    generation,
    policyDigest,
    blockedItemCount,
    capacitySource: value.capacitySource as StorageNode["capacitySource"],
    capacityObservedAt,
    categories: categories as StorageCategory[],
    capacitySegments: capacitySegments as StorageCapacitySegment[],
    projectCandidates: projects as StorageProjectCandidate[],
    quarantines: quarantines as StorageQuarantine[],
    protectedScopes: scopes,
  };
}

function parsePreview(value: unknown): StoragePreview | null {
  if (!isRecord(value)) return null;
  const id = boundedText(value.id, 36);
  const parsedNode = nodeId(value.nodeId);
  const parsedCategory = category(value.category);
  const kind = operationKind(value.operationKind);
  const projectId = nullableSafe(value.projectId, SAFE_PROJECT, 160);
  const quarantineId = nullableSafe(
    value.quarantineId,
    SAFE_QUARANTINE,
    36,
  );
  const candidateCount = integer(value.candidateCount, 0, 1_000_000_000);
  const reclaimableBytes = integer(value.reclaimableBytes, 0, MAX_BYTES);
  const expiresAt = integer(value.expiresAt, 0, MAX_BYTES);
  const createdAt = integer(value.createdAt, 0, MAX_BYTES);
  const scopes = parseScopes(value.protectedScopes);
  const expectedConfirmation = {
    cleanup: "CLEANUP",
    quarantine: "QUARANTINE",
    restore: "RESTORE",
    purge: "PURGE",
  } as const;
  const ordinary = ["build", "cache", "log", "stopped-container"];
  if (
    !id ||
    !SAFE_PREVIEW.test(id) ||
    !parsedNode ||
    !parsedCategory ||
    !kind ||
    projectId === undefined ||
    quarantineId === undefined ||
    candidateCount === null ||
    reclaimableBytes === null ||
    expiresAt === null ||
    createdAt === null ||
    value.protectedItemCount !== 0 ||
    !scopes ||
    !["CLEANUP", "QUARANTINE", "RESTORE", "PURGE"].includes(
      String(value.confirmation),
    ) ||
    typeof value.replayed !== "boolean"
  ) {
    return null;
  }
  if (
    value.confirmation !== expectedConfirmation[kind] ||
    (kind === "cleanup" &&
      (!ordinary.includes(parsedCategory) ||
        projectId !== null ||
        quarantineId !== null)) ||
    (kind === "quarantine" &&
      (parsedCategory !== "project-quarantine" ||
        projectId === null ||
        quarantineId !== null ||
        candidateCount !== 1)) ||
    (["restore", "purge"].includes(kind) &&
      (parsedCategory !== "project-quarantine" ||
        projectId !== null ||
        quarantineId === null ||
        candidateCount !== 1))
  ) {
    return null;
  }
  return {
    id,
    nodeId: parsedNode,
    category: parsedCategory,
    operationKind: kind,
    projectId,
    quarantineId,
    candidateCount,
    reclaimableBytes,
    protectedItemCount: 0,
    protectedScopes: scopes,
    confirmation: value.confirmation as StorageConfirmation,
    expiresAt,
    createdAt,
    replayed: value.replayed,
  };
}

export const parseStoragePreview = (value: unknown) => parsePreview(value);

function parseOperation(value: unknown): StorageOperation | null {
  if (!isRecord(value)) return null;
  const id = boundedText(value.id, 36);
  const previewId = boundedText(value.previewId, 36);
  const parsedNode = nodeId(value.nodeId);
  const parsedCategory = category(value.category);
  const kind = operationKind(value.operationKind);
  const quarantineId = nullableSafe(
    value.quarantineId,
    SAFE_QUARANTINE,
    36,
  );
  const errorCode = nullableSafe(value.errorCode, SAFE_VALUE, 192);
  const affectedItemCount = integer(
    value.affectedItemCount,
    0,
    1_000_000_000,
  );
  const reclaimedBytes = integer(value.reclaimedBytes, 0, MAX_BYTES);
  const createdAt = integer(value.createdAt, 0, MAX_BYTES);
  const completedAt = nullableInteger(value.completedAt);
  const statusValue = String(value.status);
  if (
    !id ||
    !SAFE_OPERATION.test(id) ||
    !previewId ||
    !SAFE_PREVIEW.test(previewId) ||
    !parsedNode ||
    !parsedCategory ||
    !kind ||
    !["pending", "succeeded", "failed"].includes(statusValue) ||
    quarantineId === undefined ||
    errorCode === undefined ||
    affectedItemCount === null ||
    reclaimedBytes === null ||
    createdAt === null ||
    completedAt === undefined ||
    typeof value.replayed !== "boolean" ||
    typeof value.reconciled !== "boolean"
  ) {
    return null;
  }
  if (
    (kind === "cleanup" &&
      (parsedCategory === "project-quarantine" ||
        quarantineId !== null)) ||
    (kind !== "cleanup" &&
      (parsedCategory !== "project-quarantine" ||
        quarantineId === null)) ||
    (statusValue === "pending" &&
      (completedAt !== null ||
        affectedItemCount !== 0 ||
        reclaimedBytes !== 0)) ||
    (statusValue === "failed" &&
      (completedAt === null ||
        affectedItemCount !== 0 ||
        reclaimedBytes !== 0 ||
        errorCode === null)) ||
    (statusValue === "succeeded" &&
      (completedAt === null || errorCode !== null))
  ) {
    return null;
  }
  return {
    id,
    previewId,
    nodeId: parsedNode,
    category: parsedCategory,
    operationKind: kind,
    status: value.status as StorageOperation["status"],
    affectedItemCount,
    reclaimedBytes,
    quarantineId,
    errorCode,
    createdAt,
    completedAt,
    replayed: value.replayed,
    reconciled: value.reconciled,
  };
}

function parseAudit(value: unknown): StorageAuditEvent | null {
  if (!isRecord(value)) return null;
  const id = boundedText(value.id, 39);
  const parsedNode = nodeId(value.nodeId);
  const parsedCategory = category(value.category);
  const kind = operationKind(value.operationKind);
  const targetRef = boundedText(value.targetRef, 160);
  const previewId = boundedText(value.previewId, 36);
  const operationId = nullableSafe(
    value.operationId,
    SAFE_OPERATION,
    36,
  );
  const createdAt = integer(value.createdAt, 0, MAX_BYTES);
  if (
    !id ||
    !SAFE_AUDIT.test(id) ||
    ![
      "storage.preview.created",
      "storage.operation.succeeded",
      "storage.operation.failed",
    ].includes(String(value.action)) ||
    !parsedNode ||
    !parsedCategory ||
    !kind ||
    !targetRef ||
    !SAFE_PROJECT.test(targetRef) ||
    !previewId ||
    !SAFE_PREVIEW.test(previewId) ||
    operationId === undefined ||
    createdAt === null
  ) {
    return null;
  }
  return {
    id,
    action: value.action as StorageAuditEvent["action"],
    nodeId: parsedNode,
    category: parsedCategory,
    operationKind: kind,
    targetRef,
    previewId,
    operationId,
    createdAt,
  };
}

function parseSnapshot(value: unknown): StorageSnapshot {
  if (
    !isRecord(value) ||
    !Array.isArray(value.nodes) ||
    !Array.isArray(value.recentOperations) ||
    !Array.isArray(value.audit) ||
    value.nodes.length !== 2 ||
    value.recentOperations.length > 20 ||
    value.audit.length > 20
  ) {
    throw new Error("Хранилище вернуло некорректный ответ.");
  }
  const nodes = value.nodes.map(parseNode);
  const operations = value.recentOperations.map(parseOperation);
  const audit = value.audit.map(parseAudit);
  if (
    new Set(
      nodes.map((item) => item?.id),
    ).size !== 2 ||
    !nodes.some((item) => item?.id === "home") ||
    !nodes.some((item) => item?.id === "primary") ||
    nodes.some((item) => item === null) ||
    operations.some((item) => item === null) ||
    audit.some((item) => item === null)
  ) {
    throw new Error("Хранилище вернуло некорректный ответ.");
  }
  return {
    nodes: nodes as StorageNode[],
    recentOperations: operations as StorageOperation[],
    audit: audit as StorageAuditEvent[],
  };
}

async function storageRequest(
  path: string,
  init: RequestInit = {},
): Promise<unknown> {
  const response = await fetch(path, {
    ...init,
    headers:
      init.method && init.method !== "GET"
        ? withCsrfHeader({
            Accept: "application/json",
            "Content-Type": "application/json",
            ...init.headers,
          })
        : { Accept: "application/json", ...init.headers },
    credentials: "same-origin",
    cache: "no-store",
  });
  const declared = Number(response.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > MAX_RESPONSE_BYTES) {
    throw new Error("Ответ хранилища слишком большой.");
  }
  const text = await response.text();
  if (new TextEncoder().encode(text).byteLength > MAX_RESPONSE_BYTES) {
    throw new Error("Ответ хранилища слишком большой.");
  }
  let payload: unknown;
  try {
    payload = JSON.parse(text) as unknown;
  } catch {
    throw new Error("Хранилище вернуло некорректный ответ.");
  }
  if (!response.ok) {
    const rawCode = isRecord(payload)
      ? boundedText(payload.code, 128)
      : null;
    const rawMessage = isRecord(payload)
      ? boundedText(payload.message, 500)
      : null;
    const code =
      rawCode && SAFE_ERROR_CODE.test(rawCode)
        ? rawCode
        : "storage_request_failed";
    const message =
      rawMessage ?? "Операция хранилища не выполнена.";
    throw new StorageAdminRequestError(code, response.status, message);
  }
  return payload;
}

export function storageIdempotencyKey(
  scope: "preview" | "execute",
) {
  return `storage-${scope}:${crypto.randomUUID()}`;
}

export async function getStorageSnapshot(
  signal?: AbortSignal,
): Promise<StorageSnapshot> {
  return parseSnapshot(
    await storageRequest("/api/superadmin/storage", { signal }),
  );
}

export async function createStoragePreview(
  input: StoragePreviewInput,
  idempotencyKey: string,
): Promise<StoragePreview> {
  const value = await storageRequest(
    "/api/superadmin/storage/previews",
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(input),
    },
  );
  const parsed = parsePreview(value);
  if (!parsed) throw new Error("Preview хранилища имеет неверный формат.");
  return parsed;
}

export async function executeStoragePreview(
  previewId: string,
  confirmation: StorageConfirmation,
  idempotencyKey: string,
): Promise<StorageOperation> {
  if (!SAFE_PREVIEW.test(previewId)) {
    throw new Error("Некорректный preview ID.");
  }
  const value = await storageRequest(
    "/api/superadmin/storage/operations",
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ previewId, confirmation }),
    },
  );
  const parsed = parseOperation(value);
  if (!parsed) throw new Error("Результат очистки имеет неверный формат.");
  return parsed;
}

export async function reconcileStorageOperation(
  operationId: string,
): Promise<StorageOperation> {
  if (!SAFE_OPERATION.test(operationId)) {
    throw new Error("Некорректный operation ID.");
  }
  const value = await storageRequest(
    "/api/superadmin/storage/operations/reconcile",
    {
      method: "POST",
      body: JSON.stringify({ operationId }),
    },
  );
  const parsed = parseOperation(value);
  if (!parsed || parsed.id !== operationId || !parsed.reconciled) {
    throw new Error("Результат сверки имеет неверный формат.");
  }
  return parsed;
}
