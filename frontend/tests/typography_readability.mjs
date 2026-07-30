import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/App.css", import.meta.url), "utf8");
const estimateWorkspace = readFileSync(new URL("../src/windows/EstimateWorkspace.jsx", import.meta.url), "utf8");

function pixelToken(name) {
  const match = css.match(new RegExp(`--${name}:\\s*(\\d+)px`));
  assert.ok(match, `missing --${name} typography token`);
  return Number(match[1]);
}

assert.ok(pixelToken("type-body") >= 16, "body copy must stay at least 16px");
assert.ok(pixelToken("type-input") >= 16, "editable text must stay at least 16px");
assert.ok(pixelToken("type-control") >= 15, "control labels must remain readable");
assert.ok(pixelToken("type-label") >= 13, "secondary labels must remain readable");
assert.ok(pixelToken("type-caption") >= 12, "metadata must not collapse into tiny type");

assert.match(css, /body\s*\{[^}]*font-size:\s*var\(--type-body\)/s);
assert.match(css, /\.project-message > div\s*\{[^}]*font-size:\s*var\(--type-body\)[^}]*line-height:\s*var\(--leading-body\)/s);
assert.match(css, /\.composer-input textarea\s*\{[^}]*font-size:\s*var\(--type-input\)/s);
assert.match(css, /\.markdown-result\s*\{[^}]*font-size:\s*var\(--type-body\)/s);
assert.match(css, /\.estimate-workspace\s*\{[^}]*font-size:\s*var\(--type-body\)/s);
assert.match(css, /\.estimate-row input,[\s\S]*?\.estimate-controls input\s*\{[^}]*font-size:\s*var\(--type-input\)/s);
assert.match(css, /@media \(max-width:\s*760px\)[\s\S]*?--type-control:\s*16px;[\s\S]*?--type-label:\s*14px;/s);

assert.match(estimateWorkspace, /function EstimateNumberInput\(props\)/);
const estimateNumberInput = estimateWorkspace.match(/function EstimateNumberInput\(props\)[\s\S]*?\n\}/)?.[0] || "";
assert.match(estimateNumberInput, /className="estimate-number-input"/);
assert.match(estimateNumberInput, /inputMode="decimal"/);
assert.match(estimateNumberInput, /type="text"/);
assert.ok(estimateNumberInput.includes('pattern="[0-9]*[.,]?[0-9]*"'), "decimal editor must validate comma and dot input without native spinner arrows");
assert.equal((estimateWorkspace.match(/<EstimateNumberInput\b/g) || []).length, 4, "all estimate numeric editors must use the shared input primitive");
assert.match(css, /\.estimate-number-input\s*\{[^}]*-moz-appearance:\s*textfield;[^}]*appearance:\s*textfield;/s);
assert.match(css, /\.estimate-number-input::-webkit-inner-spin-button,[\s\S]*?\.estimate-number-input::-webkit-outer-spin-button\s*\{[^}]*-webkit-appearance:\s*none;/s);

const explicitFontSizes = [...css.matchAll(/font-size:\s*(\d+)px/g)].map((match) => Number(match[1]));
assert.ok(explicitFontSizes.every((size) => size >= 12), "the Shell must not reintroduce sub-12px typography");

console.log("Kolibri typography, estimate input readability, and spinner guard passed");
