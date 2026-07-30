import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const vite = await createServer({
  root: fileURLToPath(new URL("..", import.meta.url)),
  server: { middlewareMode: true },
  appType: "custom",
  logLevel: "silent",
});
const {
  ProjectRepository,
  mergeRemoteMessage,
  messageMetadata,
  projectMetadata,
} = await vite.ssrLoadModule("/src/runtime/ProjectRepository.js");
await vite.close();

const now = 2_000_000_000;
const calls = [];
let projectSequence = 1;
let messageSequence = 1;
let projects = [{
  id: "project_ephemeral_default",
  object: "project.ephemeral",
  title: "New project",
  status: "active",
  metadata: { source: "public_session" },
  message_count: 0,
  created_at: now,
  updated_at: now,
}];
const messages = new Map([["project_ephemeral_default", []]]);

function notFound() {
  const error = new Error("project_not_found");
  error.status = 404;
  return error;
}

function endpointNotFound(endpoint) {
  const error = new Error("Not Found");
  error.status = 404;
  error.endpoint = endpoint;
  error.payload = { detail: "Not Found" };
  return error;
}

function clone(value) {
  return structuredClone(value);
}

const api = {
  async list() {
    calls.push(["list"]);
    return clone(projects.filter((project) => project.status !== "deleted"));
  },
  async get(projectId) {
    calls.push(["get", projectId]);
    const project = projects.find((item) => item.id === projectId && item.status !== "deleted");
    if (!project) throw notFound();
    return clone(project);
  },
  async create({ title, metadata, idempotencyKey }) {
    const project = {
      id: `project_ephemeral_created_${projectSequence++}`,
      object: "project.ephemeral",
      title,
      status: "active",
      metadata,
      message_count: 0,
      created_at: now,
      updated_at: now,
    };
    calls.push(["create", project.id, idempotencyKey]);
    projects.push(project);
    messages.set(project.id, []);
    return clone(project);
  },
  async update(projectId, patch) {
    calls.push(["update", projectId, clone(patch)]);
    const index = projects.findIndex((project) => project.id === projectId && project.status !== "deleted");
    if (index < 0) throw notFound();
    projects[index] = {
      ...projects[index],
      ...(patch.title === undefined ? {} : { title: patch.title }),
      ...(patch.metadata === undefined ? {} : { metadata: patch.metadata }),
      updated_at: now + calls.length,
    };
    return clone(projects[index]);
  },
  async remove(projectId, operationId) {
    calls.push(["remove", projectId, operationId]);
    const project = projects.find((item) => item.id === projectId);
    if (!project) throw notFound();
    project.status = "deleted";
    return clone(project);
  },
  async restore(projectId, operationId) {
    calls.push(["restore", projectId, operationId]);
    const project = projects.find((item) => item.id === projectId);
    if (!project) throw notFound();
    project.status = "active";
    return clone(project);
  },
  async listMessages(projectId) {
    calls.push(["listMessages", projectId]);
    if (!messages.has(projectId)) throw notFound();
    return clone(messages.get(projectId));
  },
  async createMessage(projectId, payload) {
    calls.push(["createMessage", projectId, clone(payload)]);
    if (!messages.has(projectId)) throw notFound();
    const remoteMessage = {
      id: `message_remote_${messageSequence++}`,
      object: "project.message",
      project_id: projectId,
      role: payload.role,
      content: payload.content,
      status: payload.status,
      message_status: payload.status,
      response_id: payload.responseId || null,
      metadata: payload.metadata,
      created_at: now,
      updated_at: now,
    };
    messages.get(projectId).push(remoteMessage);
    return clone(remoteMessage);
  },
  async updateMessage(projectId, messageId, payload) {
    calls.push(["updateMessage", projectId, messageId, clone(payload)]);
    const remoteMessages = messages.get(projectId);
    const index = remoteMessages?.findIndex((message) => message.id === messageId) ?? -1;
    if (index < 0) throw notFound();
    remoteMessages[index] = {
      ...remoteMessages[index],
      content: payload.content,
      status: payload.status,
      message_status: payload.status,
      response_id: payload.responseId || null,
      metadata: payload.metadata,
      updated_at: now + calls.length,
    };
    return clone(remoteMessages[index]);
  },
};

const localProject = (id, title, localMessages = []) => ({
  id,
  title,
  messages: localMessages,
  artifacts: [],
  canvases: [],
  viewMode: "dialog",
  executionMode: "fast",
  createdAt: "2026-07-11T10:00:00.000Z",
  updatedAt: "2026-07-11T10:00:00.000Z",
});

let releaseColdList;
let coldListStarted;
const coldListReady = new Promise((resolve) => { coldListStarted = resolve; });
let coldCreates = 0;
const coldDefault = {
  id: "project_ephemeral_cold_default",
  object: "project.ephemeral",
  title: "New project",
  status: "active",
  metadata: { source: "public_session" },
  message_count: 0,
  created_at: now,
  updated_at: now,
};
const coldApi = {
  async list() {
    coldListStarted();
    await new Promise((resolve) => { releaseColdList = resolve; });
    return clone([coldDefault]);
  },
  async update(projectId, patch) {
    assert.equal(projectId, coldDefault.id);
    Object.assign(coldDefault, patch);
    return clone(coldDefault);
  },
  async create() {
    coldCreates += 1;
    return { ...clone(coldDefault), id: `project_ephemeral_cold_duplicate_${coldCreates}` };
  },
  async listMessages() { return []; },
};
const coldRepository = new ProjectRepository(coldApi);
const coldProject = localProject("project_local_cold", "Холодный старт");
const coldHydration = coldRepository.hydrate([coldProject]);
await coldListReady;
const coldEnsure = coldRepository.ensureProject(coldProject);
releaseColdList();
const [coldHydrated, coldEnsured] = await Promise.all([coldHydration, coldEnsure]);
assert.equal(coldHydrated[0].remoteId, coldDefault.id);
assert.equal(coldEnsured.remoteId, coldDefault.id);
assert.equal(coldCreates, 0, "a send racing cold hydration must not create a duplicate project");

const firstMessage = {
  id: "message_local_first",
  role: "assistant",
  text: "Локальный ответ",
  status: "completed",
  responseId: "resp_old_session",
  canvasId: "canvas:first",
  workSummary: { items: [{ kind: "check", status: "passed" }] },
  createdAt: "2026-07-11T10:00:00.000Z",
};
const repository = new ProjectRepository(api);
let hydrated = await repository.hydrate([
  localProject("project_local_a", "Дом", [firstMessage]),
  localProject("project_local_b", "Документы"),
]);

assert.equal(hydrated.length, 2, "empty session default must be adopted, not exposed as a third project");
assert.equal(hydrated[0].remoteId, "project_ephemeral_default");
assert.equal(hydrated[0].title, "Дом");
assert.equal(hydrated[1].remoteId, "project_ephemeral_created_1");
assert.equal(calls.filter(([kind]) => kind === "create").length, 1);
assert.deepEqual(
  calls.filter(([kind]) => kind === "listMessages").map(([, projectId]) => projectId).sort(),
  ["project_ephemeral_created_1", "project_ephemeral_default"],
);
assert.equal(messages.get("project_ephemeral_default").length, 1, "cached local messages must be synchronized");

const remoteFirst = messages.get("project_ephemeral_default")[0];
remoteFirst.content = "Серверный проверенный ответ";
remoteFirst.status = "completed";
remoteFirst.message_status = "completed";
remoteFirst.updated_at = now + 10_000;
hydrated = await repository.hydrate(hydrated);
const mergedMessages = hydrated[0].messages.filter((message) => message.id === firstMessage.id);
assert.equal(mergedMessages.length, 1, "remote message must merge by shell_client_id without duplication");
assert.equal(mergedMessages[0].text, "Серверный проверенный ответ");
assert.equal(mergedMessages[0].canvasId, "canvas:first");
assert.deepEqual(mergedMessages[0].workSummary, firstMessage.workSummary);

const unsynchronized = {
  id: "message_local_second",
  role: "user",
  text: "Продолжай проект",
  status: "completed",
  createdAt: "2026-07-11T10:05:00.000Z",
};
const createdMessage = await repository.syncMessage(hydrated[0], unsynchronized);
assert.match(createdMessage.remoteId, /^message_remote_/);
await repository.syncMessage(hydrated[0], { ...createdMessage, text: "Продолжай этот проект" });
assert.ok(calls.some(([kind, , messageId]) => kind === "updateMessage" && messageId === createdMessage.remoteId));

assert.deepEqual(projectMetadata({
  id: "project_meta",
  viewMode: "dialog",
  executionMode: "fast",
  draftTool: "",
}, { draft_tool: "estimate", source: "public_session" }), {
  draft_tool: "",
  source: "public_session",
  shell_client_id: "project_meta",
  view_mode: "dialog",
  execution_mode: "fast",
});
const recoveryMetadata = messageMetadata({
  id: "message_recovery",
  recoverable: true,
  excludeFromContext: true,
  retryPrompt: "Не хранить prompt в metadata",
}, { source: "public_session" });
assert.deepEqual(recoveryMetadata, {
  source: "public_session",
  shell_client_id: "message_recovery",
  shell_recoverable: true,
  exclude_from_context: true,
});
const remoteRecovery = mergeRemoteMessage({}, {
  id: "message_remote_recovery",
  role: "assistant",
  content: "Ответ прерван до завершения.",
  status: "incomplete",
  message_status: "incomplete",
  response_id: null,
  metadata: recoveryMetadata,
  created_at: now,
  updated_at: now,
});
assert.equal(remoteRecovery.recoverable, true);
assert.equal(remoteRecovery.excludeFromContext, true);
assert.equal("retryPrompt" in remoteRecovery, false, "public persistence must not duplicate the prompt in metadata");

const orderedCalls = [];
let releaseDelete;
const serializedApi = {
  ...api,
  async remove(projectId, operationId) {
    orderedCalls.push(["remove:start", operationId]);
    await new Promise((resolve) => { releaseDelete = resolve; });
    orderedCalls.push(["remove:end", operationId]);
    return { id: projectId, status: "deleted", title: "Дом", metadata: {}, updated_at: now };
  },
  async restore(projectId, operationId) {
    orderedCalls.push(["restore", operationId]);
    return { id: projectId, status: "active", title: "Дом", metadata: {}, updated_at: now };
  },
};
const serialized = new ProjectRepository(serializedApi);
const bound = { ...hydrated[0], remoteId: "project_ephemeral_default" };
const deleting = serialized.removeProject(bound, { operationId: "delete-1" });
const restoring = serialized.restoreProject(bound, { operationId: "restore-1" });
await new Promise((resolve) => setTimeout(resolve, 0));
assert.deepEqual(orderedCalls, [["remove:start", "delete-1"]]);
releaseDelete();
await Promise.all([deleting, restoring]);
assert.deepEqual(orderedCalls, [
  ["remove:start", "delete-1"],
  ["remove:end", "delete-1"],
  ["restore", "restore-1"],
]);

const secondDelete = serialized.removeProject(bound, { operationId: "delete-2" });
await new Promise((resolve) => setTimeout(resolve, 0));
releaseDelete();
await secondDelete;
assert.deepEqual(
  orderedCalls.filter(([kind]) => kind === "remove:start").map(([, key]) => key),
  ["delete-1", "delete-2"],
  "a second delete after restore must use a new idempotency key",
);

projects = [{
  id: "project_ephemeral_new_session",
  title: "New project",
  status: "active",
  metadata: { source: "public_session" },
  message_count: 0,
  created_at: now,
  updated_at: now,
}];
messages.clear();
messages.set("project_ephemeral_new_session", []);
const rebound = await repository.updateProject({
  ...hydrated[0],
  remoteId: "project_ephemeral_expired",
  title: "Дом после обновления сессии",
});
assert.equal(rebound.remoteId, "project_ephemeral_new_session");
assert.equal(projects.length, 1, "session rollover must adopt the new empty default instead of creating a duplicate");
assert.equal(projects[0].metadata.shell_client_id, hydrated[0].id);
assert.deepEqual(
  messages.get("project_ephemeral_new_session").map((message) => message.content),
  hydrated[0].messages.filter((message) => message.text).map((message) => message.text),
  "session rollover must migrate the cached dialogue into the newly owned project",
);
assert.ok(
  messages.get("project_ephemeral_new_session").every((message) => message.response_id === null),
  "response IDs from the expired session must not cross the ownership boundary",
);
assert.ok(
  rebound.messages.every((message) => !message.responseId),
  "the rebound local projection must clear expired response bindings",
);

projects = [{
  id: "project_ephemeral_concurrent_session",
  title: "New project",
  status: "active",
  metadata: { source: "public_session" },
  message_count: 0,
  created_at: now,
  updated_at: now,
}];
messages.clear();
messages.set("project_ephemeral_concurrent_session", []);
const listCallsBeforeConcurrentRebind = calls.filter(([kind]) => kind === "list").length;
const concurrentProject = {
  ...rebound,
  remoteId: "project_ephemeral_new_session",
  messages: hydrated[0].messages,
};
const concurrentRebounds = await Promise.all([
  repository.reconcileProject(concurrentProject, { failedRemoteId: "project_ephemeral_new_session" }),
  repository.reconcileProject(concurrentProject, { failedRemoteId: "project_ephemeral_new_session" }),
]);
assert.deepEqual(
  concurrentRebounds.map((project) => project.remoteId),
  ["project_ephemeral_concurrent_session", "project_ephemeral_concurrent_session"],
);
assert.equal(
  calls.filter(([kind]) => kind === "list").length - listCallsBeforeConcurrentRebind,
  1,
  "concurrent sends for one local project must share one reconciliation",
);
assert.equal(
  messages.get("project_ephemeral_concurrent_session").length,
  hydrated[0].messages.filter((message) => message.text).length,
  "idempotent migration must not duplicate conversation messages",
);

const missingDeleteApi = {
  ...api,
  async remove() { throw notFound(); },
};
const missingDeleteRepository = new ProjectRepository(missingDeleteApi);
const removed = await missingDeleteRepository.removeProject(rebound, { operationId: "delete-missing" });
assert.equal(removed.status, "deleted", "404 after session rollover is already a successful local delete");

projects = [{
  id: "project_ephemeral_generic_rebound",
  title: "New project",
  status: "active",
  metadata: { source: "public_session" },
  message_count: 0,
  created_at: now,
  updated_at: now,
}];
messages.clear();
messages.set("project_ephemeral_generic_rebound", []);
let staleUpdateAttempts = 0;
const genericStaleProjectApi = {
  ...api,
  async update(projectId, patch) {
    if (projectId === "project_ephemeral_generic_stale") {
      staleUpdateAttempts += 1;
      throw endpointNotFound(`/v1/projects/${projectId}`);
    }
    return api.update(projectId, patch);
  },
};
const genericStaleProjectRepository = new ProjectRepository(genericStaleProjectApi);
const genericRebound = await genericStaleProjectRepository.updateProject({
  ...localProject("project_local_generic_stale", "Проект после reload"),
  remoteId: "project_ephemeral_generic_stale",
  executionMode: "codex",
});
assert.equal(genericRebound.remoteId, "project_ephemeral_generic_rebound");
assert.equal(staleUpdateAttempts, 1, "a stale public project ID must trigger one bounded rebind");

projects = [{
  id: "project_ephemeral_message_rebound",
  title: "New project",
  status: "active",
  metadata: { source: "public_session" },
  message_count: 0,
  created_at: now,
  updated_at: now,
}];
messages.clear();
messages.set("project_ephemeral_message_rebound", []);
const messageIdempotencyKeys = [];
let staleMessageAttempts = 0;
const genericStaleMessageApi = {
  ...api,
  async createMessage(projectId, payload) {
    messageIdempotencyKeys.push(payload.idempotencyKey);
    if (projectId === "project_ephemeral_message_stale") {
      staleMessageAttempts += 1;
      throw endpointNotFound(`/v1/projects/${projectId}/messages`);
    }
    return api.createMessage(projectId, payload);
  },
};
const genericStaleMessageRepository = new ProjectRepository(genericStaleMessageApi);
const staleMessageProject = {
  ...localProject("project_local_message_stale", "Диалог после reload"),
  remoteId: "project_ephemeral_message_stale",
};
const recoveredMessage = await genericStaleMessageRepository.syncMessage(staleMessageProject, {
  id: "message_local_idempotent_rebind",
  role: "user",
  text: "Продолжить тот же проект",
  status: "completed",
});
assert.match(recoveredMessage.remoteId, /^message_remote_/);
assert.equal(staleMessageAttempts, 1, "a stale message route must trigger one bounded project rebind");
assert.deepEqual(
  messageIdempotencyKeys,
  ["shell-message-message_local_idempotent_rebind", "shell-message-message_local_idempotent_rebind"],
  "the one replay after rebind must preserve the original message idempotency key",
);

const providerNotFoundRepository = new ProjectRepository({
  ...api,
  async update() { throw endpointNotFound("/v1/responses"); },
});
await assert.rejects(
  providerNotFoundRepository.updateProject({
    ...localProject("project_local_provider_404", "Не перехватывать provider 404"),
    remoteId: "project_ephemeral_provider_404",
  }),
  /Not Found/,
  "a non-project 404 must never be converted into a project rebind",
);

console.log("Kolibri ProjectRepository hydration, CRUD, rollover, message merge, and operation ordering passed");
