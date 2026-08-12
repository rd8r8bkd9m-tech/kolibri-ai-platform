"use client";

import {
	AuiProvider,
	Suggestions,
	Tools,
	unstable_Interactables,
	useAui,
} from "@assistant-ui/react";

import { kolibriToolkit } from "@/components/assistant-ui/toolkit";
import { EstimateDraftInteractableSpike } from "@/components/assistant-ui/interactables/estimate-draft-spike";
import { WorkspaceShell } from "@/components/kolibri-shell/workspace-shell";
import { ThreadDeepLink } from "@/components/kolibri-shell/thread-deep-link";

const kolibriSuggestions = Suggestions([
	{
		title: "Собрать смету",
		label: "по описанию и файлам",
		prompt:
			"Собери предварительную смету проекта. Сначала отдели факты от условий расчёта и перечисли недостающие исходные данные.",
	},
	{
		title: "Разобрать проект",
		label: "и составить план работ",
		prompt:
			"Разбери исходные данные проекта и предложи проверяемый план работ с этапами, рисками и результатами.",
	},
	{
		title: "Подготовить документы",
		label: "КП, счёт и договор",
		prompt:
			"Подготовь связанный комплект документов для проекта. Покажи, какие данные и согласования ещё нужны.",
	},
	{
		title: "Проверить расчёт",
		label: "источники и условия расчёта",
		prompt:
			"Проверь расчёт: покажи источники, версии входных данных, условия расчёта и позиции, требующие подтверждения.",
	},
]);

export function KolibriApp({
	initialThreadId,
}: {
	initialThreadId?: string;
}) {
	const aui = useAui({
		 suggestions: kolibriSuggestions,
		 tools: Tools({ toolkit: kolibriToolkit }),
		 unstable_interactables: unstable_Interactables(),
	});

	return (
		<AuiProvider value={aui}>
			{initialThreadId ? <ThreadDeepLink initialThreadId={initialThreadId} /> : null}
			{process.env.NEXT_PUBLIC_ENABLE_INTERACTABLES_SPIKE === "true" ? (
				<EstimateDraftInteractableSpike />
			) : null}
			<WorkspaceShell />
		</AuiProvider>
	);
}
