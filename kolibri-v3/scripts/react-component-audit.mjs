#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const ROOT = process.cwd();
const TARGET_EXTS = new Set([".ts", ".tsx", ".js", ".jsx"]);
const SKIP = new Set([".next", "dist", "build", "output", "coverage", ".git"]);

const args = new Set(process.argv.slice(2));
const dir = args.has("--dir")
	? process.argv[process.argv.indexOf("--dir") + 1]
	: "components";
const maxLines = Number.parseInt(
	process.argv[process.argv.indexOf("--max-lines") + 1] ?? "260",
	10,
);
const strict = args.has("--strict");
const includeMobile = args.has("--include-mobile");

const roots = [dir];
if (includeMobile) {
	roots.push("apps/kolibri-mobile/components");
}

function isPascalCase(name) {
	return /^[A-Z][A-Za-z0-9_]*$/.test(name);
}

function walk(dirPath, out) {
	for (const entry of fs.readdirSync(dirPath, { withFileTypes: true })) {
		if (entry.name.startsWith(".")) continue;
		if (SKIP.has(entry.name)) continue;
		const full = path.join(dirPath, entry.name);
		if (entry.isDirectory()) {
			walk(full, out);
			continue;
		}
		if (!TARGET_EXTS.has(path.extname(entry.name))) continue;
		out.push(full);
	}
}

function lineCount(text) {
	return text === "" ? 0 : text.split("\n").length;
}

function getHookNames() {
	return new Set([
		"useState",
		"useMemo",
		"useEffect",
		"useCallback",
		"useRef",
		"useReducer",
		"useContext",
		"useSyncExternalStore",
		"useId",
		"useTransition",
		"useDeferredValue",
		"useImperativeHandle",
		"useLayoutEffect",
	]);
}

function hasClientNeed(text, sourceFile) {
	const hasHookUsage = getHookNames().has("x");
	const usedHooks = ts
		.createScanner(
			ts.ScriptTarget.Latest,
			true,
			ts.LanguageVariant.TSX,
			text,
		)
		;
	let token = usedHooks.scan();
	while (token !== ts.SyntaxKind.EndOfFileToken) {
		if (token === ts.SyntaxKind.Identifier) {
			const textToken = usedHooks.getTokenText();
			if (getHookNames().has(textToken)) {
				return true;
			}
		}
		token = usedHooks.scan();
	}
	return hasHookUsage && /use[A-Z][A-Za-z0-9_]+\\(/.test(text);
}

function analyzeComponent(filePath) {
	const text = fs.readFileSync(filePath, "utf8");
	const sourceFile = ts.createSourceFile(
		filePath,
		text,
		ts.ScriptTarget.Latest,
		true,
		ts.ScriptKind.TSX,
	);
	const declarations = [];
	for (const stmt of sourceFile.statements) {
		if (ts.isFunctionDeclaration(stmt) && stmt.name) {
			const name = stmt.name.text;
			if (!isPascalCase(name) || !stmt.body) continue;
			declarations.push({
				name,
				line:
					text.slice(0, stmt.getStart()).split("\n").length,
				endLine: text.slice(0, stmt.body.getEnd()).split("\n").length,
				type: "function",
			});
		}
		if (ts.isVariableStatement(stmt)) {
			for (const decl of stmt.declarationList.declarations) {
				if (!ts.isIdentifier(decl.name)) continue;
				const name = decl.name.text;
				if (!isPascalCase(name) || !decl.initializer) continue;
				if (
					ts.isArrowFunction(decl.initializer) ||
					ts.isFunctionExpression(decl.initializer)
				) {
					declarations.push({
						name,
						line: text.slice(0, decl.getStart()).split("\n").length,
						endLine: text.slice(0, decl.initializer.getEnd()).split("\n").length,
						type: ts.isArrowFunction(decl.initializer) ? "arrow" : "function",
					});
				}
			}
		}
	}
	const lines = lineCount(text);
	const hasClient = /\"use client\"/.test(text);
	return {
		file: path.relative(ROOT, filePath),
		lines,
		components: declarations.length,
		declarations,
		hasUseClient: hasClient,
		needsClientHint:
			lines > 180 &&
			!hasClient &&
			/ useState\\(| useMemo\\(| useEffect\\(| useCallback\\(| useRef\\(| useContext\\(| useSyncExternalStore\\(/.test(text),
	};
}

const files = [];
for (const root of roots) {
	const abs = path.join(ROOT, root);
	if (!fs.existsSync(abs)) continue;
	walk(abs, files);
}

const rows = files
	.map((filePath) => analyzeComponent(filePath))
	.sort((a, b) => b.lines - a.lines);

console.log(`[react-component-audit] roots: ${roots.join(", ")}`);
console.log(
	`[react-component-audit] inspected files: ${rows.length}, threshold=${maxLines}`,
);
console.log("[react-component-audit] top candidates:");
for (const row of rows.slice(0, 50)) {
	console.log(
		`${String(row.lines).padStart(4, " ")} lines | ${String(row.components).padStart(2, " " )} components | ${row.file}`,
	);
}

const offenders = rows.filter((row) => row.lines >= maxLines);
if (offenders.length) {
	console.log("\n[react-component-audit] files >= maxLines:");
	for (const row of offenders) {
		console.log(`  ${row.lines}\t${row.file}`);
	}
}

const clientHints = rows.filter((row) => row.needsClientHint);
if (clientHints.length) {
	console.log("\n[react-component-audit] likely client files without 'use client':");
	for (const row of clientHints) {
		console.log(`  ${row.lines}\t${row.file}`);
	}
}

const candidates = rows.filter((row) => row.components >= 6 && row.lines > 300);
if (candidates.length) {
	console.log(
		"\n[react-component-audit] candidates for component extraction (>=6 components):",
	);
	for (const row of candidates) {
		console.log(`  ${row.file}`);
		for (const item of row.declarations.slice(0, 12)) {
			console.log(
				`    - ${item.name} (${item.type}) @${item.line}-${item.endLine}`,
			);
		}
	}
}

if (strict && offenders.length > 0) {
	process.exitCode = 1;
}
