#!/usr/bin/env node

import { createHash } from "node:crypto";
import {
	existsSync,
	readFileSync,
	readdirSync,
	statSync,
	unlinkSync,
	writeFileSync,
} from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, extname, join, relative, resolve } from "node:path";
import ts from "typescript";

const ROOT = process.cwd();
const TARGET = resolve(ROOT, "components");
const APPLY = process.argv.includes("--apply");
const CHECK = process.argv.includes("--check");
const MAX_LINES = Number.parseInt(
	process.argv.find((arg) => arg.startsWith("--max-lines="))?.split("=")[1] ?? "240",
	10,
);
const SOURCE_EXTENSIONS = new Set([".ts", ".tsx"]);
const PROJECT_SOURCE_EXTENSIONS = new Set([
	".ts",
	".tsx",
	".js",
	".jsx",
	".mjs",
	".cjs",
]);
const SKIP_DIRECTORIES = new Set([
	".git",
	".next",
	"coverage",
	"dist",
	"node_modules",
	"output",
]);

function walk(directory, files = []) {
	for (const entry of readdirSync(directory, { withFileTypes: true })) {
		if (entry.isDirectory() && SKIP_DIRECTORIES.has(entry.name)) continue;
		const path = join(directory, entry.name);
		if (entry.isDirectory()) walk(path, files);
		else if (SOURCE_EXTENSIONS.has(extname(entry.name))) files.push(path);
	}
	return files;
}

function walkProject(directory = ROOT, files = []) {
	for (const entry of readdirSync(directory, { withFileTypes: true })) {
		if (entry.isDirectory() && SKIP_DIRECTORIES.has(entry.name)) continue;
		const path = join(directory, entry.name);
		if (entry.isDirectory()) walkProject(path, files);
		else if (PROJECT_SOURCE_EXTENSIONS.has(extname(entry.name))) files.push(path);
	}
	return files;
}

function sourceFile(path, text) {
	return ts.createSourceFile(
		path,
		text,
		ts.ScriptTarget.Latest,
		true,
		path.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
	);
}

function lineOf(text, position) {
	return text.slice(0, position).split("\n").length;
}

function componentDeclarations(path, text) {
	const declarations = [];
	for (const statement of sourceFile(path, text).statements) {
		let name;
		let end;
		if (ts.isFunctionDeclaration(statement) && statement.name && statement.body) {
			name = statement.name.text;
			end = statement.body.end;
		} else if (ts.isVariableStatement(statement)) {
			const declaration = statement.declarationList.declarations[0];
			if (
				declaration &&
				ts.isIdentifier(declaration.name) &&
				declaration.initializer &&
				(ts.isArrowFunction(declaration.initializer) ||
					ts.isFunctionExpression(declaration.initializer))
			) {
				name = declaration.name.text;
				end = declaration.initializer.end;
			}
		}
		if (!name || !/^[A-Z]/.test(name) || !end) continue;
		declarations.push({
			name,
			start: lineOf(text, statement.getStart()),
			end: lineOf(text, end),
		});
	}
	return declarations;
}

function normalizedCloneWindows(text, windowSize = 8) {
	const lines = text
		.split("\n")
		.map((line) => line.replace(/\/\/.*$/, "").replace(/\s+/g, " ").trim())
		.filter(Boolean);
	const windows = [];
	for (let index = 0; index <= lines.length - windowSize; index += 1) {
		const value = lines.slice(index, index + windowSize).join("\n");
		if (value.length < 180) continue;
		windows.push(createHash("sha1").update(value).digest("hex"));
	}
	return windows;
}

function inspect(files) {
	const cloneOwners = new Map();
	const rows = files.map((path) => {
		const text = readFileSync(path, "utf8");
		for (const hash of normalizedCloneWindows(text)) {
			const owners = cloneOwners.get(hash) ?? new Set();
			owners.add(path);
			cloneOwners.set(hash, owners);
		}
		return {
			path,
			file: relative(ROOT, path),
			text,
			lines: text.split("\n").length,
			components: componentDeclarations(path, text),
			state: (text.match(/\buseState\s*\(/g) ?? []).length,
			effects: (text.match(/\buseEffect\s*\(/g) ?? []).length,
			fetches: (text.match(/\bfetch\s*\(/g) ?? []).length,
		};
	});
	const duplicateWindows = [...cloneOwners.values()].filter(
		(owners) => owners.size > 1,
	).length;
	return {
		rows,
		totalLines: rows.reduce((sum, row) => sum + row.lines, 0),
		duplicateWindows,
	};
}

function safeCleanup(text) {
	return text
		.replace(/[ \t]+$/gm, "")
		.replace(/\n{3,}/g, "\n\n")
		.replace(/\{false \? ([^{}\n]+) : undefined\}/g, "{$1}");
}

function resolveSourceImport(importer, specifier) {
	let base;
	if (specifier.startsWith("@/")) base = resolve(ROOT, specifier.slice(2));
	else if (specifier.startsWith(".")) base = resolve(dirname(importer), specifier);
	else return undefined;

	const candidates = [
		base,
		...Array.from(SOURCE_EXTENSIONS, (extension) => `${base}${extension}`),
		...Array.from(SOURCE_EXTENSIONS, (extension) => join(base, `index${extension}`)),
	];
	return candidates.find(
		(candidate) => existsSync(candidate) && statSync(candidate).isFile(),
	);
}

function referencedComponentFiles(componentFiles) {
	const componentSet = new Set(componentFiles.map((file) => resolve(file)));
	const referenced = new Set();
	for (const path of walkProject()) {
		const text = readFileSync(path, "utf8");
		const parsed = sourceFile(path, text);
		for (const statement of parsed.statements) {
			if (
				!ts.isImportDeclaration(statement) &&
				!ts.isExportDeclaration(statement)
			) {
				continue;
			}
			const literal = statement.moduleSpecifier;
			if (!literal || !ts.isStringLiteral(literal)) continue;
			const dependency = resolveSourceImport(path, literal.text);
			if (dependency && componentSet.has(resolve(dependency))) {
				referenced.add(resolve(dependency));
			}
		}
	}
	return referenced;
}

function pruneUnreferencedComponentFiles(componentFiles) {
	const referenced = referencedComponentFiles(componentFiles);
	const unused = componentFiles.filter((file) => !referenced.has(resolve(file)));
	for (const path of unused) unlinkSync(path);
	return unused;
}

function runBiome(write) {
	const commands = [
		[
			"check",
			"components",
			...(write ? ["--write"] : []),
			"--only=assist/source/organizeImports",
			"--max-diagnostics=50",
		],
		["format", "components", ...(write ? ["--write"] : [])],
	];
	for (const args of commands) {
		const result = spawnSync("npx", ["--yes", "@biomejs/biome", ...args], {
			cwd: ROOT,
			stdio: "inherit",
		});
		if (result.status !== 0) {
			throw new Error(`Biome failed: biome ${args.join(" ")}`);
		}
	}
}

function applySafeRewrites(snapshot) {
	let changed = 0;
	for (const row of snapshot.rows) {
		const next = safeCleanup(row.text);
		if (next === row.text) continue;
		writeFileSync(row.path, next);
		changed += 1;
	}
	return changed;
}

function print(snapshot) {
	const monoliths = snapshot.rows
		.filter((row) => row.lines > MAX_LINES)
		.sort((left, right) => right.lines - left.lines);
	console.log(
		`[component-refactor] files=${snapshot.rows.length} lines=${snapshot.totalLines} duplicate-windows=${snapshot.duplicateWindows}`,
	);
	for (const row of monoliths) {
		console.log(
			`${String(row.lines).padStart(4)} ${row.file} components=${row.components.length} state=${row.state} effects=${row.effects} fetch=${row.fetches}`,
		);
	}
	return monoliths;
}

if (!existsSync(TARGET)) {
	throw new Error(`components directory not found: ${TARGET}`);
}

const before = inspect(walk(TARGET));
if (APPLY) {
	runBiome(true);
	const changed = applySafeRewrites(before);
	const unusedFiles = pruneUnreferencedComponentFiles(walk(TARGET));
	const after = inspect(walk(TARGET));
	if (after.totalLines > before.totalLines) {
		throw new Error(
			`refactor rejected: total lines grew ${before.totalLines} -> ${after.totalLines}`,
		);
	}
	if (after.duplicateWindows > before.duplicateWindows) {
		throw new Error(
			`refactor rejected: duplicate windows grew ${before.duplicateWindows} -> ${after.duplicateWindows}`,
		);
	}
	console.log(
		`[component-refactor] applied files=${changed} removed-files=${unusedFiles.length} lines=${before.totalLines}->${after.totalLines}`,
	);
	for (const path of unusedFiles) {
		console.log(`[component-refactor] removed ${relative(ROOT, path)}`);
	}
	const remaining = print(after);
	if (CHECK && remaining.length) process.exitCode = 1;
} else {
	if (CHECK) runBiome(false);
	const remaining = print(before);
	if (CHECK && remaining.length) process.exitCode = 1;
}
