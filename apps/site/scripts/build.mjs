import { copyFile, mkdir, rm } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const dist = join(root, "dist");

await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });
await copyFile(join(root, "src", "index.html"), join(dist, "index.html"));
await copyFile(join(root, "src", "styles.css"), join(dist, "styles.css"));
await copyFile(join(root, "src", "kolibri-console.svg"), join(dist, "kolibri-console.svg"));
await copyFile(join(root, "..", "..", "CNAME"), join(dist, "CNAME"));

console.log(`built Kolibri site into ${dist}`);
