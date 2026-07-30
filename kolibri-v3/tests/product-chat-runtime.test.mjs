import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const APP_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

const readSource = (relativePath) =>
  readFile(path.join(APP_ROOT, relativePath), "utf8");

const contracts = await import(
  pathToFileURL(
    path.join(APP_ROOT, "lib/product-chat/contracts.ts"),
  ).href
);

const timestamp = "2026-07-28T10:20:30.000Z";
const threadId = "thread_1234567890abcdef";

const validThread = {
  id: threadId,
  projectId: "project_1234567890abcdef",
  title: "Смета производственного корпуса",
  status: "regular",
  pinned: false,
  createdAt: timestamp,
  updatedAt: timestamp,
  lastMessageAt: timestamp,
};

const validMessage = {
  id: "message_1234567890abcdef",
  role: "user",
  content: [{ type: "text", text: "Подготовь предварительную смету." }],
  createdAt: timestamp,
  status: { type: "complete", reason: "stop" },
  submittedFeedback: null,
};

test("strict Product Chat contracts accept only the documented V1 pages", () => {
  assert.deepEqual(
    contracts.parseProductChatThreadPage({
      threads: [validThread],
      nextCursor: null,
    }),
    {
      threads: [validThread],
      nextCursor: null,
    },
  );

  assert.deepEqual(
    contracts.parseProductChatMessagePage(
      {
        threadId,
        messages: [validMessage],
        nextCursor: null,
      },
      threadId,
    ),
    {
      threadId,
      messages: [validMessage],
      nextCursor: null,
    },
  );
});

test("strict Product Chat contracts reject drift, duplicate IDs, and crossed scope", () => {
  assert.throws(
    () =>
      contracts.parseProductChatThreadPage({
        threads: [{ ...validThread, tenantId: "browser-claim" }],
        nextCursor: null,
      }),
    contracts.ProductChatContractError,
  );
  assert.throws(
    () =>
      contracts.parseProductChatThreadPage({
        threads: [validThread, validThread],
        nextCursor: null,
      }),
    /duplicate identifiers/,
  );
  assert.throws(
    () =>
      contracts.parseProductChatMessagePage(
        {
          threadId: "thread_other123456",
          messages: [validMessage],
          nextCursor: null,
        },
        threadId,
      ),
    contracts.ProductChatContractError,
  );
  assert.throws(
    () =>
      contracts.parseProductChatMessagePage(
        {
          threadId,
          messages: [
            {
              ...validMessage,
              status: { type: "running", reason: "unknown" },
            },
          ],
          nextCursor: null,
        },
        threadId,
      ),
    contracts.ProductChatContractError,
  );
});

test("the official AG-UI runtime is backed by durable server history", async () => {
  const [provider, client, adapters] = await Promise.all([
    readSource("app/MyRuntimeProvider.tsx"),
    readSource("lib/product-chat/client.ts"),
    readSource("lib/product-chat/adapters.ts"),
  ]);

  assert.match(provider, /from\s+["']@ag-ui\/client["']/);
  assert.match(provider, /\bHttpAgent\b/);
  assert.match(provider, /\buseAgUiRuntime\b/);
  assert.match(provider, /\bUseAgUiThreadListAdapter\b/);
  assert.match(provider, /\buseIdentity\b/);
  assert.match(provider, /preferredAgentProfile/);
  assert.match(provider, /thread_\$\{globalThis\.crypto\.randomUUID\(\)/);
  assert.match(provider, /mountedRef\.current/);
  assert.match(provider, /pendingProjectionRef\.current/);
  assert.match(provider, /bootstrapRef\.current\s*=\s*null/);
  assert.doesNotMatch(provider, /\bnew\s+Map\b/);
  assert.doesNotMatch(provider, /\blocalStorage\b/);
  assert.doesNotMatch(provider, /\bonRename\s*:/);
  assert.match(provider, /\bonArchive\s*:/);
  assert.match(provider, /\bonUnarchive\s*:/);
  assert.match(provider, /\bonDelete\s*:/);
  assert.match(provider, /\bonUpdateCustom\s*:/);

  assert.match(adapters, /\bfromAgUiMessages\b/);
  assert.match(adapters, /\bExportedMessageRepository\.fromArray\b/);
  assert.match(adapters, /backend atomically persists the AG-UI user message/i);

  assert.match(client, /PRODUCT_CHAT_BFF_BASE\s*=\s*["']\/api\/v3\/chat["']/);
  assert.match(client, /PRODUCT_AG_UI_BFF_URL\s*=\s*["']\/api\/agui["']/);
  assert.match(client, /credentials:\s*["']same-origin["']/);
  assert.match(client, /agentProfile:\s*profile/);
  assert.doesNotMatch(
    client,
    /executionMode\s*===\s*["']developer["']\s*\?\s*["']codex-cli["']/,
  );
  assert.match(client, /\.\.\.\(accessMode\s*===\s*["']standard["']/);
  assert.match(client, /getAccessMode/);
  assert.match(provider, /developerAccessModeRef\.current/);
  assert.match(client, /getActiveThreadId/);
  assert.match(client, /threadId:\s*activeThreadId/);
  assert.match(provider, /projectionRef\.current\.activeThreadId/);
  assert.match(provider, /activeRunIdRef\.current\s*=\s*runId/);
  assert.match(provider, /\bonCancel:\s*\(\)\s*=>/);
  assert.match(provider, /agent\.abortRun\(\)/);
  assert.match(provider, /client\s*\.cancelRun\(runId\)/);
  assert.doesNotMatch(client, /kolibriAgentProfile/);
  assert.match(client, /\bwithCsrfHeader\b/);
  assert.match(client, /\basync cancelRun\(runId:\s*string\)/);
  assert.match(client, /x-kolibri-run-id/);
  assert.match(client, /onAccepted\?\.\(acceptedRunId\)/);
  assert.match(client, /state:\s*null/);
  assert.match(client, /tools:\s*\[\]/);
  assert.match(client, /context:\s*\[\]/);
  assert.match(client, /normalizedRunId\s*!==\s*null/);
  assert.match(client, /runId:\s*body\.runId/);
  assert.doesNotMatch(client, /semanticRunId/);
  assert.match(client, /browser-owned authority\s*\n?\s*\/\/\s*must never cross/i);
  assert.doesNotMatch(client, /KOLIBRI_V3_BACKEND_URL/);
  assert.doesNotMatch(client, /NEXT_PUBLIC_/);
});

test("AG-UI V1 rejects browser-owned authority state", async () => {
  const [schemaSource, modelSource, exampleSource] = await Promise.all([
    readSource("contracts/v1/chat/ag-ui-run-input.schema.json"),
    readSource("backend/app/chat/models.py"),
    readSource("contracts/v1/chat/examples/valid-ag-ui-run-input.json"),
  ]);
  const schema = JSON.parse(schemaSource);
  const example = JSON.parse(exampleSource);

  assert.deepEqual(schema.properties.state, { type: "null" });
  assert.equal(example.state, null);
  assert.match(modelSource, /^\s*state:\s*None\s*$/m);
  assert.doesNotMatch(modelSource, /^\s*state:\s*dict\[/m);
});

test("same-origin BFF relays cookies and the upstream AG-UI SSE without a demo fallback", async () => {
  const [
    agUiRoute,
    threadRoute,
    messagesRoute,
    mutationRoute,
    resumeRoute,
    cancellationRoute,
    backendHelper,
  ] =
    await Promise.all([
      readSource("app/api/agui/route.ts"),
      readSource("app/api/v3/chat/threads/route.ts"),
      readSource(
        "app/api/v3/chat/threads/[threadId]/messages/route.ts",
      ),
      readSource("app/api/v3/chat/threads/[threadId]/route.ts"),
      readSource("app/api/v3/chat/runs/[runId]/events/route.ts"),
      readSource("app/api/v3/chat/runs/[runId]/cancel/route.ts"),
      readSource("lib/server/v3-backend.ts"),
    ]);

  assert.match(agUiRoute, /["']\/v1\/chat\/ag-ui["']/);
  assert.match(agUiRoute, /text\/event-stream/);
  assert.match(agUiRoute, /\brelayV3BackendResponse\b/);
  assert.doesNotMatch(agUiRoute, /createDemoStream|design-demo/);
  assert.doesNotMatch(agUiRoute, /RUN_STARTED|RUN_FINISHED/);
  assert.doesNotMatch(agUiRoute, /KOLIBRI_AGUI_UPSTREAM_URL/);

  assert.match(threadRoute, /["']\/v1\/chat\/threads["']/);
  assert.match(
    messagesRoute,
    /\/v1\/chat\/threads\/\$\{encodeURIComponent\(threadId\)\}\/messages/,
  );
  assert.match(
    mutationRoute,
    /\/v1\/chat\/threads\/\$\{encodeURIComponent\(threadId\)\}/,
  );
  assert.match(mutationRoute, /method:\s*["']PATCH["']/);
  assert.match(
    resumeRoute,
    /\/v1\/chat\/runs\/\$\{encodeURIComponent\(runId\)\}\/events/,
  );
  assert.match(resumeRoute, /method:\s*["']GET["']/);
  assert.match(
    cancellationRoute,
    /\/v1\/chat\/runs\/\$\{encodeURIComponent\(runId\)\}\/cancel/,
  );
  assert.match(cancellationRoute, /method:\s*["']POST["']/);
  assert.match(cancellationRoute, /maxRequestBytes:\s*0/);

  assert.match(backendHelper, /KOLIBRI_V3_BACKEND_URL/);
  assert.match(backendHelper, /["']authorization["']/);
  assert.match(backendHelper, /["']cookie["']/);
  assert.match(backendHelper, /["']last-event-id["']/);
  assert.match(backendHelper, /["']x-csrf-token["']/);
  assert.match(backendHelper, /["']www-authenticate["']/);
  assert.match(backendHelper, /url\.protocol\s*===\s*["']https:["']/);
  assert.match(backendHelper, /url\.protocol\s*===\s*["']http:["']/);
  assert.match(backendHelper, /["']x-kolibri-run-id["']/);
});
