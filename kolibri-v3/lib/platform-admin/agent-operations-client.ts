"use client";

import {
  boundedText,
  integer,
  isRecord,
  platformAdminRequest,
} from "@/lib/platform-admin/client";

const SAFE_OPERATION_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$/;
const SAFE_CURSOR = /^[A-Za-z0-9_-]{1,2048}$/;
const SAFE_VALUE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SAFE_TIMESTAMP = /^[0-9T:+Z. -]{1,64}$/;

export type AgentOperationContext = {
  executionMode: string;
  executionPlane: string;
  accessMode: string;
  accessPolicyVersion: number;
  authorityRole: string;
  workspaceRef: string | null;
  sandboxProfile: string;
  approvalPolicy: string;
  approvalsReviewer: string | null;
  modelId: string | null;
  modelIdRedacted: boolean;
  reasoningEffort: string | null;
  serviceTier: string | null;
  platformAuthorityEpoch: number | null;
  trustedAgentProfileId: string | null;
  trustedAgentProfileEpoch: number | null;
  trustedAgentWorkspaceBindingId: string | null;
  trustedAgentWorkspaceBindingEpoch: number | null;
  frozenAt: string;
};

export type AgentOperationDispatch = {
  commandKind: string;
  phase: string;
  state: string;
  attempts: number;
  maxAttempts: number;
  availableAt: string;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
  lastErrorCode: string | null;
  lastErrorRedacted: boolean;
};

export type AgentOperation = {
  task: {
    tenantId: string;
    runId: string;
    projectId: string;
    threadId: string;
  };
  agent: { selectedProfile: string };
  status: "running" | "succeeded" | "failed";
  outcome: "success" | "failure" | null;
  lastEventSequence: number;
  errorCode: string | null;
  errorRedacted: boolean;
  timestamps: {
    heartbeatAt: string;
    createdAt: string;
    updatedAt: string;
    finishedAt: string | null;
  };
  frozenPolicy: AgentOperationContext | null;
  dispatch: AgentOperationDispatch | null;
};

export type AgentRuntimeAvailability = {
  profileId: string;
  runtimeId: string;
  displayName: string;
  registered: true;
  startupStatus: "start_failed" | "no_error_recorded";
  modes: string[];
  streaming: boolean;
  structuredOutput: boolean;
  activityEvents: boolean;
  persistentSessions: boolean;
  modelCatalog: boolean;
};

export type AgentProviderAvailability = {
  tenantId: string;
  profileId: string;
  status: string;
  authFlowSupported: boolean;
  authorityObserved: boolean;
  lastVerifiedAt: string | null;
  lastErrorCode: string | null;
  lastErrorRedacted: boolean;
  updatedAt: string;
};

export type AgentOperationsPage = {
  items: AgentOperation[];
  nextCursor: string | null;
  availability: {
    providers: AgentProviderAvailability[];
    providersTruncated: boolean;
    runtimes: AgentRuntimeAvailability[];
    runtimesTruncated: boolean;
  };
};

const safeValue = (value: unknown, maximum = 128) => {
  const normalized = boundedText(value, maximum);
  return normalized && SAFE_VALUE.test(normalized) ? normalized : null;
};

const safeId = (value: unknown) => {
  const normalized = boundedText(value, 192);
  return normalized && SAFE_OPERATION_ID.test(normalized) ? normalized : null;
};

const timestamp = (value: unknown) => {
  const normalized = boundedText(value, 64);
  return normalized && SAFE_TIMESTAMP.test(normalized) ? normalized : null;
};

const nullableSafeValue = (value: unknown, maximum = 128) =>
  value === null ? null : safeValue(value, maximum);

const nullableTimestamp = (value: unknown) =>
  value === null ? null : timestamp(value);

function parseContext(value: unknown): AgentOperationContext | null {
  if (!isRecord(value)) return null;
  const executionMode = safeValue(value.executionMode);
  const executionPlane = safeValue(value.executionPlane);
  const accessMode = safeValue(value.accessMode);
  const authorityRole = safeValue(value.authorityRole);
  const sandboxProfile = safeValue(value.sandboxProfile);
  const approvalPolicy = safeValue(value.approvalPolicy);
  const workspaceRef = nullableSafeValue(value.workspaceRef);
  const approvalsReviewer = nullableSafeValue(value.approvalsReviewer);
  const modelId = nullableSafeValue(value.modelId, 120);
  const reasoningEffort = nullableSafeValue(value.reasoningEffort);
  const serviceTier = nullableSafeValue(value.serviceTier);
  const frozenAt = timestamp(value.frozenAt);
  const accessPolicyVersion = integer(
    value.accessPolicyVersion,
    1,
    Number.MAX_SAFE_INTEGER,
  );
  const platformAuthorityEpoch =
    value.platformAuthorityEpoch === null
      ? null
      : integer(value.platformAuthorityEpoch, 1, Number.MAX_SAFE_INTEGER);
  const trustedAgentProfileId =
    value.trustedAgentProfileId === null
      ? null
      : safeId(value.trustedAgentProfileId);
  const trustedAgentProfileEpoch =
    value.trustedAgentProfileEpoch === null
      ? null
      : integer(
          value.trustedAgentProfileEpoch,
          1,
          Number.MAX_SAFE_INTEGER,
        );
  const trustedAgentWorkspaceBindingId =
    value.trustedAgentWorkspaceBindingId === null
      ? null
      : safeId(value.trustedAgentWorkspaceBindingId);
  const trustedAgentWorkspaceBindingEpoch =
    value.trustedAgentWorkspaceBindingEpoch === null
      ? null
      : integer(
          value.trustedAgentWorkspaceBindingEpoch,
          1,
          Number.MAX_SAFE_INTEGER,
        );
  const trustedBindingValues = [
    trustedAgentProfileId,
    trustedAgentProfileEpoch,
    trustedAgentWorkspaceBindingId,
    trustedAgentWorkspaceBindingEpoch,
  ];
  if (
    !executionMode ||
    !executionPlane ||
    !accessMode ||
    !authorityRole ||
    !sandboxProfile ||
    !approvalPolicy ||
    workspaceRef === null !== (value.workspaceRef === null) ||
    approvalsReviewer === null !== (value.approvalsReviewer === null) ||
    modelId === null !== (value.modelId === null) ||
    reasoningEffort === null !== (value.reasoningEffort === null) ||
    serviceTier === null !== (value.serviceTier === null) ||
    !frozenAt ||
    accessPolicyVersion === null ||
    platformAuthorityEpoch === null !==
      (value.platformAuthorityEpoch === null) ||
    trustedAgentProfileId === null !==
      (value.trustedAgentProfileId === null) ||
    trustedAgentProfileEpoch === null !==
      (value.trustedAgentProfileEpoch === null) ||
    trustedAgentWorkspaceBindingId === null !==
      (value.trustedAgentWorkspaceBindingId === null) ||
    trustedAgentWorkspaceBindingEpoch === null !==
      (value.trustedAgentWorkspaceBindingEpoch === null) ||
    !(
      trustedBindingValues.every((item) => item === null) ||
      trustedBindingValues.every((item) => item !== null)
    ) ||
    typeof value.modelIdRedacted !== "boolean"
  ) {
    return null;
  }
  return {
    executionMode,
    executionPlane,
    accessMode,
    accessPolicyVersion,
    authorityRole,
    workspaceRef,
    sandboxProfile,
    approvalPolicy,
    approvalsReviewer,
    modelId,
    modelIdRedacted: value.modelIdRedacted,
    reasoningEffort,
    serviceTier,
    platformAuthorityEpoch,
    trustedAgentProfileId,
    trustedAgentProfileEpoch,
    trustedAgentWorkspaceBindingId,
    trustedAgentWorkspaceBindingEpoch,
    frozenAt,
  };
}

function parseDispatch(value: unknown): AgentOperationDispatch | null {
  if (!isRecord(value)) return null;
  const commandKind = safeValue(value.commandKind);
  const phase = safeValue(value.phase);
  const state = safeValue(value.state);
  const availableAt = timestamp(value.availableAt);
  const createdAt = timestamp(value.createdAt);
  const updatedAt = timestamp(value.updatedAt);
  const completedAt = nullableTimestamp(value.completedAt);
  const lastErrorCode = nullableSafeValue(value.lastErrorCode);
  const attempts = integer(value.attempts, 0, 1_000_000);
  const maxAttempts = integer(value.maxAttempts, 1, 1_000_000);
  if (
    !commandKind ||
    !phase ||
    !state ||
    !availableAt ||
    !createdAt ||
    !updatedAt ||
    completedAt === null !== (value.completedAt === null) ||
    lastErrorCode === null !== (value.lastErrorCode === null) ||
    attempts === null ||
    maxAttempts === null ||
    typeof value.lastErrorRedacted !== "boolean"
  ) {
    return null;
  }
  return {
    commandKind,
    phase,
    state,
    attempts,
    maxAttempts,
    availableAt,
    createdAt,
    updatedAt,
    completedAt,
    lastErrorCode,
    lastErrorRedacted: value.lastErrorRedacted,
  };
}

function parseOperation(value: unknown): AgentOperation | null {
  if (
    !isRecord(value) ||
    !isRecord(value.task) ||
    !isRecord(value.agent) ||
    !isRecord(value.timestamps)
  ) {
    return null;
  }
  const tenantId = safeId(value.task.tenantId);
  const runId = safeId(value.task.runId);
  const projectId = safeId(value.task.projectId);
  const threadId = safeId(value.task.threadId);
  const selectedProfile = safeValue(value.agent.selectedProfile);
  const heartbeatAt = timestamp(value.timestamps.heartbeatAt);
  const createdAt = timestamp(value.timestamps.createdAt);
  const updatedAt = timestamp(value.timestamps.updatedAt);
  const finishedAt = nullableTimestamp(value.timestamps.finishedAt);
  const errorCode = nullableSafeValue(value.errorCode);
  const frozenPolicy =
    value.frozenPolicy === null ? null : parseContext(value.frozenPolicy);
  const dispatch =
    value.dispatch === null ? null : parseDispatch(value.dispatch);
  const lastEventSequence = integer(
    value.lastEventSequence,
    0,
    Number.MAX_SAFE_INTEGER,
  );
  if (
    !tenantId ||
    !runId ||
    !projectId ||
    !threadId ||
    !selectedProfile ||
    !heartbeatAt ||
    !createdAt ||
    !updatedAt ||
    finishedAt === null !== (value.timestamps.finishedAt === null) ||
    errorCode === null !== (value.errorCode === null) ||
    frozenPolicy === null !== (value.frozenPolicy === null) ||
    dispatch === null !== (value.dispatch === null) ||
    !["running", "succeeded", "failed"].includes(String(value.status)) ||
    ![null, "success", "failure"].includes(
      value.outcome as null | string,
    ) ||
    lastEventSequence === null ||
    typeof value.errorRedacted !== "boolean"
  ) {
    return null;
  }
  return {
    task: { tenantId, runId, projectId, threadId },
    agent: { selectedProfile },
    status: value.status as AgentOperation["status"],
    outcome: value.outcome as AgentOperation["outcome"],
    lastEventSequence,
    errorCode,
    errorRedacted: value.errorRedacted,
    timestamps: { heartbeatAt, createdAt, updatedAt, finishedAt },
    frozenPolicy,
    dispatch,
  };
}

function parseRuntime(value: unknown): AgentRuntimeAvailability | null {
  if (!isRecord(value) || !Array.isArray(value.modes)) return null;
  const profileId = safeValue(value.profileId);
  const runtimeId = safeValue(value.runtimeId);
  const displayName = boundedText(value.displayName, 160);
  const modes = value.modes.map((mode) => safeValue(mode)).filter(Boolean);
  if (
    !profileId ||
    !runtimeId ||
    !displayName ||
    modes.length !== value.modes.length ||
    modes.length > 16 ||
    value.registered !== true ||
    !["start_failed", "no_error_recorded"].includes(
      String(value.startupStatus),
    ) ||
    [
      value.streaming,
      value.structuredOutput,
      value.activityEvents,
      value.persistentSessions,
      value.modelCatalog,
    ].some((flag) => typeof flag !== "boolean")
  ) {
    return null;
  }
  return {
    profileId,
    runtimeId,
    displayName,
    registered: true,
    startupStatus:
      value.startupStatus as AgentRuntimeAvailability["startupStatus"],
    modes: modes as string[],
    streaming: value.streaming as boolean,
    structuredOutput: value.structuredOutput as boolean,
    activityEvents: value.activityEvents as boolean,
    persistentSessions: value.persistentSessions as boolean,
    modelCatalog: value.modelCatalog as boolean,
  };
}

function parseProvider(value: unknown): AgentProviderAvailability | null {
  if (!isRecord(value)) return null;
  const tenantId = safeId(value.tenantId);
  const profileId = safeValue(value.profileId);
  const providerStatus = safeValue(value.status);
  const lastVerifiedAt = nullableTimestamp(value.lastVerifiedAt);
  const lastErrorCode = nullableSafeValue(value.lastErrorCode);
  const updatedAt = timestamp(value.updatedAt);
  if (
    !tenantId ||
    !profileId ||
    !providerStatus ||
    lastVerifiedAt === null !== (value.lastVerifiedAt === null) ||
    lastErrorCode === null !== (value.lastErrorCode === null) ||
    !updatedAt ||
    typeof value.authFlowSupported !== "boolean" ||
    typeof value.authorityObserved !== "boolean" ||
    typeof value.lastErrorRedacted !== "boolean"
  ) {
    return null;
  }
  return {
    tenantId,
    profileId,
    status: providerStatus,
    authFlowSupported: value.authFlowSupported,
    authorityObserved: value.authorityObserved,
    lastVerifiedAt,
    lastErrorCode,
    lastErrorRedacted: value.lastErrorRedacted,
    updatedAt,
  };
}

function parsePage(value: unknown): AgentOperationsPage {
  if (
    !isRecord(value) ||
    !Array.isArray(value.items) ||
    !isRecord(value.availability) ||
    !Array.isArray(value.availability.providers) ||
    !Array.isArray(value.availability.runtimes)
  ) {
    throw new Error("Контур агентов вернул некорректный ответ.");
  }
  const items = value.items.slice(0, 100).map(parseOperation);
  const providers = value.availability.providers.slice(0, 100).map(parseProvider);
  const runtimes = value.availability.runtimes.slice(0, 64).map(parseRuntime);
  const nextCursor =
    value.nextCursor === null ? null : boundedText(value.nextCursor, 2048);
  if (
    items.some((item) => item === null) ||
    providers.some((item) => item === null) ||
    runtimes.some((item) => item === null) ||
    (nextCursor !== null && !SAFE_CURSOR.test(nextCursor)) ||
    typeof value.availability.providersTruncated !== "boolean" ||
    typeof value.availability.runtimesTruncated !== "boolean"
  ) {
    throw new Error("Контур агентов вернул некорректный ответ.");
  }
  return {
    items: items as AgentOperation[],
    nextCursor,
    availability: {
      providers: providers as AgentProviderAvailability[],
      providersTruncated: value.availability.providersTruncated,
      runtimes: runtimes as AgentRuntimeAvailability[],
      runtimesTruncated: value.availability.runtimesTruncated,
    },
  };
}

export async function getAgentOperationsPage(
  cursor?: string,
  signal?: AbortSignal,
): Promise<AgentOperationsPage> {
  if (cursor && !SAFE_CURSOR.test(cursor)) {
    throw new Error("Некорректный cursor операций.");
  }
  const parameters = new URLSearchParams({ limit: "50" });
  if (cursor) parameters.set("cursor", cursor);
  return parsePage(
    await platformAdminRequest(
      `/api/superadmin/agent-operations?${parameters.toString()}`,
      { signal },
    ),
  );
}
