import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const backendLauncher = readFileSync(
  new URL("../scripts/dev-backend.sh", import.meta.url),
  "utf8",
);
const mobileLauncher = readFileSync(
  new URL("../scripts/dev-mobile.mjs", import.meta.url),
  "utf8",
);
const stackSupervisor = readFileSync(
  new URL("../scripts/dev-stack.mjs", import.meta.url),
  "utf8",
);
const uiGateway = readFileSync(
  new URL("../scripts/dev-ui-gateway.mjs", import.meta.url),
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
const homePreviewLauncher = readFileSync(
  new URL("../scripts/home-preview-frontend.mjs", import.meta.url),
  "utf8",
);
const homePreviewService = readFileSync(
  new URL("../scripts/kolibri-v3-home-preview.service", import.meta.url),
  "utf8",
);
const mobileEnvironment = readFileSync(
  new URL("../components/kolibri-shell/mobile-environment.tsx", import.meta.url),
  "utf8",
);
const appPage = readFileSync(
  new URL("../app/app/page.tsx", import.meta.url),
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
  assert.match(
    backendLauncher,
    /KOLIBRI_V3_ALLOWED_ORIGINS=.*127\.0\.0\.1:4103.*localhost:4103/,
  );
  assert.match(backendLauncher, /--reload/);
  assert.match(
    backendLauncher,
    /--reload-dir "\$\{v3_root\}\/backend"/,
  );
});

test("mobile development has one explicit Expo runtime and shared V3 backend", () => {
  assert.equal(packageManifest.scripts["dev:mobile"], "node scripts/dev-mobile.mjs");
  assert.match(mobileLauncher, /apps.*kolibri-mobile/);
  assert.match(mobileLauncher, /"--host"[\s\S]*mobileHost/);
  assert.match(mobileLauncher, /"--port"[\s\S]*String\(mobilePort\)/);
  assert.match(mobileLauncher, /http:\/\/127\.0\.0\.1:8002/);
  assert.match(mobileLauncher, /KOLIBRI_V3_MOBILE_API_BASE_URL/);
  assert.match(mobileLauncher, /3103 and 4103 are UI ports/);
  assert.doesNotMatch(mobileLauncher, /EXPO_PUBLIC_API_BASE_URL\?\.trim/);
  assert.match(mobileLauncher, /public UI origin is 3103/);
});

test("desktop app hands mobile-sized /app routes to the same UI origin", () => {
  assert.match(mobileEnvironment, /searchParams\.set\("client", "mobile"\)/);
  assert.match(mobileEnvironment, /max-width: 959px/);
  assert.match(mobileEnvironment, /window\.location\.replace\(mobileAppUrl\(\)\)/);
  assert.match(mobileEnvironment, /DESKTOP_APP_PATH\.test\(window\.location\.pathname\)/);
  assert.doesNotMatch(mobileEnvironment, /NEXT_PUBLIC_MOBILE_APP_ORIGIN/);
  assert.doesNotMatch(mobileEnvironment, /:4103/);
});

test("the desktop app route redirects mobile requests before rendering", () => {
  assert.match(appPage, /await headers\(\)/);
  assert.match(appPage, /sec-ch-ua-mobile/);
  assert.match(appPage, /MOBILE_USER_AGENT/);
  assert.match(appPage, /redirect\("\/app\?client=mobile"\)/);
  assert.match(appPage, /return <KolibriApp \/>/);
});

test("the UI gateway keeps desktop and mobile on one public origin", () => {
  assert.match(uiGateway, /KOLIBRI_V3_UI_PORT.*3103/);
  assert.match(uiGateway, /KOLIBRI_V3_DESKTOP_INTERNAL_PORT.*3104/);
  assert.match(uiGateway, /KOLIBRI_V3_MOBILE_INTERNAL_PORT[\s\S]*4103/);
  assert.match(uiGateway, /KOLIBRI_V3_MOBILE_INTERNAL_HOST/);
  assert.match(uiGateway, /client.*mobile/);
  assert.match(uiGateway, /sec-ch-ua-mobile/);
  assert.match(uiGateway, /mobileUserAgent/);
  assert.match(uiGateway, /url\.pathname\.slice\("\/app"\.length\)/);
  assert.match(uiGateway, /server\.on\("upgrade", proxyUpgrade\)/);
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
  assert.match(stackSupervisor, /KOLIBRI_V3_DESKTOP_INTERNAL_PORT[\s\S]*3104/);
  assert.match(stackSupervisor, /KOLIBRI_V3_MOBILE_INTERNAL_PORT[\s\S]*4103/);
  assert.match(stackSupervisor, /KOLIBRI_V3_MOBILE_HOST: "localhost"/);
  assert.match(stackSupervisor, /KOLIBRI_V3_MOBILE_INTERNAL_HOST: "::1"/);
  assert.match(stackSupervisor, /KOLIBRI_V3_UI_PORT[\s\S]*3103/);
  assert.match(stackSupervisor, /mobileLauncher = path\.join[\s\S]*dev-mobile\.mjs/);
  assert.match(stackSupervisor, /gatewayLauncher = path\.join[\s\S]*dev-ui-gateway\.mjs/);
  assert.match(stackSupervisor, /path: "\/v1\/health"/);
  assert.match(stackSupervisor, /payload\.service === "kolibri-v3"/);
  assert.match(
    stackSupervisor,
    /payload\.instanceId === devInstanceId/,
  );
  assert.match(stackSupervisor, /payload\.sourceRoot === v3Root/);
  assert.match(
    stackSupervisor,
    /payload\.agentRuntimeContract === agentRuntimeContract/,
  );
  assert.match(
    stackSupervisor,
    /agentRuntimeContract = "kolibri\.agent-runtime@1\.1"/,
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
    backendApplication,
    /payload\["sourceRoot"\] = str\(Path\(__file__\)\.resolve\(\)\.parents\[2\]\)/,
  );
  assert.match(backendApplication, /AGENT_RUNTIME_SCHEMA_ID/);
  assert.match(backendApplication, /AGENT_RUNTIME_SCHEMA_VERSION/);
  assert.match(
    stackSupervisor,
    /healthy &&[\s\S]*backend\.exitCode === null[\s\S]*startWeb\(\)/,
  );
  assert.match(stackSupervisor, /startMobile\(\);/);
  assert.match(stackSupervisor, /startGateway\(\);/);
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
  assert.match(
    persistentLauncher,
    /'"agentRuntimeContract":"kolibri\.agent-runtime@1\.1"'/,
  );
  assert.match(persistentLauncher, /\\"sourceRoot\\":\\"\$\{v3_root\}\\"/);
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

test("Home HMR preview always recovers after an unexpected Next exit", () => {
  assert.equal(
    packageManifest.scripts["preview:home:web"],
    "node scripts/home-preview-frontend.mjs",
  );
  assert.match(homePreviewLauncher, /previewHost = "127\.0\.0\.2"/);
  assert.match(
    homePreviewLauncher,
    /productionBackend = "http:\/\/127\.0\.0\.1:8002"/,
  );
  assert.match(homePreviewLauncher, /KOLIBRI_HOME_PREVIEW_CONFIRM/);
  assert.match(homePreviewLauncher, /if \(stopping\)[\s\S]*process\.exit\(0\)/);
  assert.match(homePreviewLauncher, /process\.exit\(1\)/);
  assert.match(homePreviewService, /Restart=always/);
  assert.match(homePreviewService, /StartLimitIntervalSec=0/);
  assert.match(
    homePreviewService,
    /WorkingDirectory=\/opt\/kolibri-v3\/workspaces\/v3-current\/kolibri-v3/,
  );
});
