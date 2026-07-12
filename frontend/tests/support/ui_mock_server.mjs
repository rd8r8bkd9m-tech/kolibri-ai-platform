import http from "node:http";

const host = "127.0.0.1";
const port = Number(process.env.KOLIBRI_UI_MOCK_PORT || 5190);
const now = () => Math.floor(Date.now() / 1000);
let projectSequence = 1;
let messageSequence = 1;
let responseSequence = 1;
let sessionSequence = 1;
const messageIdempotency = new Map();
const projects = [{
  id: "project_ephemeral_ui_default",
  object: "project.ephemeral",
  title: "New project",
  status: "active",
  durable: false,
  metadata: { source: "public_session" },
  message_count: 0,
  created_at: now(),
  updated_at: now(),
  deleted_at: null,
}];
const messages = new Map([[projects[0].id, []]]);

function sendJson(response, status, payload, headers = {}) {
  response.writeHead(status, {
    "Cache-Control": "no-store",
    "Content-Type": "application/json; charset=utf-8",
    ...headers,
  });
  response.end(JSON.stringify(payload));
}

async function readJson(request) {
  let body = "";
  for await (const chunk of request) body += chunk;
  return body ? JSON.parse(body) : {};
}

function projectPayload(project) {
  project.message_count = (messages.get(project.id) || []).filter((message) => message.status !== "deleted").length;
  return { ...project };
}

function projectById(projectId, includeDeleted = false) {
  return projects.find((project) => project.id === projectId && (includeDeleted || project.status !== "deleted"));
}

function messageById(projectId, messageId, includeDeleted = false) {
  return (messages.get(projectId) || []).find((message) => message.id === messageId && (includeDeleted || message.status !== "deleted"));
}

function messagePayload(message) {
  return {
    ...message,
    message_status: message.message_status || message.status,
  };
}

function responseEnvelope(id, outputText) {
  return {
    id,
    object: "response",
    created_at: now(),
    status: "completed",
    model: "kolibri",
    output: [{
      id: `msg_${id}`,
      type: "message",
      status: "completed",
      role: "assistant",
      content: [{ type: "output_text", text: outputText, annotations: [] }],
    }],
    output_text: outputText,
  };
}

async function handleRequest(request, response) {
  const url = new URL(request.url, `http://${request.headers.host}`);
  const path = url.pathname;
  if (path === "/__test__/reset-public-session" && request.method === "POST") {
    sessionSequence += 1;
    const replacement = {
      id: `project_ephemeral_ui_session_${sessionSequence}`,
      object: "project.ephemeral",
      title: "New project",
      status: "active",
      durable: false,
      metadata: { source: "public_session" },
      message_count: 0,
      created_at: now(),
      updated_at: now(),
      deleted_at: null,
    };
    projects.splice(0, projects.length, replacement);
    messages.clear();
    messages.set(replacement.id, []);
    messageIdempotency.clear();
    return sendJson(response, 200, { status: "reset", session_id: `session_ui_${sessionSequence}` });
  }
  if (path === "/v1/public/session") {
    return sendJson(response, 200, {
      id: `session_ui_${sessionSequence}`,
      object: "public.session",
      active: true,
      expires_at: now() + 3600,
      project: projectPayload(projects[0]),
      model: "kolibri",
    }, { "Set-Cookie": "kolibri_public_session=ui; HttpOnly; Path=/; SameSite=Lax" });
  }
  if (path === "/v1/models") {
    return sendJson(response, 200, {
      object: "list",
      data: [{ id: "kolibri", object: "model", supported_execution_modes: ["fast", "codex"] }],
    });
  }
  if (path === "/api/factory/status") {
    return sendJson(response, 200, {
      status: "online",
      online_nodes: 0,
      total_nodes: 0,
      queue_size: 0,
      control_plane: { status: "ok" },
    });
  }
  if (path === "/v1/tasks") return sendJson(response, 200, { object: "list", data: [] });
  if (path === "/v1/nodes") return sendJson(response, 200, { object: "list", data: [] });
  if (path === "/v1/capabilities") return sendJson(response, 200, { object: "list", data: [] });
  if (path === "/v1/approvals") return sendJson(response, 200, { object: "list", data: [] });

  if (path === "/v1/projects" && request.method === "GET") {
    return sendJson(response, 200, {
      object: "list",
      data: projects.filter((project) => project.status !== "deleted").map(projectPayload),
      has_more: false,
    });
  }
  if (path === "/v1/projects" && request.method === "POST") {
    const body = await readJson(request);
    const project = {
      id: `project_ephemeral_ui_${projectSequence++}`,
      object: "project.ephemeral",
      title: body.title,
      status: "active",
      durable: false,
      metadata: body.metadata || {},
      message_count: 0,
      created_at: now(),
      updated_at: now(),
      deleted_at: null,
    };
    projects.push(project);
    messages.set(project.id, []);
    return sendJson(response, 201, projectPayload(project));
  }

  const projectMatch = path.match(/^\/v1\/projects\/([^/]+)$/);
  if (projectMatch) {
    const project = projectById(projectMatch[1], url.searchParams.get("include_deleted") === "true");
    if (!project) return sendJson(response, 404, { detail: "project_not_found" });
    if (request.method === "GET") return sendJson(response, 200, projectPayload(project));
    const body = await readJson(request);
    if (body.title !== undefined) project.title = body.title;
    if (body.metadata !== undefined) project.metadata = body.metadata;
    project.updated_at = now();
    return sendJson(response, 200, projectPayload(project));
  }

  const projectAction = path.match(/^\/v1\/projects\/([^/]+)\/(delete|restore)$/);
  if (projectAction) {
    const project = projectById(projectAction[1], true);
    if (!project) return sendJson(response, 404, { detail: "project_not_found" });
    project.status = projectAction[2] === "delete" ? "deleted" : "active";
    project.deleted_at = project.status === "deleted" ? now() : null;
    project.updated_at = now();
    return sendJson(response, 200, projectPayload(project));
  }

  const messagesList = path.match(/^\/v1\/projects\/([^/]+)\/messages$/);
  if (messagesList) {
    const project = projectById(messagesList[1]);
    if (!project) return sendJson(response, 404, { detail: "project_not_found" });
    if (request.method === "GET") {
      return sendJson(response, 200, {
        object: "list",
        data: (messages.get(project.id) || []).filter((message) => message.status !== "deleted").map(messagePayload),
        has_more: false,
      });
    }
    const body = await readJson(request);
    const idempotencyKey = String(request.headers["idempotency-key"] || "");
    const idempotencyScope = `${project.id}:${idempotencyKey}`;
    if (idempotencyKey && messageIdempotency.has(idempotencyScope)) {
      return sendJson(response, 200, messagePayload(messageIdempotency.get(idempotencyScope)));
    }
    const message = {
      id: `message_ui_${messageSequence++}`,
      object: "project.message",
      project_id: project.id,
      role: body.role,
      content: body.content,
      status: body.status || "completed",
      message_status: body.status || "completed",
      response_id: body.response_id || null,
      metadata: body.metadata || {},
      created_at: now(),
      updated_at: now(),
      deleted_at: null,
    };
    messages.get(project.id).push(message);
    if (idempotencyKey) messageIdempotency.set(idempotencyScope, message);
    return sendJson(response, 201, messagePayload(message));
  }

  const messageMatch = path.match(/^\/v1\/projects\/([^/]+)\/messages\/([^/]+)$/);
  if (messageMatch) {
    const message = messageById(messageMatch[1], messageMatch[2], url.searchParams.get("include_deleted") === "true");
    if (!message) return sendJson(response, 404, { detail: "message_not_found" });
    if (request.method === "GET") return sendJson(response, 200, messagePayload(message));
    const body = await readJson(request);
    if (body.content !== undefined) message.content = body.content;
    if (body.status !== undefined) message.status = body.status;
    message.message_status = message.status;
    if (body.response_id !== undefined) message.response_id = body.response_id;
    if (body.metadata !== undefined) message.metadata = body.metadata;
    message.updated_at = now();
    return sendJson(response, 200, messagePayload(message));
  }

  if (path === "/v1/responses" && request.method === "POST") {
    const body = await readJson(request);
    if (!projectById(body.project_id)) return sendJson(response, 404, { detail: "project_not_found" });
    const id = `resp_ui_${responseSequence++}`;
    const deltas = ["Потоковый ответ Kolibri ", "приходит по частям."];
    const envelope = responseEnvelope(id, deltas.join(""));
    response.writeHead(200, {
      "Cache-Control": "no-cache, no-store",
      Connection: "keep-alive",
      "Content-Type": "text/event-stream; charset=utf-8",
    });
    response.write(`event: response.created\ndata: ${JSON.stringify({ type: "response.created", response: { ...envelope, status: "in_progress", output: [] } })}\n\n`);
    response.write(`event: response.output_text.delta\ndata: ${JSON.stringify({ type: "response.output_text.delta", delta: deltas[0] })}\n\n`);
    setTimeout(() => {
      response.write(`event: response.output_text.delta\ndata: ${JSON.stringify({ type: "response.output_text.delta", delta: deltas[1] })}\n\n`);
      setTimeout(() => {
        response.end(`event: response.completed\ndata: ${JSON.stringify({ type: "response.completed", response: envelope })}\n\n`);
      }, 500);
    }, 1_500);
    return;
  }

  return sendJson(response, 404, { detail: "not_found", path });
}

const server = http.createServer((request, response) => {
  handleRequest(request, response).catch((error) => {
    sendJson(response, 500, { detail: error.message });
  });
});

server.listen(port, host, () => {
  process.stdout.write(`Kolibri UI mock listening on http://${host}:${port}\n`);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
