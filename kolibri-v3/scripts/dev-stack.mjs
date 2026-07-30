#!/usr/bin/env node

import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import http from "node:http";
import { fileURLToPath } from "node:url";
import path from "node:path";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const v3Root = path.resolve(scriptDirectory, "..");
const nextBinary = path.join(v3Root, "node_modules", ".bin", "next");
const restartDelayMs = 1_000;
const readinessPollMs = 150;
const devInstanceId = randomUUID();

let backend = null;
let web = null;
let backendReady = false;
let stopping = false;
let readinessTimer = null;
const restartTimers = new Set();

function scheduleRestart(start) {
  if (stopping) {
    return;
  }
  const timer = setTimeout(() => {
    restartTimers.delete(timer);
    start();
  }, restartDelayMs);
  restartTimers.add(timer);
}

function scheduleReadinessProbe() {
  if (stopping || web || readinessTimer) {
    return;
  }
  readinessTimer = setTimeout(() => {
    readinessTimer = null;
    probeBackendReadiness();
  }, readinessPollMs);
}

function probeBackendReadiness() {
  if (stopping || web) {
    return;
  }
  let settled = false;
  const finish = (healthy) => {
    if (settled) {
      return;
    }
    settled = true;
    if (
      healthy &&
      backend &&
      backend.exitCode === null &&
      backend.signalCode === null
    ) {
      backendReady = true;
      startWeb();
      return;
    }
    backendReady = false;
    scheduleReadinessProbe();
  };
  const request = http.get(
    {
      hostname: "127.0.0.1",
      port: 8002,
      path: "/v1/health",
      timeout: 500,
    },
    (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => {
        if (body.length < 1_024) {
          body += chunk;
        }
      });
      response.on("end", () => {
        try {
          const payload = JSON.parse(body);
          finish(
            response.statusCode === 200 &&
              payload.status === "ok" &&
              payload.service === "kolibri-v3" &&
              payload.instanceId === devInstanceId,
          );
        } catch {
          finish(false);
        }
      });
    },
  );
  request.on("timeout", () => request.destroy());
  request.on("error", () => finish(false));
}

function startBackend() {
  if (stopping || backend) {
    return;
  }
  backendReady = false;
  backend = spawn("/bin/bash", ["scripts/dev-backend.sh"], {
    cwd: v3Root,
    env: {
      ...process.env,
      KOLIBRI_V3_DEV_INSTANCE_ID: devInstanceId,
    },
    stdio: "inherit",
  });
  backend.once("exit", (code, signal) => {
    backend = null;
    backendReady = false;
    if (!stopping) {
      web?.kill("SIGTERM");
      console.error(
        `[dev:stack] backend stopped (${signal ?? code}); restarting`,
      );
      scheduleRestart(startBackend);
    }
  });
  probeBackendReadiness();
}

function startWeb() {
  if (stopping || web || !backendReady) {
    return;
  }
  web = spawn(nextBinary, ["dev", "--port", "3103"], {
    cwd: v3Root,
    env: {
      ...process.env,
      KOLIBRI_V3_BACKEND_URL: "http://127.0.0.1:8002",
    },
    stdio: "inherit",
  });
  web.once("exit", (code, signal) => {
    web = null;
    if (!stopping) {
      if (backendReady) {
        console.error(
          `[dev:stack] web stopped (${signal ?? code}); restarting`,
        );
        scheduleRestart(startWeb);
      } else {
        scheduleReadinessProbe();
      }
    }
  });
}

function shutdown(signal) {
  if (stopping) {
    return;
  }
  stopping = true;
  for (const timer of restartTimers) {
    clearTimeout(timer);
  }
  restartTimers.clear();
  if (readinessTimer) {
    clearTimeout(readinessTimer);
    readinessTimer = null;
  }
  backend?.kill("SIGTERM");
  web?.kill("SIGTERM");
  const activeChildren = [backend, web].filter(Boolean);
  if (activeChildren.length === 0) {
    process.exit(signal === "SIGINT" ? 130 : 0);
  }
  const deadline = setTimeout(() => process.exit(1), 5_000);
  deadline.unref();
  Promise.all(
    activeChildren.map(
      (child) =>
        new Promise((resolve) => {
          child.once("exit", resolve);
        }),
    ),
  ).then(() => process.exit(signal === "SIGINT" ? 130 : 0));
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));

console.log(
  `[dev:stack] Kolibri V3 source=${v3Root} database=var/kolibri-v3.db`,
);
startBackend();
