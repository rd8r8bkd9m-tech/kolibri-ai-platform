import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");

assert.match(app, /VITE_API_BASE/);
assert.match(app, /VITE_WS_BASE/);
assert.match(app, /window\.location\.host/);
assert.doesNotMatch(app, /127\.0\.0\.1:8000/);
assert.doesNotMatch(app, /localhost.*8000/);

console.log("api origin guard passed");
