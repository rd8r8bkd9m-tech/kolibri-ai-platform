import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const css = readFileSync(new URL("../src/App.css", import.meta.url), "utf8");

function stripCssComments(source) {
  let output = "";
  let cursor = 0;

  while (cursor < source.length) {
    const commentStart = source.indexOf("/*", cursor);
    if (commentStart === -1) {
      output += source.slice(cursor);
      break;
    }

    output += source.slice(cursor, commentStart);
    const commentEnd = source.indexOf("*/", commentStart + 2);
    assert.notEqual(commentEnd, -1, "CSS contains an unterminated comment");
    cursor = commentEnd + 2;
  }

  return output;
}

const activeCss = stripCssComments(css);

assert.match(activeCss, /--composer-bottom-gap:\s*24px/);
assert.match(activeCss, /--composer-bottom-gap-mobile:\s*28px/);
assert.match(activeCss, /min-height:\s*100svh/);
assert.match(activeCss, /@supports \(height:\s*100dvh\)/);
assert.match(activeCss, /\.input-area \{ padding: 12px 16px calc\(var\(--composer-bottom-gap-mobile\) \+ var\(--safe-bottom\)\); flex-shrink: 0; position: sticky; bottom: 0; z-index: 10; \}/);
assert.match(activeCss, /\.kolibri-avatar\s*\{/);

console.log("mobile layout guard passed");
