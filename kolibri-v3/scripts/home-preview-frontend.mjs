#!/usr/bin/env node

import { spawn } from "node:child_process";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const v3Root = path.resolve(scriptDirectory, "..");
const nextBinary = path.join(v3Root, "node_modules", ".bin", "next");
const previewHost = "127.0.0.2";
const previewPort = "3103";
const productionBackend = "http://127.0.0.1:8002";
const requiredConfirmation = "production-backend-read-only-binding";
const releaseIdPattern = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const releaseCommitPattern = /^[0-9a-f]{40}$/;

if (process.env.KOLIBRI_HOME_PREVIEW_CONFIRM !== requiredConfirmation) {
  console.error(
    `[home-preview] refusing to start without KOLIBRI_HOME_PREVIEW_CONFIRM=${requiredConfirmation}`,
  );
  process.exit(64);
}

function probeProductionBackend() {
  return new Promise((resolve, reject) => {
    const request = http.get(
      {
        hostname: "127.0.0.1",
        port: 8002,
        path: "/v1/health",
        timeout: 2_000,
      },
      (response) => {
        let body = "";
        response.setEncoding("utf8");
        response.on("data", (chunk) => {
          if (body.length < 4_096) body += chunk;
        });
        response.on("end", () => {
          try {
            const payload = JSON.parse(body);
            if (
              response.statusCode === 200 &&
              payload.status === "ok" &&
              payload.service === "kolibri-v3" &&
              typeof payload.releaseId === "string" &&
              releaseIdPattern.test(payload.releaseId) &&
              typeof payload.releaseCommit === "string" &&
              releaseCommitPattern.test(payload.releaseCommit)
            ) {
              resolve({
                releaseId: payload.releaseId,
                releaseCommit: payload.releaseCommit,
              });
              return;
            }
          } catch {
            // The bounded error below intentionally does not echo the response.
          }
          reject(new Error("production backend health contract was not met"));
        });
      },
    );
    request.on("timeout", () => request.destroy());
    request.on("error", reject);
  });
}

const release = await probeProductionBackend();
let stopping = false;

const child = spawn(
  nextBinary,
  ["dev", "--hostname", previewHost, "--port", previewPort],
  {
    cwd: v3Root,
    env: {
      ...process.env,
      HOSTNAME: previewHost,
      KOLIBRI_V3_BACKEND_URL: productionBackend,
      KOLIBRI_RELEASE_ID: release.releaseId,
      KOLIBRI_RELEASE_COMMIT: release.releaseCommit,
      PORT: previewPort,
    },
    stdio: "inherit",
  },
);

const forward = (signal) => {
  stopping = true;
  if (child.exitCode === null && child.signalCode === null) child.kill(signal);
};

process.on("SIGINT", () => forward("SIGINT"));
process.on("SIGTERM", () => forward("SIGTERM"));

child.once("exit", (code, signal) => {
  if (stopping) {
    process.exit(0);
  }
  console.error(
    `[home-preview] Next exited unexpectedly (${signal ?? code ?? "unknown"})`,
  );
  // The user service restarts this launcher even when Next chose exit 0.
  process.exit(1);
});
