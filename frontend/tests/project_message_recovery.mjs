import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

const vite = await createServer({
  root: fileURLToPath(new URL("..", import.meta.url)),
  server: { middlewareMode: true },
  appType: "custom",
  logLevel: "silent",
});
const {
  FAILED_RESPONSE_TEXT,
  INTERRUPTED_RESPONSE_TEXT,
  recoverInterruptedProject,
} = await vite.ssrLoadModule("/src/shell/projectMessageRecovery.js");
const {
  beginTurnProject,
  completedAssistantReply,
  prepareProjectTurn,
} = await vite.ssrLoadModule("/src/shell/projectMessagingModel.js");
const {
  createProjectStoreState,
  projectStoreReducer,
} = await vite.ssrLoadModule("/src/shell/projectStoreModel.js");
const { readProjects } = await vite.ssrLoadModule("/src/app/utils.js");
await vite.close();

const interrupted = {
  id: "project-recovery",
  title: "Продолжение проекта",
  executionMode: "codex",
  messages: [
    { id: "user-1", role: "user", text: "что умеешь делать?", createdAt: "2026-07-11T10:00:00.000Z" },
    {
      id: "assistant-1",
      role: "assistant",
      text: "",
      progressText: "",
      status: "running",
      createdAt: "2026-07-11T10:00:01.000Z",
      workSummary: { items: [{ kind: "plan", status: "running", detail: "Готовлю ответ" }] },
    },
  ],
  artifacts: [],
  canvases: [],
  createdAt: "2026-07-11T10:00:00.000Z",
  updatedAt: "2026-07-11T10:00:01.000Z",
};

const recovered = recoverInterruptedProject(interrupted);
const recoveredReply = recovered.messages[1];
assert.equal(recoveredReply.status, "incomplete");
assert.equal(recoveredReply.text, INTERRUPTED_RESPONSE_TEXT);
assert.equal(recoveredReply.recoverable, true);
assert.equal(recoveredReply.excludeFromContext, true);
assert.equal(recoveredReply.retryPrompt, "что умеешь делать?");
assert.equal(recoveredReply.retryExecutionMode, "codex");
assert.equal(recoveredReply.workSummary.items[0].status, "incomplete");
assert.ok(recoveredReply.text.trim(), "a recovered assistant turn must never render blank");

const completedBlank = recoverInterruptedProject({
  ...interrupted,
  messages: [interrupted.messages[0], { ...interrupted.messages[1], status: "completed" }],
});
assert.equal(completedBlank.messages[1].status, "incomplete");
assert.equal(completedBlank.messages[1].text, INTERRUPTED_RESPONSE_TEXT);

const remotelyMarked = recoverInterruptedProject({
  ...interrupted,
  messages: [
    interrupted.messages[0],
    {
      ...interrupted.messages[1],
      text: INTERRUPTED_RESPONSE_TEXT,
      status: "incomplete",
      recoverable: true,
      excludeFromContext: true,
      retryPrompt: "",
    },
  ],
});
assert.equal(remotelyMarked.messages[1].retryPrompt, "что умеешь делать?");

const legacyFailure = recoverInterruptedProject({
  ...interrupted,
  messages: [
    interrupted.messages[0],
    {
      ...interrupted.messages[1],
      text: "legacy provider failure wording",
      status: "failed",
    },
  ],
});
assert.equal(legacyFailure.messages[1].text, FAILED_RESPONSE_TEXT);
assert.equal(legacyFailure.messages[1].status, "incomplete");
assert.equal(legacyFailure.messages[1].retryPrompt, "что умеешь делать?");

const state = createProjectStoreState([interrupted], interrupted.id);
assert.equal(state.projects[0].messages[1].status, "incomplete");
const reconciled = projectStoreReducer(state, {
  type: "RECONCILE_PROJECTS",
  projects: [interrupted],
  baseProjectIds: [interrupted.id],
  startedAt: Date.now() + 1000,
});
assert.equal(reconciled.projects[0].messages[1].text, INTERRUPTED_RESPONSE_TEXT);

const liveState = {
  ...state,
  projects: [{ ...interrupted, updatedAt: "2026-07-12T10:00:00.000Z" }],
  busyProjects: { [interrupted.id]: true },
};
const liveReconciled = projectStoreReducer(liveState, {
  type: "RECONCILE_PROJECTS",
  projects: [interrupted],
  baseProjectIds: [interrupted.id],
  startedAt: Date.parse("2026-07-12T09:59:59.000Z"),
});
assert.equal(liveReconciled.projects[0].messages[1].status, "running", "hydration must not interrupt a live in-page request");

const retry = prepareProjectTurn(recovered, recoveredReply.retryPrompt, "", "codex", {
  retryMessageId: recoveredReply.id,
});
assert.equal(retry.retrying, true);
assert.equal(retry.userMessage, null, "retry must reuse the original user turn");
assert.deepEqual(retry.requestMessages, [], "the Responses API appends the retried user prompt exactly once");
const retryingProject = beginTurnProject(recovered, retry);
assert.equal(retryingProject.messages.length, recovered.messages.length);
assert.equal(retryingProject.messages[1].status, "running");
assert.equal(retryingProject.messages[1].text, "");
const completed = completedAssistantReply(retry.reply, {
  text: "Готовый ответ",
  task: null,
  taskId: "resp-safe",
  workSummary: null,
}, null);
assert.equal(completed.status, "completed");
assert.equal(completed.text, "Готовый ответ");
assert.equal(completed.recoverable, false);

const storage = new Map([["kolibri.vista.projects.v2", JSON.stringify([interrupted])]]);
const previousStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: { getItem: (key) => storage.get(key) || null },
});
try {
  const restored = readProjects();
  assert.equal(restored[0].messages[1].text, INTERRUPTED_RESPONSE_TEXT);
  assert.equal(restored[0].messages[1].status, "incomplete");
} finally {
  if (previousStorage) Object.defineProperty(globalThis, "localStorage", previousStorage);
  else delete globalThis.localStorage;
}

const cacheSource = readFileSync(new URL("../src/shell/useProjectCache.js", import.meta.url), "utf8");
const workspaceSource = readFileSync(new URL("../src/windows/ProjectWorkspace.jsx", import.meta.url), "utf8");
assert.match(cacheSource, /JSON\.stringify\(recoverInterruptedProjects\(state\.projects\)\)/);
assert.match(workspaceSource, /retryMessageId: message\.id/);
assert.match(workspaceSource, /status=\{message\.status \|\| "completed"\}/);

console.log("Kolibri interrupted assistant recovery, retry, and nonblank persistence contracts passed");
