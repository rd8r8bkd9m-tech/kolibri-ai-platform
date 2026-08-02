#!/usr/bin/env node

import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import http from "node:http";
import { fileURLToPath } from "node:url";
import path from "node:path";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const v3Root = path.resolve(scriptDirectory, "..");
const nextBinary = path.join(v3Root, "node_modules", ".bin", "next");
const mobileLauncher = path.join(v3Root, "scripts", "dev-mobile.mjs");
const gatewayLauncher = path.join(v3Root, "scripts", "dev-ui-gateway.mjs");
const desktopInternalPort = Number(
	process.env.KOLIBRI_V3_DESKTOP_INTERNAL_PORT || "3104",
);
const mobileInternalPort = Number(
	process.env.KOLIBRI_V3_MOBILE_INTERNAL_PORT || "4103",
);
const uiGatewayPort = Number(process.env.KOLIBRI_V3_UI_PORT || "3103");
const restartDelayMs = 1_000;
const readinessPollMs = 150;
const devInstanceId = randomUUID();
const agentRuntimeContract = "kolibri.agent-runtime@1.1";

let backend = null;
let web = null;
let mobile = null;
let gateway = null;
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
              payload.instanceId === devInstanceId &&
              payload.sourceRoot === v3Root &&
              payload.agentRuntimeContract === agentRuntimeContract,
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
		mobile?.kill("SIGTERM");
		gateway?.kill("SIGTERM");
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
	web = spawn(nextBinary, ["dev", "--port", String(desktopInternalPort)], {
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
	startMobile();
	startGateway();
}

function startMobile() {
	if (stopping || mobile || !backendReady) {
		return;
	}
	mobile = spawn(process.execPath, [mobileLauncher], {
		cwd: v3Root,
			env: {
			...process.env,
			KOLIBRI_V3_MOBILE_HOST: "localhost",
			KOLIBRI_V3_MOBILE_INTERNAL_HOST: "127.0.0.1",
			KOLIBRI_V3_MOBILE_INTERNAL_PORT: String(mobileInternalPort),
			KOLIBRI_V3_MOBILE_API_BASE_URL: "http://127.0.0.1:8002",
		},
		stdio: "inherit",
	});
	mobile.once("exit", (code, signal) => {
		mobile = null;
		if (!stopping) {
			if (backendReady) {
				console.error(
					`[dev:stack] mobile UI stopped (${signal ?? code}); restarting`,
				);
				scheduleRestart(startMobile);
			} else {
				scheduleReadinessProbe();
			}
		}
	});
}

function startGateway() {
	if (stopping || gateway || !backendReady) {
		return;
	}
	gateway = spawn(process.execPath, [gatewayLauncher], {
		cwd: v3Root,
		env: {
			...process.env,
			KOLIBRI_V3_UI_PORT: String(uiGatewayPort),
			KOLIBRI_V3_DESKTOP_INTERNAL_PORT: String(desktopInternalPort),
			KOLIBRI_V3_MOBILE_INTERNAL_HOST: "127.0.0.1",
			KOLIBRI_V3_MOBILE_INTERNAL_PORT: String(mobileInternalPort),
		},
		stdio: "inherit",
	});
	gateway.once("exit", (code, signal) => {
		gateway = null;
		if (!stopping) {
			if (backendReady) {
				console.error(
					`[dev:stack] UI gateway stopped (${signal ?? code}); restarting`,
				);
				scheduleRestart(startGateway);
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
	mobile?.kill("SIGTERM");
	gateway?.kill("SIGTERM");
	const activeChildren = [backend, web, mobile, gateway].filter(Boolean);
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
