import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";

const assetDirectory = new URL("../dist/assets/", import.meta.url);
const javascript = readdirSync(assetDirectory)
  .filter((name) => name.endsWith(".js"))
  .map((name) => readFileSync(new URL(name, assetDirectory), "utf8"))
  .join("\n");
const forbiddenEnglishFallback = new RegExp(["Kolibri could not produce", "a verified response"].join(" "), "i");
const forbiddenRussianDeadline = new RegExp([
  "Исполнители не успели завершить ответ",
  "в отведённое время",
].join(" "), "i");
const unimplementedClaim = new RegExp(["coming", "soon"].join(" "), "i");

assert.doesNotMatch(javascript, forbiddenEnglishFallback);
assert.doesNotMatch(javascript, forbiddenRussianDeadline);
assert.doesNotMatch(javascript, unimplementedClaim);

console.log("Kolibri production bundle contains no forbidden fallback or unimplemented capability claim");
