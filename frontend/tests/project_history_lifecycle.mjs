import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

import { HISTORY_STORAGE_KEY, PROJECTS_STORAGE_KEY } from "../src/app/constants.js";
import {
  createProjectStoreState,
  deleteProjectState,
  projectStoreReducer,
  restoreProjectState,
} from "../src/shell/projectStoreModel.js";
import { initialWorkbench, workbenchReducer } from "../src/workbench/reducer.js";

const vite = await createServer({
  root: fileURLToPath(new URL("..", import.meta.url)),
  server: { middlewareMode: true },
  appType: "custom",
  logLevel: "silent",
});
const { readProjects } = await vite.ssrLoadModule("/src/app/utils.js");
const { materializedArtifacts } = await vite.ssrLoadModule("/src/shell/projectModel.js");
await vite.close();

const project = (id, title) => ({
  id,
  title,
  messages: [],
  artifacts: [],
  canvases: [],
  createdAt: "2026-07-11T10:00:00.000Z",
  updatedAt: "2026-07-11T10:00:00.000Z",
});

const projectA = project("project-a", "Проект A");
const projectB = project("project-b", "Проект B");
const projectC = project("project-c", "Проект C");
const replacement = project("project-new", "Новый проект");

let store = createProjectStoreState([projectA, projectB], projectA.id);
store.busyProjects = { [projectB.id]: true };
store = deleteProjectState(store, projectA.id);
assert.deepEqual(store.projects.map((item) => item.id), [projectB.id]);
assert.equal(store.activeProjectId, projectB.id);
assert.equal(projectA.id in store.busyProjects, false);
assert.equal(store.busyProjects[projectB.id], true);
assert.equal(store.lastDeleted.project.id, projectA.id);
store = restoreProjectState(store);
assert.deepEqual(store.projects.map((item) => item.id), [projectA.id, projectB.id]);
assert.equal(store.activeProjectId, projectA.id);
assert.equal(store.lastDeleted, null);

store = createProjectStoreState([projectA, projectB], projectA.id);
store = deleteProjectState(store, projectB.id);
assert.equal(store.activeProjectId, projectA.id);
store = restoreProjectState(store);
assert.equal(store.activeProjectId, projectA.id, "undoing an inactive project must not steal focus");

store = createProjectStoreState([projectA, projectB, projectC], projectA.id);
store = deleteProjectState(store, projectA.id);
store = projectStoreReducer(store, { type: "SET_ACTIVE_PROJECT", projectId: projectC.id });
store = restoreProjectState(store);
assert.equal(store.activeProjectId, projectC.id, "undo must preserve a project explicitly selected after deletion");

store = createProjectStoreState([projectA, projectB], projectA.id);
store.busyProjects = { [projectA.id]: true };
const busyDelete = deleteProjectState(store, projectA.id);
assert.equal(busyDelete, store, "a project with an active request cannot be deleted");

store = createProjectStoreState([projectA, projectB], projectA.id);
store = projectStoreReducer(store, {
  type: "DELETE_PROJECT",
  projectId: projectA.id,
  operationId: "delete-a",
});
const rollbackSnapshot = store.lastDeleted;
store = projectStoreReducer(store, { type: "DISMISS_DELETION" });
store = projectStoreReducer(store, { type: "ROLLBACK_PROJECT_DELETE", deletion: rollbackSnapshot });
assert.deepEqual(store.projects.map((item) => item.id), [projectA.id, projectB.id]);
assert.equal(store.lastDeleted, null, "network rollback must remain exact after the Undo notice was dismissed");

store = createProjectStoreState([projectA], projectA.id);
store = deleteProjectState(store, projectA.id, replacement);
assert.deepEqual(store.projects.map((item) => item.id), [replacement.id]);
assert.equal(store.activeProjectId, replacement.id);
store = restoreProjectState(store);
assert.deepEqual(store.projects.map((item) => item.id), [projectA.id], "undo removes an untouched generated replacement");
assert.equal(store.activeProjectId, projectA.id);

store = createProjectStoreState([projectA], projectA.id);
store = deleteProjectState(store, projectA.id, replacement);
store.projects = store.projects.map((item) => ({ ...item, remoteId: "project_ephemeral_replacement" }));
store = restoreProjectState(store);
assert.deepEqual(store.projects.map((item) => item.id), [projectA.id], "remote binding alone must not make the generated replacement look edited");

store = createProjectStoreState([projectA], projectA.id);
store = deleteProjectState(store, projectA.id, replacement);
store.projects = store.projects.map((item) => ({ ...item, title: "Начат новый проект" }));
store = restoreProjectState(store);
assert.deepEqual(store.projects.map((item) => item.id), [projectA.id, replacement.id], "undo preserves a replacement already edited by the user");

let workbench = initialWorkbench;
for (const window of [
  { id: "projects-window", kind: "projects", title: "История" },
  { id: "workspace:project-a", kind: "workspace", title: "A", projectId: projectA.id },
  { id: "canvas-window:a", kind: "canvas", title: "Canvas A", parentProjectId: projectA.id },
  { id: "artifact:a", kind: "pdf", title: "PDF A", parentProjectId: projectA.id },
  { id: "workspace:project-b", kind: "workspace", title: "B", projectId: projectB.id },
]) {
  workbench = workbenchReducer(workbench, { type: "OPEN", window });
}
workbench = workbenchReducer(workbench, { type: "REMOVE_PROJECT_WINDOWS", projectId: projectA.id });
assert.deepEqual(workbench.windows.map((item) => item.id), ["projects-window", "workspace:project-b"]);
assert.equal(workbench.focusedId, "workspace:project-b");

assert.deepEqual(materializedArtifacts([
  { id: "draft", status: "pending" },
  { id: "missing" },
  { id: "verified", status: "materialized" },
]).map((item) => item.id), ["verified"]);

const previousStorageDescriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
const values = new Map([
  [PROJECTS_STORAGE_KEY, "[]"],
  [HISTORY_STORAGE_KEY, JSON.stringify([{ projectId: "legacy", title: "Не воскрешать" }])],
]);
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: {
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(key, String(value)); },
    removeItem(key) { values.delete(key); },
  },
});
try {
  const projects = readProjects();
  assert.equal(projects.length, 1);
  assert.notEqual(projects[0].id, "legacy", "an explicitly empty v2 history must not resurrect v1 data");
} finally {
  if (previousStorageDescriptor) Object.defineProperty(globalThis, "localStorage", previousStorageDescriptor);
  else delete globalThis.localStorage;
}

console.log("Kolibri project delete, window cleanup, persistence, artifact visibility, and undo contracts passed");
