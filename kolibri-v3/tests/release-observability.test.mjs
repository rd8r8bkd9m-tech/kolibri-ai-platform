import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const APP_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

async function loadLiveRoute() {
  const routePath = path.join(APP_ROOT, "app/api/live/route.ts");
  const source = await readFile(routePath, "utf8");
  const executable = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ESNext,
    },
    fileName: routePath,
  }).outputText;
  return import(
    `data:text/javascript;base64,${Buffer.from(executable).toString("base64")}`
  );
}

test("frontend liveness is process-local, bounded, and bodyless for HEAD", async () => {
  const route = await loadLiveRoute();
  const get = await route.GET();
  const head = await route.HEAD();

  assert.equal(get.status, 200);
  assert.deepEqual(await get.json(), {
    status: "ok",
    service: "kolibri-v3",
    component: "frontend",
  });
  assert.equal(get.headers.get("cache-control"), "no-store, max-age=0");
  assert.equal(head.status, 200);
  assert.equal(await head.text(), "");
});

test("frontend responses bind the public release header", async () => {
  const nextConfig = await readFile(
    path.join(APP_ROOT, "next.config.ts"),
    "utf8",
  );

  assert.match(nextConfig, /X-Kolibri-Release/);
  assert.match(nextConfig, /KOLIBRI_RELEASE_ID/);
  assert.match(nextConfig, /unversioned/);
  assert.doesNotMatch(nextConfig, /KOLIBRI_RELEASE_COMMIT.*headers/);
});

test("portable Nginx probes the application instead of returning static health", async () => {
  const installer = await readFile(
    path.join(APP_ROOT, "deploy/portable/install.sh"),
    "utf8",
  );

  assert.doesNotMatch(
    installer,
    /location\s*=\s*\/healthz[^{]*\{[^}]*return\s+200/s,
  );
  assert.match(installer, /location = \/livez[\s\S]+\/api\/live/);
  assert.match(installer, /location = \/readyz[\s\S]+\/api\/health/);
  assert.match(installer, /location = \/healthz[\s\S]+\/api\/health/);
  assert.match(installer, /--no-access-log/);
});

test("portable release installs fail-closed monitoring and verified backup timers", async () => {
  const installer = await readFile(
    path.join(APP_ROOT, "deploy/portable/install.sh"),
    "utf8",
  );
  const installContract = await readFile(
    path.join(APP_ROOT, "deploy/portable/install-contract.py"),
    "utf8",
  );
  const monitor = await readFile(
    path.join(APP_ROOT, "backend/app/release_monitor.py"),
    "utf8",
  );
  const unitSource = `${installer}\n${installContract}`;

  assert.match(installer, /render-operations/);
  assert.match(unitSource, /app[.]release_monitor/);
  assert.match(unitSource, /release-monitor[.]service/);
  assert.match(unitSource, /release-monitor[.]timer/);
  assert.match(unitSource, /OnUnitActiveSec=60s/);
  assert.match(unitSource, /database-backup[.]service/);
  assert.match(unitSource, /database-backup[.]timer/);
  assert.match(unitSource, /scheduled-backup/);
  assert.match(unitSource, /OnFailure=.*release-monitor[.]service/);
  assert.match(installer, /install_error=release_monitor_failed/);
  assert.match(installer, /systemctl enable --now .*release-monitor[.]timer/);
  assert.match(installer, /systemctl enable --now .*database-backup[.]timer/);

  for (const code of [
    "public_down",
    "backend_not_ready",
    "product_worker_stopped",
    "error_rate_spike",
    "stuck_runs",
    "disk_space_low",
    "database_backup_job_failed",
    "database_backup_stale",
    "tls_expiring",
  ]) {
    assert.match(monitor, new RegExp(code));
  }
  assert.match(monitor, /p95DurationMs/);
  assert.match(monitor, /productQueueDepth/);
  assert.match(monitor, /directQueueDepth/);
  assert.doesNotMatch(monitor, /print\(.*(?:url|path|prompt|cookie|token)/i);
});
