#!/usr/bin/env node

import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import {
	existsSync,
	mkdirSync,
	readFileSync,
	rmSync,
	writeFileSync,
} from "node:fs";
import http from "node:http";
import { fileURLToPath } from "node:url";
import path from "node:path";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const v3Root = path.resolve(scriptDirectory, "..");
const nextBinary = path.join(v3Root, "node_modules", ".bin", "next");
const mobileLauncher = path.join(v3Root, "scripts", "dev-mobile.mjs");
const mobileBridgeLauncher = path.join(
	v3Root,
	"scripts",
	"dev-mobile-private-bridge.mjs",
);
const gatewayLauncher = path.join(v3Root, "scripts", "dev-ui-gateway.mjs");
const runtimeDir = path.join(v3Root, "var", "dev-runtime");
const devStackPidFile = path.join(runtimeDir, "dev-stack.pid");
const desktopInternalPort = Number(
	process.env.KOLIBRI_V3_DESKTOP_INTERNAL_PORT || "3104",
);
const mobileUpstreamPort = Number(
	process.env.KOLIBRI_V3_MOBILE_UPSTREAM_PORT || "4104",
);
const mobileSocket = path.join(v3Root, "var", "mobile-web.sock");
const uiGatewayPort = Number(process.env.KOLIBRI_V3_UI_PORT || "3103");
const legacyUiPort = Number(process.env.KOLIBRI_V3_LEGACY_UI_PORT || "3000");
const restartDelayMs = 1_000;
const readinessPollMs = 150;
const healthPollMs = 1_000;
const healthProbeTimeoutMs = 2_000;
const healthFailureThreshold = 8;
const backendTerminationGraceMs = 3_000;
const devInstanceId = randomUUID();
const agentRuntimeContract = "kolibri.agent-runtime@1.1";

function isProcessAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return Boolean(error && error.code === "EPERM");
  }
}

// Refuse to run a second dev stack: two supervisors restarting the same
// children fight over ports 8002/3103/3104/4104, which shows up as the
// backend repeatedly failing to bind and the UI flapping between ready and
// 502. The pid file is advisory only; the liveness check prevents a stale
// file from blocking a legitimate start after a crash.
function acquireSingleInstance() {
  if (existsSync(devStackPidFile)) {
    const raw = readFileSync(devStackPidFile, "utf8").trim();
    const pid = Number(raw);
    if (
      Number.isInteger(pid) &&
      pid > 0 &&
      pid !== process.pid &&
      isProcessAlive(pid)
    ) {
      console.error(
        `[dev:stack] another dev stack is already running (pid ${pid}); ` +
          "refusing to start a duplicate. Use `npm run dev:persistent:restart` " +
          "if you intended to restart it.",
      );
      process.exit(1);
    }
  }
  mkdirSync(runtimeDir, { recursive: true });
  writeFileSync(devStackPidFile, String(process.pid));
  const releasePidFile = () => {
    try {
      const current = readFileSync(devStackPidFile, "utf8").trim();
      if (current === String(process.pid)) {
        rmSync(devStackPidFile, { force: true });
      }
    } catch {
      // pid file is best-effort bookkeeping only
    }
  };
  process.on("exit", releasePidFile);
}

let backend = null;
let web = null;
let mobile = null;
let mobileBridge = null;
let gateway = null;
let legacyRedirect = null;
let backendReady = false;
let backendHealthFailures = 0;
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
  if (stopping || !backend || readinessTimer) {
    return;
  }
  readinessTimer = setTimeout(() => {
    readinessTimer = null;
    probeBackendReadiness();
  }, backendReady ? healthPollMs : readinessPollMs);
}

function stopUiChildren() {
	web?.kill("SIGTERM");
	mobile?.kill("SIGTERM");
	mobileBridge?.kill("SIGTERM");
	gateway?.kill("SIGTERM");
	legacyRedirect?.close();
	legacyRedirect = null;
}

function fenceUnhealthyBackend() {
	if (stopping || !backend) {
		return;
	}
	const unhealthyBackend = backend;
	backendReady = false;
	backendHealthFailures = 0;
	stopUiChildren();
	console.error(
		"[dev:stack] backend health failed repeatedly; fencing and restarting",
	);
	unhealthyBackend.kill("SIGTERM");
	const timer = setTimeout(() => {
		restartTimers.delete(timer);
		if (
			backend === unhealthyBackend &&
			unhealthyBackend.exitCode === null &&
			unhealthyBackend.signalCode === null
		) {
			unhealthyBackend.kill("SIGKILL");
		}
	}, backendTerminationGraceMs);
	restartTimers.add(timer);
}

function probeBackendReadiness() {
  if (stopping || !backend) {
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
      backendHealthFailures = 0;
      if (!web) {
		startWeb();
	  }
	  scheduleReadinessProbe();
      return;
    }
	if (backendReady) {
		backendHealthFailures += 1;
		if (backendHealthFailures >= healthFailureThreshold) {
			fenceUnhealthyBackend();
			return;
		}
	}
    scheduleReadinessProbe();
  };
  const request = http.get(
    {
      hostname: "127.0.0.1",
      port: 8002,
      path: "/v1/health",
      timeout: healthProbeTimeoutMs,
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
  backendHealthFailures = 0;
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
	backendHealthFailures = 0;
    if (!stopping) {
		stopUiChildren();
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
	startMobileBridge();
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
			KOLIBRI_V3_MOBILE_UPSTREAM_PORT: String(mobileUpstreamPort),
			KOLIBRI_V3_MOBILE_API_BASE_URL: "http://127.0.0.1:8002",
		},
		stdio: "inherit",
	});
	mobile.once("exit", (code, signal) => {
		mobile = null;
		if (!stopping && backendReady) {
			console.error(`[dev:stack] mobile UI stopped (${signal ?? code}); restarting`);
			scheduleRestart(startMobile);
		}
	});
}

function startMobileBridge() {
	if (stopping || mobileBridge || !backendReady) {
		return;
	}
	mobileBridge = spawn(process.execPath, [mobileBridgeLauncher], {
		cwd: v3Root,
		env: {
			...process.env,
			KOLIBRI_V3_MOBILE_INTERNAL_SOCKET: mobileSocket,
			KOLIBRI_V3_MOBILE_UPSTREAM_HOST: "127.0.0.1",
			KOLIBRI_V3_MOBILE_UPSTREAM_PORT: String(mobileUpstreamPort),
		},
		stdio: "inherit",
	});
	mobileBridge.once("exit", (code, signal) => {
		mobileBridge = null;
		if (!stopping && backendReady) {
			console.error(`[dev:stack] mobile bridge stopped (${signal ?? code}); restarting`);
			scheduleRestart(startMobileBridge);
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
			KOLIBRI_V3_MOBILE_INTERNAL_SOCKET: mobileSocket,
			KOLIBRI_V3_MOBILE_INTERNAL_PORT: String(mobileUpstreamPort),
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

// The pre-V3 development URL was http://localhost:3000. Keep that address
// working by redirecting it to the unified gateway, so muscle-memory
// bookmarks and installed dev PWAs do not land on a dead port.
function startLegacyRedirect() {
  if (legacyRedirect) {
    return;
  }
  legacyRedirect = http.createServer((request, response) => {
    const url = request.url || "/";
    response.writeHead(302, {
      Location: `http://127.0.0.1:${uiGatewayPort}${url}`,
    });
    response.end();
  });
  legacyRedirect.on("error", () => {
    legacyRedirect = null;
  });
  legacyRedirect.listen(legacyUiPort, "127.0.0.1");
  console.log(`[dev:stack] legacy UI redirect http://localhost:${legacyUiPort} -> ${uiGatewayPort}`);
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
	stopUiChildren();
	const activeChildren = [backend, web, mobile, mobileBridge, gateway].filter(Boolean);
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
acquireSingleInstance();
startLegacyRedirect();
startBackend();
