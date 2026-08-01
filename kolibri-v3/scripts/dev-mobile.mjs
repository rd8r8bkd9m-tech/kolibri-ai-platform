#!/usr/bin/env node

import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptsDirectory = path.dirname(fileURLToPath(import.meta.url));
const v3Root = path.resolve(scriptsDirectory, "..");
const mobileRoot = path.join(v3Root, "apps", "kolibri-mobile");
const expoBinary = path.join(
	mobileRoot,
	"node_modules",
	".bin",
	process.platform === "win32" ? "expo.cmd" : "expo",
);
const mobilePort = Number(
	process.env.KOLIBRI_V3_MOBILE_INTERNAL_PORT || "4103",
);
const mobileHost = process.env.KOLIBRI_V3_MOBILE_HOST?.trim() || "lan";
const apiBaseUrl =
	process.env.KOLIBRI_V3_MOBILE_API_BASE_URL?.trim() ||
	"http://127.0.0.1:8002";
const parsedApiBaseUrl = new URL(apiBaseUrl);
const loopbackHost = /^(localhost|127(?:\.\d{1,3}){3}|\[::1\])$/i.test(
	parsedApiBaseUrl.hostname,
);
if (loopbackHost && parsedApiBaseUrl.port !== "8002") {
	throw new Error(
		"Mobile UI must use the shared V3 API on port 8002; 3103 and 4103 are UI ports.",
	);
}

console.log(
	`[dev:mobile] source=${mobileRoot} port=${mobilePort} api=${apiBaseUrl}`,
);
console.log(
	"[dev:mobile] Expo is an internal mobile upstream; the public UI origin is 3103.",
);

const child = spawn(
	expoBinary,
	[
		"start",
		"--web",
		"--host",
		mobileHost,
		"--port",
		String(mobilePort),
		...process.argv.slice(2),
	],
	{
	cwd: mobileRoot,
	env: {
		...process.env,
		EXPO_PUBLIC_API_BASE_URL: apiBaseUrl,
	},
	stdio: "inherit",
},
);

const shutdown = (signal) => {
	child.kill(signal);
};

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));

child.once("exit", (code, signal) => {
	process.exit(signal ? 1 : (code ?? 1));
});
