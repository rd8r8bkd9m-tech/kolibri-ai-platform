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

test("message timing is a quiet assistant-ui action-bar detail", async () => {
  const [component, thread] = await Promise.all([
    readSource("components/assistant-ui/message-timing.tsx"),
    readSource("components/assistant-ui/thread.tsx"),
  ]);

  assert.match(component, /\buseMessageTiming\b/);
  assert.match(component, /timing\?\.totalStreamTime\s*===\s*undefined/);
  assert.match(component, /Клиентское измерение текущей сессии/);
  assert.match(component, /Скорость, оценка/);
  assert.match(component, /aria-label=["']Статистика ответа["']/);
  assert.match(thread, /<MessageTiming\s+side=["']bottom["']\s*\/>/);
});
