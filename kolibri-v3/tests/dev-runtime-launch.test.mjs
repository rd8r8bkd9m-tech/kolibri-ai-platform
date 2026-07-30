import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const backendLauncher = readFileSync(
  new URL("../scripts/dev-backend.sh", import.meta.url),
  "utf8",
);
const stackSupervisor = readFileSync(
  new URL("../scripts/dev-stack.mjs", import.meta.url),
  "utf8",
);
const blockedWebLauncher = readFileSync(
  new URL("../scripts/dev-web-blocked.mjs", import.meta.url),
  "utf8",
);
const persistentLauncher = readFileSync(
  new URL("../scripts/dev-persistent.sh", import.meta.url),
  "utf8",
);
const screenEntry = readFileSync(
  new URL("../scripts/dev-screen-entry.sh", import.meta.url),
  "utf8",
);
const backendApplication = readFileSync(
  new URL("../backend/app/main.py", import.meta.url),
  "utf8",
);
const packageManifest = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url), "utf8"),
);

test("canonical backend launcher pins the V3 database and auth surface", () => {
  assert.match(
    backendLauncher,
    /KOLIBRI_V3_DATABASE_URL='sqlite:\/\/\/\.\/var\/kolibri-v3\.db'/,
  );
  assert.match(backendLauncher, /KOLIBRI_V3_DIRECT_MODEL_RUNTIME=true/);
  assert.match(backendLauncher, /KOLIBRI_V3_DEVELOPER_AGENT_ENABLED=true/);
  assert.match(backendLauncher, /KOLIBRI_V3_COOKIE_SECURE=false/);
  assert.match(
    backendLauncher,
    /KOLIBRI_V3_SESSION_COOKIE_NAME='kolibri_v3_session'/,
  );
  assert.match(backendLauncher, /unset KOLIBRI_V3_CSRF_SECRET_FILE/);
  assert.match(backendLauncher, /KOLIBRI_V3_DEV_OWNER_EMAIL/);
  assert.match(backendLauncher, /--expected-owner-email/);
});

test("migration and owner preflight runs before uvicorn opens the port", () => {
  const preflight = backendLauncher.indexOf("-m app.dev_preflight");
  const uvicorn = backendLauncher.indexOf("-m uvicorn");

  assert.ok(preflight >= 0);
  assert.ok(uvicorn > preflight);
});

test("dev stack restarts only the canonical backend launcher", () => {
  assert.match(
    stackSupervisor,
    /spawn\("\/bin\/bash", \["scripts\/dev-backend\.sh"\]/,
  );
  assert.match(stackSupervisor, /scheduleRestart\(startBackend\)/);
  assert.match(
    stackSupervisor,
    /KOLIBRI_V3_BACKEND_URL: "http:\/\/127\.0\.0\.1:8002"/,
  );
  assert.match(stackSupervisor, /path: "\/v1\/health"/);
  assert.match(stackSupervisor, /payload\.service === "kolibri-v3"/);
  assert.match(
    stackSupervisor,
    /payload\.instanceId === devInstanceId/,
  );
  assert.match(
    stackSupervisor,
    /KOLIBRI_V3_DEV_INSTANCE_ID: devInstanceId/,
  );
  assert.match(
    backendApplication,
    /os\.getenv\(\s*"KOLIBRI_V3_DEV_INSTANCE_ID"/,
  );
  assert.match(
    backendApplication,
    /payload\["instanceId"\] = dev_instance_id/,
  );
  assert.match(
    stackSupervisor,
    /healthy &&[\s\S]*backend\.exitCode === null[\s\S]*startWeb\(\)/,
  );
  assert.match(
    stackSupervisor,
    /backend\.once\("exit"[\s\S]*backendReady = false;[\s\S]*web\?\.kill\("SIGTERM"\)/,
  );
  assert.match(
    stackSupervisor,
    /if \(stopping \|\| web \|\| !backendReady\)/,
  );
  assert.match(
    stackSupervisor,
    /if \(backendReady\)[\s\S]*scheduleRestart\(startWeb\)[\s\S]*else[\s\S]*scheduleReadinessProbe\(\)/,
  );
  assert.doesNotMatch(stackSupervisor, /startBackend\(\);\s*startWeb\(\);/);
  assert.doesNotMatch(stackSupervisor, /launchctl|Logical Home/);
});

test("the default dev command cannot bypass the canonical V3 stack", () => {
  assert.equal(packageManifest.scripts.dev, "node scripts/dev-stack.mjs");
  assert.equal(
    packageManifest.scripts["dev:backend"],
    "bash scripts/dev-backend.sh",
  );
  assert.equal(
    packageManifest.scripts["dev:web"],
    "node scripts/dev-web-blocked.mjs",
  );
  assert.match(blockedWebLauncher, /frontend-only development is disabled/);
  assert.match(blockedWebLauncher, /npm run dev/);
  assert.match(blockedWebLauncher, /migrations, owner preflight/);
  assert.match(blockedWebLauncher, /process\.exitCode = 2/);

  for (const [name, command] of Object.entries(packageManifest.scripts)) {
    if (name === "dev:backend") {
      continue;
    }
    assert.doesNotMatch(command, /\buvicorn\b/);
    assert.doesNotMatch(command, /\bnext dev\b/);
  }
});

test("persistent development delegates only to the canonical supervisor", () => {
  assert.equal(
    packageManifest.scripts["dev:persistent"],
    "bash scripts/dev-persistent.sh start",
  );
  assert.match(persistentLauncher, /session_name="kolibri-v3-dev"/);
  assert.match(persistentLauncher, /\/bin\/bash "\$\{screen_entry\}"/);
  assert.match(screenEntry, /exec "\$\{npm_bin\}" run dev/);
  assert.match(screenEntry, />>"\$\{runtime_log\}" 2>&1/);
  assert.match(persistentLauncher, /'"service":"kolibri-v3"'/);
  assert.match(persistentLauncher, /'"instanceId":"'/);
  assert.match(persistentLauncher, /session_process_group/);
  assert.match(persistentLauncher, /kill -TERM -- "-\$\{process_group\}"/);
  assert.match(
    persistentLauncher,
    /! session_exists && runtime_ports_free/,
  );
  assert.doesNotMatch(persistentLauncher, /\buvicorn\b/);
  assert.doesNotMatch(persistentLauncher, /\bnext dev\b/);
  assert.doesNotMatch(persistentLauncher, /launchctl|LaunchAgent/);
});
