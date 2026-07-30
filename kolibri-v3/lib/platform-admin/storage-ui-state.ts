export type StorageActionLocks = {
  busy: boolean;
  loading: boolean;
  snapshotStale: boolean;
  hasActivePreview: boolean;
};

export type StoragePreviewTargetInput = {
  category: string;
  projectId: string | null;
  quarantineId: string | null;
};

export type StoragePreviewConfirmationInput = {
  candidateCount: number;
  confirmation: string;
  expiresAt: number;
};

export const storageAdminActionsLocked = ({
  busy,
  loading,
  snapshotStale,
  hasActivePreview,
}: StorageActionLocks) =>
  busy || loading || snapshotStale || hasActivePreview;

export const storageNodeAllowsActions = (node: {
  executorStatus: string;
  executeEnabled: boolean;
}) => node.executorStatus === "ready" && node.executeEnabled;

export const storagePreviewTarget = (
  preview: StoragePreviewTargetInput,
  nodes: ReadonlyArray<{
    quarantines: ReadonlyArray<{
      id: string;
      projectId: string;
    }>;
  }>,
) =>
  preview.projectId ??
  nodes
    .flatMap((node) => node.quarantines)
    .find((item) => item.id === preview.quarantineId)?.projectId ??
  preview.quarantineId ??
  preview.category;

export const storageConfirmationReady = (
  preview: StoragePreviewConfirmationInput,
  confirmation: string,
  nowSeconds: number,
  pendingRetry = false,
) =>
  confirmation === preview.confirmation &&
  (pendingRetry ||
    (preview.candidateCount > 0 && preview.expiresAt >= nowSeconds));

export const storageOperationDisposition = (
  status: "pending" | "succeeded" | "failed",
) => {
  if (status === "succeeded") {
    return {
      alert: "success",
      dismissPreview: true,
    } as const;
  }
  if (status === "failed") {
    return {
      alert: "failed",
      dismissPreview: true,
    } as const;
  }
  return {
    alert: "pending",
    dismissPreview: false,
  } as const;
};

export const storageExecutionFailureIsAmbiguous = (
  responseStatus: number | null,
) =>
  responseStatus === null ||
  responseStatus === 408 ||
  responseStatus >= 500;
