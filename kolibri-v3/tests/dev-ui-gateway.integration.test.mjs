import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import http from "node:http";
import test from "node:test";
import { fileURLToPath } from "node:url";

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      server.off("error", reject);
      resolve(server.address().port);
    });
  });
}

function close(server) {
  return new Promise((resolve) => server.close(resolve));
}

function request(port, path, userAgent = "Mozilla/5.0 (iPhone) Mobile/15E148") {
  return new Promise((resolve, reject) => {
    const outgoing = http.get(
      {
        hostname: "127.0.0.1",
        port,
        path,
        headers: {
          "user-agent": userAgent,
        },
      },
      (response) => {
        let body = "";
        response.setEncoding("utf8");
        response.on("data", (chunk) => {
          body += chunk;
        });
        response.on("end", () => resolve({ response, body }));
      },
    );
    outgoing.once("error", reject);
  });
}

test("mobile /app reaches the IPv4 Expo upstream through the public gateway", async (t) => {
  const desktop = http.createServer((request, response) => {
    response.writeHead(200, { "content-type": "text/plain" });
    response.end(`desktop:${request.url}`);
  });
  const desktopPort = await listen(desktop);
  t.after(() => close(desktop));

  const mobile = http.createServer((request, response) => {
    response.writeHead(200, { "content-type": "text/plain" });
    response.end(`mobile:${request.url}`);
  });
  const mobilePort = await listen(mobile);
  t.after(() => close(mobile));

  const reservation = http.createServer();
  const gatewayPort = await listen(reservation);
  await close(reservation);

  const gateway = spawn(
    process.execPath,
    [fileURLToPath(new URL("../scripts/dev-ui-gateway.mjs", import.meta.url))],
    {
      env: {
        ...process.env,
        KOLIBRI_V3_UI_PORT: String(gatewayPort),
        KOLIBRI_V3_DESKTOP_INTERNAL_PORT: String(desktopPort),
        KOLIBRI_V3_MOBILE_INTERNAL_HOST: "127.0.0.1",
        KOLIBRI_V3_MOBILE_INTERNAL_PORT: String(mobilePort),
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  t.after(() => gateway.kill("SIGTERM"));

  await new Promise((resolve, reject) => {
    const timeout = setTimeout(
      () => reject(new Error("gateway did not start")),
      5_000,
    );
    gateway.stdout.once("data", () => {
      clearTimeout(timeout);
      resolve();
    });
    gateway.once("exit", (code) => {
      clearTimeout(timeout);
      reject(new Error(`gateway exited early with ${code}`));
    });
  });

  const { response, body } = await request(
    gatewayPort,
    "/app?client=mobile",
  );
  assert.equal(response.statusCode, 200);
  assert.equal(response.headers["x-kolibri-ui-target"], "mobile");
  assert.match(response.headers["set-cookie"][0], /kolibri_ui_client=mobile/);
  assert.equal(body, "mobile:/app");

  const desktopResult = await request(
    gatewayPort,
    "/app?client=mobile",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
  );
  assert.equal(desktopResult.response.statusCode, 200);
  assert.equal(desktopResult.response.headers["x-kolibri-ui-target"], "desktop");
  assert.match(
    desktopResult.response.headers["set-cookie"][0],
    /kolibri_ui_client=desktop/,
  );
  assert.equal(desktopResult.body, "desktop:/app?client=mobile");
});
