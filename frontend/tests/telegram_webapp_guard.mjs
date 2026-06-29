import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const app = readFileSync(new URL("../src/App.jsx", import.meta.url), "utf8");
const telegramLib = readFileSync(new URL("../src/lib/telegram.js", import.meta.url), "utf8");
const indexHtml = readFileSync(new URL("../index.html", import.meta.url), "utf8");

assert.match(indexHtml, /telegram-web-app\.js/);
assert.match(app, /bootstrapTelegramWebApp/);
assert.match(app, /getTelegramWebApp\(\)\?\.colorScheme/);
assert.match(app, /if \(!isTelegramMiniapp\) connectWS\(\)/);
assert.match(telegramLib, /viewportChanged/);
assert.match(telegramLib, /themeChanged/);
assert.match(telegramLib, /disableVerticalSwipes/);
assert.match(telegramLib, /--app-height/);
assert.match(telegramLib, /initData/);

console.log("telegram webapp guard passed");
