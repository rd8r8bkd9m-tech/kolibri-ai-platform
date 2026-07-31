import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const launcher = fs.readFileSync(
  new URL("../scripts/home-preview-frontend.mjs", import.meta.url),
  "utf8",
);
const nginx = fs.readFileSync(
  new URL("../deploy/preview/dev.kolibriai.ru.nginx", import.meta.url),
  "utf8",
);
const service = fs.readFileSync(
  new URL(
    "../deploy/preview/kolibri-v3-home-preview.service",
    import.meta.url,
  ),
  "utf8",
);
const acmeNginx = fs.readFileSync(
  new URL("../deploy/preview/dev.kolibriai.ru.acme.nginx", import.meta.url),
  "utf8",
);

test("Home preview binds HMR separately while using the production backend", () => {
  assert.match(launcher, /const previewHost = "127\.0\.0\.2"/);
  assert.match(launcher, /const previewPort = "3103"/);
  assert.match(launcher, /const productionBackend = "http:\/\/127\.0\.0\.1:8002"/);
  assert.match(launcher, /production-backend-read-only-binding/);
  assert.match(launcher, /KOLIBRI_RELEASE_ID: release\.releaseId/);
  assert.match(launcher, /KOLIBRI_RELEASE_COMMIT: release\.releaseCommit/);
  assert.doesNotMatch(launcher, /dev-backend\.sh|uvicorn|sqlite/);
});

test("dev.kolibriai.ru proxies only to the isolated HMR listener", () => {
  assert.match(nginx, /server_name dev\.kolibriai\.ru/);
  assert.match(nginx, /proxy_pass http:\/\/127\.0\.0\.2:3103/);
  assert.match(nginx, /proxy_set_header Upgrade \$http_upgrade/);
  assert.match(nginx, /X-Kolibri-Preview home-agent-worktree/);
  assert.match(nginx, /X-Robots-Tag "noindex, nofollow, noarchive"/);
  assert.doesNotMatch(nginx, /proxy_pass http:\/\/127\.0\.0\.1:8002/);
});

test("preview service runs from the single V3 agent worktree", () => {
  assert.match(
    service,
    /WorkingDirectory=\/opt\/kolibri-v3\/workspaces\/v3-current\/kolibri-v3/,
  );
  assert.match(service, /ExecStart=\/usr\/bin\/node scripts\/home-preview-frontend\.mjs/);
});

test("ACME bootstrap keeps the dev host challenge on the dev host", () => {
  assert.match(acmeNginx, /server_name dev\.kolibriai\.ru/);
  assert.match(acmeNginx, /location \^~ \/.well-known\/acme-challenge\//);
  assert.match(acmeNginx, /root \/var\/www\/html/);
});
