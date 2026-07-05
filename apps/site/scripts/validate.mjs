import { access, readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const required = [
  "src/index.html",
  "src/styles.css",
  "src/kolibri-console.svg",
];

for (const file of required) {
  await access(join(root, file));
}

const html = await readFile(join(root, "src", "index.html"), "utf8");
for (const marker of ["Kolibri Control Station", "kolibriai.ru", "Rust-first"]) {
  if (!html.includes(marker)) {
    throw new Error(`site is missing required marker: ${marker}`);
  }
}

console.log("site validation passed");
