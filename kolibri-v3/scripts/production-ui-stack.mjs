#!/usr/bin/env node

import { spawn } from "node:child_process";
import path from "node:path";

const releaseRoot = path.resolve(process.env.KOLIBRI_V3_RELEASE_ROOT || "");
const publicPort = Number(process.env.PORT || "3103");
const desktopPort = Number(process.env.KOLIBRI_V3_DESKTOP_INTERNAL_PORT || "3104");
const mobilePort = Number(process.env.KOLIBRI_V3_MOBILE_INTERNAL_PORT || "4103");

if (
	!process.env.KOLIBRI_V3_RELEASE_ROOT ||
	new Set([publicPort, desktopPort, mobilePort]).size !== 3
) {
	throw new Error("A release root and three unique UI ports are required");
}

const runtimeRoot = path.join(releaseRoot, "runtime");
const sourceRoot = path.join(releaseRoot, "source");
const children = [];
let stopping = false;

function launch(name, script, cwd, env) {
	const child = spawn(process.execPath, [script], {
		cwd,
		env: { ...process.env, ...env },
		stdio: "inherit",
	});
	children.push(child);
	child.once("exit", (code, signal) => {
		if (stopping) return;
		console.error(`[ui:stack] ${name} stopped (${signal ?? code})`);
		shutdown(1);
	});
}

function shutdown(exitCode) {
	if (stopping) return;
	stopping = true;
	for (const child of children) child.kill("SIGTERM");
	const deadline = setTimeout(() => process.exit(exitCode), 5_000);
	deadline.unref();
	Promise.all(
		children.map(
			(child) =>
				new Promise((resolve) => {
					if (child.exitCode !== null || child.signalCode !== null) resolve();
					else child.once("exit", resolve);
				}),
		),
	).then(() => process.exit(exitCode));
}

launch(
	"desktop",
	path.join(runtimeRoot, "frontend", "server.js"),
	path.join(runtimeRoot, "frontend"),
	{ HOSTNAME: "127.0.0.1", PORT: String(desktopPort) },
);
launch(
	"mobile",
	path.join(sourceRoot, "scripts", "mobile-static-server.mjs"),
	path.join(runtimeRoot, "mobile"),
	{
		KOLIBRI_V3_MOBILE_HOST: "127.0.0.1",
		KOLIBRI_V3_MOBILE_PORT: String(mobilePort),
		KOLIBRI_V3_MOBILE_ROOT: path.join(runtimeRoot, "mobile"),
	},
);
launch(
	"gateway",
	path.join(sourceRoot, "scripts", "dev-ui-gateway.mjs"),
	sourceRoot,
	{
		KOLIBRI_V3_UI_HOST: "127.0.0.1",
		KOLIBRI_V3_UI_PORT: String(publicPort),
		KOLIBRI_V3_DESKTOP_INTERNAL_PORT: String(desktopPort),
		KOLIBRI_V3_MOBILE_INTERNAL_HOST: "127.0.0.1",
		KOLIBRI_V3_MOBILE_INTERNAL_PORT: String(mobilePort),
	},
);

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
