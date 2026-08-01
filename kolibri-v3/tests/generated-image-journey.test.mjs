import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const APP_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

const readSource = (relativePath) =>
  readFile(path.join(APP_ROOT, relativePath), "utf8");

test("generated images use the authenticated assistant-ui artifact path", async () => {
  const [provider, thread, tool, contentRoute, artifactRoute] =
    await Promise.all([
      readSource("app/MyRuntimeProvider.tsx"),
      Promise.all([
        readSource("components/assistant-ui/thread/parts/thread-layout.tsx"),
        readSource("components/assistant-ui/thread/thread-suggestions-config.ts"),
      ]).then((sources) => sources.join("\n")),
      readSource("components/assistant-ui/generated-image-tool.tsx"),
      readSource(
        "app/api/product/v1/attachments/[attachmentId]/content/route.ts",
      ),
      readSource(
        "app/api/product/v1/artifacts/[artifactId]/versions/[artifactVersion]/route.ts",
      ),
    ]);

  assert.match(provider, /<GeneratedImageToolUI\s*\/>/);
  assert.match(thread, /label:\s*["']Создать изображение["']/);
  assert.match(thread, /prompt:\s*["'][^"']*Создай изображение/);
  assert.match(
    thread,
    /<ThreadPrimitive\.Suggestion[\s\S]{0,240}prompt=\{prompt\}[\s\S]{0,120}send=\{send\}[\s\S]{0,120}clearComposer=\{send\}/,
  );
  assert.match(tool, /toolName:\s*["']generate_image["']/);
  assert.match(tool, /\$type\s*!==\s*["']GeneratedImage["']/);
  assert.match(tool, /schemaId\s*!==\s*["']kolibri\.product\.attachment["']/);
  assert.match(
    tool,
    /\/api\\\/product\\\/v1\\\/attachments\\\/attachment_/,
  );
  assert.match(tool, /value\.contentPath\s*!==/);
  assert.match(tool, /value\.status\s*!==\s*["']available["']/);
  assert.doesNotMatch(tool, /data:image\//);
  assert.doesNotMatch(tool, /\bbase64\b/i);
  assert.doesNotMatch(tool, /https?:\/\/.*(?:openai|provider)/i);

  assert.match(contentRoute, /SAFE_ATTACHMENT_ID/);
  assert.match(
    contentRoute,
    /`\/v1\/attachments\/\$\{encodeURIComponent\(attachmentId\)\}\/content`/,
  );
  assert.match(contentRoute, /\bfetchV3Backend\b/);
  assert.match(contentRoute, /\brelayV3BackendResponse\b/);

  assert.match(artifactRoute, /SAFE_ARTIFACT_ID/);
  assert.match(artifactRoute, /SAFE_ARTIFACT_VERSION/);
  assert.match(
    artifactRoute,
    /`\/v1\/artifacts\/\$\{encodeURIComponent\(artifactId\)\}\/versions\/`/,
  );
  assert.match(artifactRoute, /\bproxyV3JsonRequest\b/);
});
