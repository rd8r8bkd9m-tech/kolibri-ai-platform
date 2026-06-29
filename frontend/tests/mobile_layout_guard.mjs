import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const css = readFileSync(new URL("../src/App.css", import.meta.url), "utf8");

assert.match(css, /--composer-bottom-gap:\s*24px/);
assert.match(css, /--composer-bottom-gap-mobile:\s*28px/);
assert.match(css, /min-height:\s*var\(--app-height,\s*100svh\)/);
assert.match(css, /@supports \(height:\s*100dvh\)/);
assert.match(css, /\.input-area \{ padding: 12px 16px calc\(var\(--composer-bottom-gap-mobile\) \+ var\(--safe-bottom\)\); flex-shrink: 0; position: sticky; bottom: 0; z-index: 10; \}/);
assert.match(css, /--bg-primary:\s*var\(--tg-bg-color,\s*#0a0a0f\)/);

console.log("mobile layout guard passed");
