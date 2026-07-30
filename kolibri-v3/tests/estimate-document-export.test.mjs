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

test("saved estimates expose one-click native PDF sharing and document exports", async () => {
  const [widgetSource, threadSource, shareSource, routeSource] = await Promise.all([
    readSource("components/assistant-ui/product-widgets.tsx"),
    readSource("components/assistant-ui/thread.tsx"),
    readSource("lib/estimate-share.ts"),
    readSource(
      "app/api/v3/projects/[projectId]/estimate/export/[format]/route.ts",
    ),
  ]);

  assert.match(
    shareSource,
    /ESTIMATE_SHARE_FORMAT = "pdf" as const/,
  );
  assert.match(shareSource, /async function prepareEstimateShareFiles\(/);
  assert.match(shareSource, /credentials:\s*"same-origin"/);
  assert.match(
    shareSource,
    /contentType !== ESTIMATE_SHARE_MEDIA_TYPE/,
  );
  assert.match(shareSource, /async function sharePreparedEstimateFiles\(/);
  assert.match(shareSource, /navigator\.canShare\(payload\)/);
  assert.match(shareSource, /\.\.\.shareData/);
  assert.match(shareSource, /files: prepared\.files/);
  assert.match(threadSource, /part\.args\.\$type !== "EstimateEditor"/);
  assert.match(threadSource, /prepareEstimateShareFiles\(/);
  assert.match(threadSource, /sharePreparedEstimateFiles\(/);
  assert.match(threadSource, /<AssistantMessageShareAction \/>/);
  assert.match(threadSource, /<AssistantMessageDownloadAction \/>/);
  assert.doesNotMatch(widgetSource, /EstimateShareButton/);
  assert.doesNotMatch(widgetSource, /shareEstimate|shareSavedEstimate/);
  assert.doesNotMatch(widgetSource, /Поделиться файлами/);
  assert.match(widgetSource, />\s*Word\s*</);
  assert.match(
    routeSource,
    /"pdf",\s*"xlsx",\s*"docx",\s*"csv",\s*"zip"/,
  );
});

test("assistant messages expose direct assistant-ui actions", async () => {
  const threadSource = await readSource("components/assistant-ui/thread.tsx");

  assert.match(threadSource, /autohide="never"/);
  assert.match(threadSource, /<ActionBarPrimitive\.Copy/);
  assert.match(threadSource, /<AssistantMessageShareAction \/>/);
  assert.match(threadSource, /<ActionBarPrimitive\.ExportMarkdown/);
  assert.match(threadSource, /<ActionBarPrimitive\.FeedbackPositive/);
  assert.match(threadSource, /<ActionBarPrimitive\.FeedbackNegative/);
  assert.match(threadSource, /<ActionBarPrimitive\.Reload/);
  assert.doesNotMatch(threadSource, /ActionBarMorePrimitive/);
});
