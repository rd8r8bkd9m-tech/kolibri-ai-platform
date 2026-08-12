import assert from "node:assert/strict";
import test from "node:test";

import {
	buildAgentRun,
	formatAgentElapsed,
	humanToolTitle,
} from "../lib/agent-run.ts";

test("buildAgentRun groups reasoning and tool parts into steps", () => {
	const run = buildAgentRun(
		[
			{ type: "reasoning", text: "raw reasoning" },
			{
				type: "tool-call",
				toolCallId: "tc1",
				toolName: "developer_command",
				args: { command: "npm run test", cwd: "." },
				status: { type: "running" },
			},
			{
				type: "tool-call",
				toolCallId: "tc2",
				toolName: "developer_file_change",
				args: {
					files: [{ kind: "write", path: "src/app.tsx" }],
				},
				result: { changes: [{ path: "src/app.tsx", diff: "+1 -1" }] },
				status: { type: "complete" },
			},
		],
		{ runId: "run-1", startedAt: 0 },
	);

	assert.equal(run.id, "run-1");
	assert.equal(run.status, "running");
	assert.equal(run.steps.length, 3);
	assert.equal(run.steps[0]?.type, "thinking");
	assert.equal(run.steps[0]?.title, "Анализирую задачу");
	assert.equal(run.steps[1]?.type, "tool");
	assert.equal(run.steps[1]?.title, "Выполняю команду: npm run test");
	assert.equal(run.steps[2]?.status, "completed");
	assert.equal(run.progress, "2 из 3 шагов");
	assert.equal(run.lastUsefulState, "Выполняю команду: npm run test");
});

test("buildAgentRun collapses after completion", () => {
	const run = buildAgentRun(
		[
			{
				type: "tool-call",
				toolCallId: "tc1",
				toolName: "search_prices",
				status: { type: "complete" },
			},
		],
		{ finishedAt: 1000 },
	);
	assert.equal(run.status, "completed");
	assert.equal(run.lastUsefulState, "Готово");
	assert.equal(run.progress, "Выполнено шагов: 1");
});

test("buildAgentRun marks error steps and keeps them open", () => {
	const run = buildAgentRun([
		{
			type: "tool-call",
			toolCallId: "tc1",
			toolName: "get_weather",
			status: { type: "error" },
		},
	]);
	assert.equal(run.status, "error");
	assert.equal(run.lastUsefulState, "Ошибка");
	assert.equal(run.steps[0]?.status, "error");
});

test("humanToolTitle covers developer and product tools", () => {
	assert.equal(
		humanToolTitle("developer_file_change", { files: [{ kind: "read" }] }, "running"),
		"Читаю файлы",
	);
	assert.equal(
		humanToolTitle("developer_file_change", { files: [{ kind: "glob" }] }, "completed"),
		"Поиск выполнен",
	);
	assert.equal(
		humanToolTitle("developer_file_change", { files: [{ kind: "write" }] }, "running"),
		"Изменяю файлы",
	);
	assert.equal(humanToolTitle("search_prices", null, "completed"), "Цены найдены");
	assert.equal(humanToolTitle("present", null, "running"), "Формирую представление");
});

test("formatAgentElapsed renders mm:ss", () => {
	assert.equal(formatAgentElapsed(0), "0:00");
	assert.equal(formatAgentElapsed(134_000), "2:14");
});
