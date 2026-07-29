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

test("browser mutations use the bounded public double-submit CSRF cookie", async () => {
  const [csrf, identity, providers, chat] = await Promise.all([
    readSource("lib/csrf.ts"),
    readSource("lib/identity/client.ts"),
    readSource("lib/providers/client.ts"),
    readSource("lib/product-chat/client.ts"),
  ]);

  assert.match(csrf, /kolibri_v3_csrf/);
  assert.match(csrf, /typeof\s+document\s*===\s*["']undefined["']/);
  assert.match(csrf, /SAFE_CSRF_TOKEN/);
  assert.match(csrf, /result\.set\(["']x-csrf-token["'],\s*token\)/);
  assert.doesNotMatch(csrf, /localStorage|sessionStorage/);

  for (const source of [identity, providers]) {
    assert.match(source, /\bwithCsrfHeader\b/);
    assert.match(
      source,
      /method\s*===\s*["']GET["']\s*\|\|\s*method\s*===\s*["']HEAD["']/,
    );
  }

  assert.match(chat, /const headers = withCsrfHeader\(init\?\.headers\)/);
  assert.match(chat, /forwardedProps:\s*\{[\s\S]*?agentProfile:/);
  assert.match(chat, /\.\.\.\(accessMode\s*===\s*["']standard["']/);
  assert.match(chat, /getAccessMode/);
  assert.doesNotMatch(chat, /kolibriAgentProfile/);
});
