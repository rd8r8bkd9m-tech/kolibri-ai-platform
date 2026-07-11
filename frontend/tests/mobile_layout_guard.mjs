import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/App.css", import.meta.url), "utf8");
const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");

assert.match(css, /--composer-bottom-gap:\s*18px/);
assert.match(css, /--composer-bottom-gap-mobile:\s*14px/);
assert.match(css, /min-height:\s*100svh/);
assert.match(css, /@supports \(height:\s*100dvh\)/);
assert.match(css, /@media \(max-width:\s*760px\)/);
assert.match(css, /\.workbench-body\s*\{[^}]*overflow:\s*hidden/s);
assert.match(css, /\.stage-canvas,[\s\S]*?\.mobile-stage\s*\{[^}]*position:\s*relative/s);
assert.match(css, /\.composer-layer\s*\{[^}]*position:\s*absolute/s);
assert.match(css, /\.mobile-window\s*\{/);
assert.match(css, /\.composer-layer\s*\{[^}]*var\(--safe-bottom\)/s);
assert.match(css, /\.floating-composer \.composer-send\s*\{[^}]*width:\s*44px[^}]*height:\s*44px/s);
assert.match(css, /@media \(max-width:\s*760px\)[\s\S]*?\.tool-dock\s*\{[^}]*display:\s*none/s);
assert.match(css, /@media \(max-width:\s*760px\)[\s\S]*?\.mobile-stage\s*\{[^}]*width:\s*100%/s);
assert.match(css, /@media \(prefers-reduced-motion:\s*reduce\)/);
assert.match(css, /button:focus-visible/);
assert.doesNotMatch(html, /user-scalable=no/);
assert.doesNotMatch(html, /maximum-scale=1/);
assert.match(html, /href="\/kolibri-bird\.png"/);

console.log("Kolibri responsive layout and accessibility guard passed");
