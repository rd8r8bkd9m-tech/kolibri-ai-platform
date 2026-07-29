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

test("assistant messages use the official bounded Streamdown renderer", async () => {
  const markdown = await readSource(
    "components/assistant-ui/markdown-text.tsx",
  );

  assert.match(
    markdown,
    /StreamdownTextPrimitive[\s\S]*mode=["']streaming["']/,
  );

  for (const plugin of ["cjk", "code", "math", "mermaid"]) {
    assert.match(
      markdown,
      new RegExp(`RICH_TEXT_PLUGINS[\\s\\S]*\\b${plugin}\\b`),
    );
  }

  assert.match(markdown, /shikiTheme=\{\["github-light", "github-dark"\]\}/);
  assert.match(markdown, /\bdefer\b/);
  assert.match(markdown, /\bsmooth=\{false\}/);
  assert.match(markdown, /\banimated=\{false\}/);
  assert.doesNotMatch(markdown, /\bcaret=/);

  assert.match(markdown, /code:\s*\{[\s\S]*copy:\s*true[\s\S]*download:\s*false/);
  assert.match(markdown, /table:\s*false/);
  assert.match(
    markdown,
    /mermaid:\s*\{[\s\S]*copy:\s*true[\s\S]*download:\s*true[\s\S]*fullscreen:\s*false[\s\S]*panZoom:\s*false/,
  );
  assert.match(markdown, /\bExternalLinkSafetyDialog\b/);
  assert.match(markdown, /renderModal:\s*\(props\)/);
});

test("rich message content is constrained before it reaches the DOM", async () => {
  const markdown = await readSource(
    "components/assistant-ui/markdown-text.tsx",
  );

  assert.match(markdown, /securityLevel:\s*"strict"/);
  assert.match(markdown, /maxTextSize:\s*12_000/);
  assert.match(markdown, /maxEdges:\s*200/);
  assert.match(markdown, /allowedProtocols:\s*\["https", "mailto"\]/);
  assert.match(markdown, /allowedImagePrefixes:\s*\[\]/);
  assert.match(markdown, /allowDataImages:\s*false/);
  assert.match(markdown, /disallowedElements=\{\["img"\]\}/);
  assert.match(markdown, /\bskipHtml\b/);
  assert.match(markdown, /allowDangerousHtml:\s*false/);
  assert.doesNotMatch(markdown, /dangerouslySetInnerHTML/);
});

test("Streamdown package styles are discoverable and KaTeX is loaded once", async () => {
  const [globals, layout] = await Promise.all([
    readSource("app/globals.css"),
    readSource("app/layout.tsx"),
  ]);

  for (const source of [
    "streamdown/dist/*.js",
    "@streamdown/cjk/dist/*.js",
    "@streamdown/code/dist/*.js",
    "@streamdown/math/dist/*.js",
    "@streamdown/mermaid/dist/*.js",
  ]) {
    assert.ok(globals.includes(source), `missing Tailwind source: ${source}`);
  }

  assert.match(layout, /import\s+["']katex\/dist\/katex\.min\.css["']/);
});

test("Kolibri workflow stages never expose raw tool JSON in the chat", async () => {
  const fallback = await readSource(
    "components/assistant-ui/tool-fallback.tsx",
  );

  for (const toolName of [
    "project_case_analysis",
    "technology_card_build",
    "price_candidates_apply",
    "price_candidates_verify",
    "estimate_engine_calculate",
    "estimate_verification",
  ]) {
    assert.match(fallback, new RegExp(`["']${toolName}["']`));
  }

  assert.match(
    fallback,
    /const ToolFallbackImpl:[\s\S]*return <ProductToolStatus/,
  );
  const productToolStatus = fallback.slice(
    fallback.indexOf("function ProductToolStatus"),
    fallback.indexOf("function ToolFallbackContent"),
  );
  const defaultFallback = fallback.slice(
    fallback.indexOf("const ToolFallbackImpl"),
    fallback.indexOf("const ToolFallback = memo"),
  );
  assert.doesNotMatch(productToolStatus, /ToolFallbackArgs/);
  assert.doesNotMatch(productToolStatus, /ToolFallbackResult/);
  assert.doesNotMatch(productToolStatus, /JSON\.stringify/);
  assert.doesNotMatch(defaultFallback, /<ToolFallbackArgs/);
  assert.doesNotMatch(defaultFallback, /<ToolFallbackResult/);
  assert.doesNotMatch(defaultFallback, /<ToolFallbackApproval/);
});
