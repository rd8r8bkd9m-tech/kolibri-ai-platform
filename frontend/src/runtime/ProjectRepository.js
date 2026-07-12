import { createProject } from "../app/utils";
import { publicProjectsApi } from "./kolibriApi";

const MESSAGE_STATUSES = new Set([
  "pending",
  "running",
  "completed",
  "failed",
  "incomplete",
  "cancelled",
]);

function text(value) {
  return typeof value === "string" ? value.trim() : "";
}

function isoTimestamp(value, fallback = new Date().toISOString()) {
  const milliseconds = Number(value) * 1000;
  return Number.isFinite(milliseconds) && milliseconds > 0
    ? new Date(milliseconds).toISOString()
    : fallback;
}

function localTimestamp(value) {
  const milliseconds = Date.parse(String(value || ""));
  return Number.isFinite(milliseconds) ? milliseconds : 0;
}

function remoteTimestamp(value) {
  const milliseconds = Number(value) * 1000;
  return Number.isFinite(milliseconds) ? milliseconds : 0;
}

function messageStatus(value) {
  return MESSAGE_STATUSES.has(value) ? value : "completed";
}

function clientId(metadata) {
  return text(metadata?.shell_client_id);
}

function messageKey(projectId, messageId) {
  return `${projectId}:${messageId}`;
}

function errorCode(error) {
  const candidates = [
    error?.payload?.detail?.code,
    error?.payload?.error?.code,
    error?.payload?.code,
    typeof error?.payload?.detail === "string" ? error.payload.detail : "",
    error?.message,
  ];
  return text(candidates.find((value) => typeof value === "string" && value)).toLowerCase();
}

function publicProjectEndpoint(error) {
  const endpoint = text(error?.endpoint);
  if (!endpoint) return false;
  let pathname;
  try {
    pathname = new URL(endpoint, "https://kolibri.invalid").pathname;
  } catch {
    return false;
  }
  return /^\/v1\/projects\/project_ephemeral_[A-Za-z0-9._:-]+(?:\/(?:messages(?:\/message_[A-Za-z0-9._:-]+)?|delete|restore))?$/.test(pathname);
}

function projectOwnershipMissing(error) {
  const status = Number(error?.status);
  const code = errorCode(error);
  if (status === 404) {
    return code === "project_not_found"
      || code === "project_not_found_in_session"
      || publicProjectEndpoint(error);
  }
  if (status !== 403) return false;
  return new Set([
    "project_not_found_in_session",
    "public_session_project_not_owned",
    "public_session_project_forbidden",
  ]).has(code);
}

export function projectMetadata(project, existing = {}) {
  return {
    ...(existing && typeof existing === "object" ? existing : {}),
    shell_client_id: project.id,
    view_mode: project.viewMode || "dialog",
    execution_mode: project.executionMode || "fast",
    draft_tool: project.draftTool || "",
  };
}

export function messageMetadata(message, existing = {}) {
  return {
    ...(existing && typeof existing === "object" ? existing : {}),
    shell_client_id: message.id,
    ...(message.canvasId ? { canvas_id: message.canvasId } : {}),
    ...(message.recoverable === true ? { shell_recoverable: true } : {}),
    ...(message.excludeFromContext === true ? { exclude_from_context: true } : {}),
  };
}

export function mergeRemoteMessage(localMessage, remoteMessage) {
  const local = localMessage || {};
  const {
    responseId: localResponseId,
    recoverable: localRecoverable,
    excludeFromContext: localExcludeFromContext,
    ...localWithoutBindings
  } = local;
  const remoteDefinesResponseId = Object.prototype.hasOwnProperty.call(remoteMessage || {}, "response_id");
  const metadata = remoteMessage?.metadata && typeof remoteMessage.metadata === "object"
    ? remoteMessage.metadata
    : {};
  const shellOwnedMetadata = Boolean(clientId(metadata));
  return {
    ...localWithoutBindings,
    id: local.id || clientId(remoteMessage?.metadata) || remoteMessage.id,
    remoteId: remoteMessage.id,
    role: remoteMessage.role,
    text: remoteMessage.content,
    status: messageStatus(remoteMessage.message_status || remoteMessage.status),
    ...(remoteDefinesResponseId
      ? (remoteMessage.response_id ? { responseId: remoteMessage.response_id } : {})
      : (localResponseId ? { responseId: localResponseId } : {})),
    ...(shellOwnedMetadata
      ? {
          recoverable: metadata.shell_recoverable === true,
          excludeFromContext: metadata.exclude_from_context === true,
        }
      : {
          ...(localRecoverable === undefined ? {} : { recoverable: localRecoverable }),
          ...(localExcludeFromContext === undefined
            ? {}
            : { excludeFromContext: localExcludeFromContext }),
        }),
    createdAt: local.createdAt || isoTimestamp(remoteMessage.created_at),
    updatedAt: isoTimestamp(remoteMessage.updated_at, local.updatedAt || local.createdAt),
  };
}

export function mergeRemoteProject(localProject, remoteProject, messages = null) {
  const local = localProject || createProject(remoteProject.title || "Новый проект");
  const metadata = remoteProject?.metadata && typeof remoteProject.metadata === "object"
    ? remoteProject.metadata
    : {};
  return {
    ...local,
    id: local.id || clientId(metadata) || createProject().id,
    remoteId: remoteProject.id,
    title: remoteProject.title || local.title,
    viewMode: text(metadata.view_mode) || local.viewMode || "dialog",
    executionMode: text(metadata.execution_mode) || local.executionMode || "fast",
    draftTool: text(metadata.draft_tool) || local.draftTool || "",
    ...(messages ? { messages } : {}),
    createdAt: local.createdAt || isoTimestamp(remoteProject.created_at),
    updatedAt: isoTimestamp(remoteProject.updated_at, local.updatedAt || local.createdAt),
  };
}

function localProjectForRemote(remoteProject, usedIds) {
  const requestedId = clientId(remoteProject.metadata);
  const shellProject = createProject(remoteProject.title || "Новый проект");
  if (requestedId && !usedIds.has(requestedId)) shellProject.id = requestedId;
  return mergeRemoteProject(shellProject, remoteProject);
}

function localMessageForRemote(remoteMessage, usedIds) {
  const requestedId = clientId(remoteMessage.metadata);
  const id = requestedId && !usedIds.has(requestedId) ? requestedId : remoteMessage.id;
  return mergeRemoteMessage({ id }, remoteMessage);
}

/**
 * Session-scoped project persistence. localStorage remains a recoverable UI
 * cache; this repository is the authoritative synchronization boundary to the
 * public project/message CRUD API.
 */
export class ProjectRepository {
  constructor(api = publicProjectsApi) {
    this.api = api;
    this.projectBindings = new Map();
    this.messageBindings = new Map();
    this.pendingProjects = new Map();
    this.pendingRebinds = new Map();
    this.projectMutations = new Map();
    this.rebindQueue = Promise.resolve();
    this.hydrationPromise = null;
    this.hydratingProjectIds = new Set();
  }

  remoteProjectId(project) {
    return this.projectBindings.get(project?.id) || text(project?.remoteId);
  }

  bindProject(project, remoteProject) {
    if (project?.id && remoteProject?.id) this.projectBindings.set(project.id, remoteProject.id);
    return mergeRemoteProject(project, remoteProject);
  }

  bindMessage(projectId, message, remoteMessage) {
    if (projectId && message?.id && remoteMessage?.id) {
      this.messageBindings.set(messageKey(projectId, message.id), remoteMessage.id);
    }
    return mergeRemoteMessage(message, remoteMessage);
  }

  async ensureProject(project, signal, { waitForHydration = true } = {}) {
    if (!project?.id) throw new Error("Проект не найден в локальном кеше.");
    if (waitForHydration && this.hydrationPromise && this.hydratingProjectIds.has(project.id)) {
      const hydrated = await this.hydrationPromise;
      const synchronized = hydrated.find((item) => item.id === project.id);
      if (synchronized?.remoteId) return synchronized;
    }
    const boundId = this.remoteProjectId(project);
    if (boundId) {
      this.projectBindings.set(project.id, boundId);
      return { ...project, remoteId: boundId };
    }
    if (this.pendingProjects.has(project.id)) return this.pendingProjects.get(project.id);

    const pending = this.api.create({
      title: project.title || "Новый проект",
      metadata: projectMetadata(project),
      idempotencyKey: `shell-project-${project.id}`,
    }, signal).then((remoteProject) => this.bindProject(project, remoteProject));
    this.pendingProjects.set(project.id, pending);
    try {
      return await pending;
    } finally {
      this.pendingProjects.delete(project.id);
    }
  }

  enqueueProjectMutation(projectId, operation) {
    const previous = this.projectMutations.get(projectId) || Promise.resolve();
    const current = previous.catch(() => {}).then(operation);
    this.projectMutations.set(projectId, current);
    current.finally(() => {
      if (this.projectMutations.get(projectId) === current) this.projectMutations.delete(projectId);
    }).catch(() => {});
    return current;
  }

  async migrateProjectMessages(project, reboundProject, signal) {
    const localMessages = Array.isArray(project.messages) ? project.messages : [];
    if (!localMessages.some((message) => text(message?.text))) return reboundProject;

    const remoteMessages = await this.api.listMessages(reboundProject.remoteId, signal);
    const claimedRemoteIds = new Set();
    const migrated = [];
    for (const localMessage of localMessages) {
      if (!text(localMessage?.text)) {
        migrated.push(localMessage);
        continue;
      }
      const match = remoteMessages.find((remoteMessage) => (
        !claimedRemoteIds.has(remoteMessage.id)
        && (
          clientId(remoteMessage.metadata) === localMessage.id
          || (
            remoteMessage.role === localMessage.role
            && remoteMessage.content === localMessage.text
          )
        )
      ));
      let remoteMessage = match;
      if (!remoteMessage) {
        remoteMessage = await this.api.createMessage(reboundProject.remoteId, {
          role: localMessage.role,
          content: localMessage.text,
          status: messageStatus(localMessage.status),
          // Response IDs are scoped to the expired browser session and must
          // never be copied into its replacement. The dialogue itself remains
          // intact and the next response receives a fresh binding.
          responseId: null,
          metadata: messageMetadata(localMessage),
          idempotencyKey: `shell-message-${localMessage.id}`,
        }, signal);
      }
      claimedRemoteIds.add(remoteMessage.id);
      migrated.push(this.bindMessage(project.id, localMessage, remoteMessage));
    }
    return { ...reboundProject, messages: migrated };
  }

  async rebindProject(project, signal, { failedRemoteId = "" } = {}) {
    if (!project?.id) throw new Error("Проект не найден в локальном кеше.");
    if (signal?.aborted) throw signal.reason || new Error("Синхронизация проекта отменена.");
    const currentRemoteId = this.remoteProjectId(project);
    if (failedRemoteId && currentRemoteId && currentRemoteId !== failedRemoteId) {
      return { ...project, remoteId: currentRemoteId };
    }
    if (this.pendingRebinds.has(project.id)) return this.pendingRebinds.get(project.id);

    const operation = this.rebindQueue.catch(() => {}).then(async () => {
      const latestRemoteId = this.remoteProjectId(project);
      if (failedRemoteId && latestRemoteId && latestRemoteId !== failedRemoteId) {
        return { ...project, remoteId: latestRemoteId };
      }
      this.projectBindings.delete(project.id);
      // Reconciliation is shared by concurrent sends for the same project.
      // Do not bind the shared repair to one caller's AbortSignal: cancelling
      // one request must not poison another request waiting on the same rebind.
      const remoteProjects = await this.api.list();
      const linked = remoteProjects.find((remoteProject) => clientId(remoteProject.metadata) === project.id);
      const emptyDefault = remoteProjects.find((remoteProject) => (
        remoteProject.status !== "deleted"
        && remoteProject.metadata?.source === "public_session"
        && !clientId(remoteProject.metadata)
        && Number(remoteProject.message_count || 0) === 0
      ));
      let rebound;
      if (linked) {
        rebound = this.bindProject(project, linked);
      } else if (emptyDefault) {
        const adopted = await this.api.update(emptyDefault.id, {
          title: project.title || "Новый проект",
          metadata: projectMetadata(project, emptyDefault.metadata),
        });
        rebound = this.bindProject(project, adopted);
      } else {
        rebound = await this.ensureProject({ ...project, remoteId: "" });
      }
      return this.migrateProjectMessages(project, rebound);
    });
    this.rebindQueue = operation.catch(() => {});
    this.pendingRebinds.set(project.id, operation);
    try {
      return await operation;
    } finally {
      if (this.pendingRebinds.get(project.id) === operation) this.pendingRebinds.delete(project.id);
    }
  }

  reconcileProject(project, { failedRemoteId = "", signal } = {}) {
    return this.rebindProject(project, signal, { failedRemoteId });
  }

  async updateProject(project, signal) {
    return this.enqueueProjectMutation(project.id, async () => {
      const bound = await this.ensureProject(project, signal);
      try {
        const remoteProject = await this.api.update(bound.remoteId, {
          title: project.title || "Новый проект",
          metadata: projectMetadata(project),
        }, signal);
        return this.bindProject(project, remoteProject);
      } catch (error) {
        if (!projectOwnershipMissing(error)) throw error;
        return this.rebindProject(project, signal, { failedRemoteId: bound.remoteId });
      }
    });
  }

  async removeProject(project, { operationId = "", signal } = {}) {
    return this.enqueueProjectMutation(project.id, async () => {
      const bound = await this.ensureProject(project, signal);
      try {
        return await this.api.remove(bound.remoteId, operationId, signal);
      } catch (error) {
        if (Number(error?.status) === 404) return { ...bound, status: "deleted" };
        throw error;
      }
    });
  }

  async restoreProject(project, { operationId = "", signal } = {}) {
    return this.enqueueProjectMutation(project.id, async () => {
      const remoteId = this.remoteProjectId(project);
      if (!remoteId) return this.rebindProject(project, signal);
      try {
        const remoteProject = await this.api.restore(remoteId, operationId, signal);
        return this.bindProject(project, remoteProject);
      } catch (error) {
        if (!projectOwnershipMissing(error)) throw error;
        return this.rebindProject(project, signal, { failedRemoteId: remoteId });
      }
    });
  }

  async syncMessage(project, message, {
    responseId = message?.responseId,
    signal,
    waitForHydration = true,
  } = {}) {
    if (!text(message?.text)) return message;
    const boundProject = await this.ensureProject(project, signal, { waitForHydration });
    const bindingKey = messageKey(project.id, message.id);
    const remoteMessageId = this.messageBindings.get(bindingKey) || text(message.remoteId);
    const payload = {
      content: message.text,
      status: messageStatus(message.status),
      responseId: responseId || null,
      metadata: messageMetadata(message),
    };
    let remoteMessage;
    if (remoteMessageId) {
      try {
        remoteMessage = await this.api.updateMessage(
          boundProject.remoteId,
          remoteMessageId,
          payload,
          signal,
        );
      } catch (error) {
        if (Number(error?.status) !== 404) throw error;
        this.messageBindings.delete(bindingKey);
      }
    }
    if (!remoteMessage) {
      try {
        remoteMessage = await this.api.createMessage(boundProject.remoteId, {
          role: message.role,
          ...payload,
          idempotencyKey: `shell-message-${message.id}`,
        }, signal);
      } catch (error) {
        if (Number(error?.status) !== 404) throw error;
        let recoveredProject;
        if (projectOwnershipMissing(error)) {
          recoveredProject = await this.rebindProject(project, signal, {
            failedRemoteId: boundProject.remoteId,
          });
        } else {
          try {
            await this.api.get(boundProject.remoteId, signal);
            recoveredProject = boundProject;
          } catch (projectError) {
            if (!projectOwnershipMissing(projectError)) throw projectError;
            recoveredProject = await this.rebindProject(project, signal, {
              failedRemoteId: boundProject.remoteId,
            });
          }
        }
        remoteMessage = await this.api.createMessage(recoveredProject.remoteId, {
          role: message.role,
          ...payload,
          responseId: null,
          idempotencyKey: `shell-message-${message.id}`,
        }, signal);
      }
    }
    return this.bindMessage(project.id, message, remoteMessage);
  }

  async mergeMessages(project, remoteMessages, signal, { waitForHydration = true } = {}) {
    const localMessages = Array.isArray(project.messages) ? project.messages : [];
    const usedLocalIds = new Set(localMessages.map((message) => message.id));
    const claimedRemoteIds = new Set();
    const merged = [];

    for (const localMessage of localMessages) {
      const boundId = this.messageBindings.get(messageKey(project.id, localMessage.id))
        || text(localMessage.remoteId);
      const match = remoteMessages.find((remoteMessage) => (
        !claimedRemoteIds.has(remoteMessage.id)
        && (
          remoteMessage.id === boundId
          || clientId(remoteMessage.metadata) === localMessage.id
          || (
            !boundId
            && remoteMessage.role === localMessage.role
            && remoteMessage.content === localMessage.text
          )
        )
      ));
      if (!match) {
        merged.push(localMessage);
        continue;
      }
      claimedRemoteIds.add(match.id);
      this.messageBindings.set(messageKey(project.id, localMessage.id), match.id);
      const localIsNewer = localTimestamp(localMessage.updatedAt) > remoteTimestamp(match.updated_at) + 1_500;
      merged.push(localIsNewer
        ? await this.syncMessage(project, { ...localMessage, remoteId: match.id }, {
            signal,
            waitForHydration,
          })
        : mergeRemoteMessage(localMessage, match));
    }

    for (const remoteMessage of remoteMessages) {
      if (claimedRemoteIds.has(remoteMessage.id)) continue;
      const localMessage = localMessageForRemote(remoteMessage, usedLocalIds);
      usedLocalIds.add(localMessage.id);
      this.messageBindings.set(messageKey(project.id, localMessage.id), remoteMessage.id);
      merged.push(localMessage);
    }

    const synchronized = [];
    for (const localMessage of merged) {
      const remoteId = this.messageBindings.get(messageKey(project.id, localMessage.id))
        || text(localMessage.remoteId);
      if (remoteId || !text(localMessage.text)) {
        synchronized.push(remoteId ? { ...localMessage, remoteId } : localMessage);
        continue;
      }
      synchronized.push(await this.syncMessage(project, localMessage, {
        signal,
        waitForHydration,
      }));
    }
    return synchronized;
  }

  async hydrateProjects(localProjects, signal) {
    this.projectBindings.clear();
    this.messageBindings.clear();
    const local = (Array.isArray(localProjects) ? localProjects : []).map((project) => ({ ...project }));
    const remote = await this.api.list(signal);
    const claimedRemoteIds = new Set();
    const usedLocalIds = new Set(local.map((project) => project.id));

    for (let index = 0; index < local.length; index += 1) {
      const project = local[index];
      const match = remote.find((remoteProject) => (
        !claimedRemoteIds.has(remoteProject.id)
        && (
          remoteProject.id === text(project.remoteId)
          || clientId(remoteProject.metadata) === project.id
        )
      ));
      if (!match) continue;
      claimedRemoteIds.add(match.id);
      this.projectBindings.set(project.id, match.id);
      const localIsNewer = localTimestamp(project.updatedAt) > remoteTimestamp(match.updated_at) + 1_500;
      if (localIsNewer) {
        const updated = await this.api.update(match.id, {
          title: project.title || "Новый проект",
          metadata: projectMetadata(project, match.metadata),
        }, signal);
        local[index] = this.bindProject(project, updated);
      } else {
        local[index] = this.bindProject(project, match);
      }
    }

    const defaultRemote = remote.find((remoteProject) => (
      !claimedRemoteIds.has(remoteProject.id)
      && remoteProject.metadata?.source === "public_session"
      && !clientId(remoteProject.metadata)
      && Number(remoteProject.message_count || 0) === 0
      && remoteProject.status !== "deleted"
    ));
    const unboundIndex = local.findIndex((project) => !this.projectBindings.has(project.id));
    if (defaultRemote && unboundIndex >= 0) {
      const project = local[unboundIndex];
      const adopted = await this.api.update(defaultRemote.id, {
        title: project.title || "Новый проект",
        metadata: projectMetadata(project, defaultRemote.metadata),
      }, signal);
      claimedRemoteIds.add(defaultRemote.id);
      local[unboundIndex] = this.bindProject(project, adopted);
    }

    for (const remoteProject of remote) {
      if (claimedRemoteIds.has(remoteProject.id)) continue;
      if (
        remoteProject.metadata?.source === "public_session"
        && !clientId(remoteProject.metadata)
        && Number(remoteProject.message_count || 0) === 0
      ) continue;
      let project = localProjectForRemote(remoteProject, usedLocalIds);
      usedLocalIds.add(project.id);
      if (clientId(remoteProject.metadata) !== project.id) {
        const updated = await this.api.update(remoteProject.id, {
          metadata: projectMetadata(project, remoteProject.metadata),
        }, signal);
        project = this.bindProject(project, updated);
      } else {
        project = this.bindProject(project, remoteProject);
      }
      local.push(project);
    }

    for (let index = 0; index < local.length; index += 1) {
      let project = local[index];
      if (!this.projectBindings.has(project.id)) {
        project = await this.ensureProject(project, signal, { waitForHydration: false });
      }
      const remoteId = this.remoteProjectId(project);
      const remoteMessages = await this.api.listMessages(remoteId, signal);
      const messages = await this.mergeMessages(project, remoteMessages, signal, {
        waitForHydration: false,
      });
      local[index] = { ...project, remoteId, messages };
    }

    return local;
  }

  hydrate(localProjects, signal) {
    if (this.hydrationPromise) return this.hydrationPromise;
    this.hydratingProjectIds = new Set(
      (Array.isArray(localProjects) ? localProjects : [])
        .map((project) => project?.id)
        .filter(Boolean),
    );
    const operation = this.hydrateProjects(localProjects, signal);
    const tracked = operation.finally(() => {
      if (this.hydrationPromise === tracked) {
        this.hydrationPromise = null;
        this.hydratingProjectIds.clear();
      }
    });
    this.hydrationPromise = tracked;
    return tracked;
  }
}

export const projectRepository = new ProjectRepository();
