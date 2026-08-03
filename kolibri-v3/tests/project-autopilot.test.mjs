import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("developer menu exposes bounded project audit and improvement cycles", async () => {
	const [control, prompts] = await Promise.all([
		read("components/assistant-ui/developer-mode-control.tsx"),
		read("lib/product-chat/project-improvement.ts"),
	]);

	assert.match(control, /Автопилот проекта/);
	assert.match(control, /Полное сканирование/);
	assert.match(control, /Улучшить безопасно/);
	assert.match(
		control,
		/prepareProjectAutopilot\("auto", PROJECT_AUDIT_PROMPT\)/,
	);
	assert.match(
		control,
		/prepareProjectAutopilot\("full", PROJECT_IMPROVEMENT_PROMPT\)/,
	);
	assert.doesNotMatch(control, /composer\.send\(/);

	assert.match(prompts, /в режиме только чтения/);
	assert.match(
		prompts,
		/Выбери ровно одно наиболее ценное низкорисковое улучшение/,
	);
	assert.match(prompts, /Не выполняй deploy/);
	assert.match(
		prompts,
		/Не перезаписывай и не откатывай пользовательские изменения/,
	);
});
