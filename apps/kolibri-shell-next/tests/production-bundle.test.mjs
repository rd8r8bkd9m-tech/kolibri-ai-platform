import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, readdir } from "node:fs/promises";
import { extname, resolve } from "node:path";
import test from "node:test";

const root = resolve(import.meta.dirname, "..");
const dist = resolve(root, "dist");

async function files(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const found = [];
  for (const entry of entries) {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) found.push(...await files(path));
    else found.push(path);
  }
  return found;
}

test("production bundle contains no development fixture", async () => {
  const textFiles = (await files(dist)).filter((file) => [".html", ".js", ".css", ".map"].includes(extname(file)));
  const bundle = (await Promise.all(textFiles.map((file) => readFile(file, "utf8")))).join("\n");
  assert.doesNotMatch(bundle, /KOLIBRI_VISUAL_FIXTURE_V1_DEV_ONLY/);
  assert.doesNotMatch(bundle, /гамбургер динамично меняется/);
  assert.doesNotMatch(bundle, /Смета_дом_100м2_Лениногорск/);
  assert.doesNotMatch(bundle, /apps\/kolibri-shell(?:\/|["'])/);
  assert.doesNotMatch(bundle, /\.\.\/\.\.\/frontend/);
});

test("production contains the approved bird bytes", async () => {
  const bird = await readFile(resolve(dist, "kolibri-bird.png"));
  assert.equal(
    createHash("sha256").update(bird).digest("hex"),
    "6f30357f75c963e5e4d85b464b10eadb2545d2a6b40aced54861571c4322c3d7",
  );
});
