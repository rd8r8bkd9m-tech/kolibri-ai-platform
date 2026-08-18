#!/usr/bin/env node
/**
 * Kolibri V3 skill router.
 *
 * Usage:
 *   node .agents/scripts/skill-router.mjs "<task description>" [--top N] [--rebuild]
 *
 * Selects the smallest relevant `.agents/skills` set for a task by scoring the
 * task language against skill names, descriptions and categories. The index
 * (`skills-index.json`) is rebuilt from the filesystem with `--rebuild` or
 * automatically when missing. Read the top-ranked SKILL.md files in full
 * before implementing; do not load the whole catalog.
 */
import { readFile, writeFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const AGENTS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SKILLS_DIR = path.join(AGENTS, "skills");
const INDEX_PATH = path.join(AGENTS, "skills-index.json");

// Project-specific keyword overrides: task token -> exact skill names.
const OVERRIDES = {
	composer: ["kolibri-mobile-chat", "chat-interface", "primitives", "chat-feature-implementation"],
	композер: ["kolibri-mobile-chat", "chat-interface", "primitives"],
	модель: ["model-selector", "kolibri-mobile-chat", "model-routing"],
	streaming: ["assistant-ui-streaming", "streaming", "llm-streaming", "kolibri-agui-transport"],
	стриминг: ["assistant-ui-streaming", "streaming", "kolibri-agui-transport"],
	drawer: ["kolibri-mobile-navigation", "thread-list"],
	сайдбар: ["kolibri-mobile-navigation", "thread-list"],
	тема: ["dark-mode", "kolibri-mobile-ui"],
	theme: ["dark-mode", "kolibri-mobile-ui"],
	смета: ["estimate-end-to-end", "kolibri-estimates-engine", "estimate-calculation-engine"],
	estimate: ["estimate-end-to-end", "kolibri-estimates-engine"],
	backend: ["api-feature-implementation", "kolibri-backend", "fastapi", "contract-driven-feature"],
	auth: ["authentication", "kolibri-auth-session"],
	вложение: ["attachments-pipeline", "kolibri-mobile-chat", "file-attachments"],
	attachment: ["attachments-pipeline", "file-attachments"],
	тест: ["development-smoke-check", "kolibri-mobile-qa", "unit-testing", "test-triage"],
	qa: ["kolibri-mobile-qa", "development-smoke-check", "visual-e2e"],
	рефакторинг: ["code-refactoring", "react-native-components", "typescript-strict"],
	refactor: ["code-refactoring", "react-native-components"],
	проект: ["kolibri-mobile-navigation", "kolibri-vertical-registry", "screen-implementation"],
	карточк: ["interactive-artifacts", "kolibri-mobile-chat", "message-rendering"],
	экспорт: ["estimate-xlsx-export", "estimate-pdf-export", "estimate-end-to-end"],
	расценками: ["estimate-pricing", "kolibri-estimates-engine"],
	back: ["kolibri-mobile-navigation"],
	voice: ["kolibri-mobile-chat", "runtime"],
	голос: ["kolibri-mobile-chat", "runtime"],
	expo: ["expo-project-structure", "expo-router", "expo-upgrade"],
};

const STOPWORDS = new Set([
	"в", "на", "и", "для", "по", "с", "у", "не", "от", "до", "из", "за", "при", "или",
	"the", "to", "of", "for", "and", "a", "an", "use", "when", "task", "this",
	"мне", "нужно", "сделай", "почини", "исправь", "добавь", "надо",
]);

function tokenize(text) {
	return (text.toLowerCase().match(/[a-zа-яё0-9]+/g) ?? []).filter(
		(token) => token.length > 1 && !STOPWORDS.has(token),
	);
}

function parseFrontmatter(content) {
	const match = content.match(/^---\n([\s\S]*?)\n---/);
	const frontmatter = match?.[1] ?? "";
	const field = (key) =>
		frontmatter.match(new RegExp(`^${key}:[ ]*(.*)$`, "m"))?.[1]?.trim() ?? "";
	return { name: field("name"), description: field("description") };
}

async function rebuildIndex() {
	const skills = [];
	const walk = async (dir, category) => {
		for (const entry of await readdir(dir, { withFileTypes: true })) {
			const full = path.join(dir, entry.name);
			if (entry.isDirectory()) {
				await walk(full, category);
			} else if (entry.name === "SKILL.md") {
				const content = await readFile(full, "utf8");
				const { name, description } = parseFrontmatter(content);
				const relative = path.relative(SKILLS_DIR, full);
				const first = relative.split(path.sep)[0];
				const skillCategory = /^\d{2}-/.test(first) ? first : "flat";
				skills.push({
					name: name || path.basename(path.dirname(full)),
					path: `.agents/skills/${relative}`,
					category: skillCategory,
					description,
				});
			}
		}
	};
	await walk(SKILLS_DIR, "flat");
	skills.sort((a, b) => a.path.localeCompare(b.path));
	const index = { version: "3.1.0", count: skills.length, skills };
	await writeFile(INDEX_PATH, `${JSON.stringify(index, null, 2)}\n`, "utf8");
	return index;
}

async function loadIndex(force) {
	if (force) return rebuildIndex();
	try {
		return JSON.parse(await readFile(INDEX_PATH, "utf8"));
	} catch {
		return rebuildIndex();
	}
}

function score(query, skill) {
	const tokens = tokenize(query);
	let score = 0;
	for (const token of tokens) {
		const haystack = `${skill.name} ${skill.description} ${skill.category}`.toLowerCase();
		if (haystack.includes(token)) score += 1;
		if (skill.name === token) score += 50;
		for (const name of OVERRIDES[token] ?? []) {
			if (skill.name === name) score += 20;
		}
	}
	return score;
}

const args = process.argv.slice(2);
const rebuild = args.includes("--rebuild");
	const top = (() => {
		const flag = args.indexOf("--top");
		return flag >= 0 ? Number(args[flag + 1]) || 5 : 5;
	})();
const query = args.filter((arg) => !arg.startsWith("--")).join(" ") || "(пустой запрос)";

const index = await loadIndex(rebuild);
const ranked = index.skills
	.map((skill) => ({ ...skill, score: score(query, skill) }))
	.filter((skill) => skill.score > 0)
	.sort((a, b) => b.score - a.score || a.path.localeCompare(b.path));

console.log(`Задача: ${query}`);
console.log(`Скиллов в каталоге: ${index.count}; релевантных: ${ranked.length}`);
console.log("Топ (читай SKILL.md целиком перед разработкой):");
for (const skill of ranked.slice(0, top)) {
	console.log(`  [${skill.score}] ${skill.name}  (${skill.category})\n      ${skill.path}`);
}
if (ranked.length === 0) {
	console.log("  (нет совпадений — выбери ближайшие по категории и зафиксируй решение в decision-log)");
}
