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
  ).href,
);

const timestamp = "2026-07-30T10:20:30.000Z";
const attachmentPart = {
  type: "document",
  source: {
    type: "url",
    value:
      "/api/product/v1/attachments/attachment_contract000001/content",
    mimeType: "text/csv",
  },
  metadata: { filename: "данные.csv" },
};

test("strict Product Chat history preserves only canonical attachment refs", () => {
  const page = {
    threadId: "thread_attachment_contract01",
    messages: [
      {
        id: "message_attachment_contract01",
        role: "user",
        content: [
          { type: "text", text: "Проанализируй файл." },
          attachmentPart,
        ],
        createdAt: timestamp,
        status: { type: "complete", reason: "stop" },
        submittedFeedback: null,
      },
    ],
    nextCursor: null,
  };
  assert.deepEqual(
    contracts.parseProductChatMessagePage(
      page,
      "thread_attachment_contract01",
    ),
    page,
  );

  assert.throws(
    () =>
      contracts.parseProductChatMessagePage(
        {
          ...page,
          messages: [
            {
              ...page.messages[0],
              content: [
                page.messages[0].content[0],
                {
                  ...attachmentPart,
                  source: {
                    ...attachmentPart.source,
                    value: "data:text/csv;base64,ZmFrZQ==",
                  },
                },
              ],
            },
          ],
        },
        "thread_attachment_contract01",
      ),
    contracts.ProductChatContractError,
  );
});

test("assistant-ui attachment capability is backend-gated and never fakes upload success", async () => {
  const [provider, adapter, client, uploadRoute, contentRoute, backend] =
    await Promise.all([
      readSource("app/MyRuntimeProvider.tsx"),
      readSource("lib/product-chat/attachments.ts"),
      readSource("lib/product-chat/client.ts"),
      readSource("app/api/product/v1/attachments/route.ts"),
      readSource(
        "app/api/product/v1/attachments/[attachmentId]/content/route.ts",
      ),
      readSource("lib/server/v3-backend.ts"),
    ]);

  assert.match(provider, /\bloadProductAttachmentCapability\b/);
  assert.match(provider, /setAttachmentCapability\(null\)/);
  assert.match(
    provider,
    /attachmentCapability\s*\?\s*createProductChatAttachmentAdapter/,
  );
  assert.match(provider, /adapters:\s*\{[\s\S]{0,80}\battachments\b/);

  assert.match(
    adapter,
    /PRODUCT_ATTACHMENT_R1_MAX_BYTES\s*=\s*10\s*\*\s*1024\s*\*\s*1024/,
  );
  assert.match(adapter, /credentials:\s*["']same-origin["']/);
  assert.match(adapter, /\bwithCsrfHeader\b/);
  assert.match(adapter, /["']Idempotency-Key["']:\s*attachmentId/);
  assert.match(adapter, /["']X-Kolibri-Project-Id["']/);
  assert.match(adapter, /["']X-Kolibri-Thread-Id["']/);
  assert.match(adapter, /error\.status\s*>=\s*500/);
  assert.match(adapter, /content:\s*\[\s*\{/);
  assert.match(adapter, /status:\s*\{\s*type:\s*["']requires-action["']/);
  assert.match(adapter, /if\s*\(!attachment\.content\?\.length\)/);
  assert.doesNotMatch(adapter, /FileReader/);
  assert.doesNotMatch(adapter, /readAsDataURL/);
  assert.doesNotMatch(adapter, /\bbase64\b/i);

  assert.match(client, /\bnormalizeAttachmentUrl\b/);
  assert.match(client, /ATTACHMENT_CONTENT_PATH/);
  assert.match(client, /parsed\.origin\s*!==\s*globalThis\.location\.origin/);
  assert.match(client, /content\.some\(\(part\)\s*=>\s*part\s*===\s*null\)/);

  assert.match(uploadRoute, /body:\s*request\.body/);
  assert.match(uploadRoute, /R1_ATTACHMENT_MAX_BYTES/);
  assert.doesNotMatch(uploadRoute, /arrayBuffer\(\)/);
  assert.match(contentRoute, /\bSAFE_ATTACHMENT_ID\b/);
  assert.match(contentRoute, /\brelayV3BackendResponse\b/);
  assert.match(backend, /["']x-kolibri-filename["']/);
  assert.match(backend, /["']x-kolibri-project-id["']/);
  assert.match(backend, /["']x-kolibri-thread-id["']/);
  assert.match(backend, /duplex\s*=\s*["']half["']/);
});
