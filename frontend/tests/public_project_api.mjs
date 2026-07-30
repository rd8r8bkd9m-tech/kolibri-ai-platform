import assert from "node:assert/strict";


const originalFetch = globalThis.fetch;
const calls = [];

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

globalThis.fetch = async (url, options = {}) => {
  calls.push({ url: String(url), options });
  if (url === "/v1/public/session") {
    return jsonResponse({
      id: "session_test",
      object: "public.session",
      active: true,
      project: { id: "project_ephemeral_default", object: "project.ephemeral" },
      model: "kolibri",
    });
  }
  if (String(url).endsWith("/messages") && options.method === "POST") {
    return jsonResponse({ id: "message_test", object: "project.message" }, 201);
  }
  if (String(url).includes("/messages")) {
    return jsonResponse({ object: "list", data: [], has_more: false });
  }
  if (url === "/v1/projects" && options.method === "POST") {
    return jsonResponse({ id: "project_ephemeral_test", object: "project.ephemeral" }, 201);
  }
  if (String(url).includes("/delete")) {
    return jsonResponse({ id: "project_ephemeral_test", status: "deleted" });
  }
  if (String(url).includes("/restore")) {
    return jsonResponse({ id: "project_ephemeral_test", status: "active" });
  }
  return jsonResponse({ object: "list", data: [], has_more: false });
};

try {
  const api = await import("../src/runtime/kolibriApi.js");
  api.resetPublicSessionForTests();
  assert.equal(api.API_ENDPOINTS.publicProjects, "/v1/projects");

  const created = await api.publicProjectsApi.create({
    title: "Дом",
    metadata: { view: "dialog" },
    idempotencyKey: "project-create-stable",
  });
  assert.equal(created.id, "project_ephemeral_test");
  await api.publicProjectsApi.list();
  await api.publicProjectsApi.get("project_ephemeral_test");
  await api.publicProjectsApi.update("project_ephemeral_test", {
    title: "Дом — смета",
    idempotencyKey: "project-update-stable",
  });
  await api.publicProjectsApi.createMessage("project_ephemeral_test", {
    role: "user",
    content: "Продолжай проект",
    idempotencyKey: "message-create-stable",
  });
  await api.publicProjectsApi.listMessages("project_ephemeral_test");
  await api.publicProjectsApi.remove("project_ephemeral_test", "project-delete-stable");
  await api.publicProjectsApi.restore("project_ephemeral_test", "project-restore-stable");

  assert.equal(typeof api.publicProjectsApi.create, "function");
  assert.equal(typeof api.publicProjectsApi.restoreMessage, "function");
  const projectCalls = calls.filter((call) => call.url.startsWith("/v1/projects"));
  assert.ok(projectCalls.length >= 7);
  assert.ok(projectCalls.every((call) => !call.options.headers?.Authorization));
  assert.ok(projectCalls.every((call) => call.url.startsWith("/v1/projects")));
  assert.ok(calls.some((call) => call.url === "/v1/projects" && !call.options.method));

  const createCall = calls.find(
    (call) => call.url === "/v1/projects" && call.options.method === "POST",
  );
  assert.deepEqual(JSON.parse(createCall.options.body), {
    title: "Дом",
    metadata: { view: "dialog" },
  });
  assert.equal(
    createCall.options.headers["Idempotency-Key"],
    "project-create:project-create-stable",
  );
  const deleteCall = calls.find((call) => call.url.endsWith("/delete"));
  assert.equal(deleteCall.options.method, "POST");
  assert.equal(
    deleteCall.options.headers["Idempotency-Key"],
    "project-delete:project-delete-stable",
  );

  await assert.rejects(
    api.publicProjectsApi.create({
      title: "Unsafe",
      metadata: { api_key: "must-not-" + "enter-public-metadata" },
    }),
    /credential|секрет/,
  );
} finally {
  globalThis.fetch = originalFetch;
}

console.log("public project API helpers: ok");
