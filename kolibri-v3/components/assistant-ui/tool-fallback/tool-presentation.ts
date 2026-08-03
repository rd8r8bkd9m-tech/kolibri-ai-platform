import type { ToolCallMessagePartStatus } from "@assistant-ui/react";
import {
	AlertCircleIcon,
	FileSearchIcon,
	FileTextIcon,
	GlobeIcon,
	ImagesIcon,
	LoaderIcon,
	type LucideIcon,
	PencilIcon,
	SquareTerminalIcon,
	WrenchIcon,
	XCircleIcon,
} from "lucide-react";

type ToolPresentation = {
	icon: LucideIcon;
	label: string;
};

export type ToolStatusPresentation = ToolPresentation & {
	isCancelled: boolean;
	isRunning: boolean;
};

const EXACT_TOOL_PRESENTATIONS: Readonly<
	Record<string, { running: string; complete: string; icon: LucideIcon }>
> = {
	project_case_analysis: {
		running: "Анализ исходных данных…",
		complete: "Исходные данные разобраны",
		icon: FileSearchIcon,
	},
	technology_card_build: {
		running: "Строится техкарта…",
		complete: "Техкарта подготовлена",
		icon: WrenchIcon,
	},
	price_candidates_apply: {
		running: "Независимо проверяются цены…",
		complete: "Ценовые кандидаты проверены",
		icon: FileSearchIcon,
	},
	price_candidates_verify: {
		running: "Независимо проверяются цены…",
		complete: "Ценовые кандидаты проверены",
		icon: FileSearchIcon,
	},
	estimate_engine_calculate: {
		running: "Рассчитывается смета…",
		complete: "Смета рассчитана",
		icon: WrenchIcon,
	},
	estimate_verification: {
		running: "Проверяется результат…",
		complete: "Проверка завершена",
		icon: FileSearchIcon,
	},
	create_estimate_document_pack: {
		running: "Формируется комплект документов…",
		complete: "Комплект документов подготовлен",
		icon: FileTextIcon,
	},
};

const TOOL_FAMILIES: ReadonlyArray<{
	match: readonly string[];
	icon: LucideIcon;
	running: string;
	complete: string;
}> = [
	{
		match: ["edit", "write", "patch"],
		icon: PencilIcon,
		running: "Редактирование…",
		complete: "Отредактирован файл",
	},
	{
		match: ["image", "screenshot"],
		icon: ImagesIcon,
		running: "Просмотр изображения…",
		complete: "Просмотрено изображение",
	},
	{
		match: ["exec", "shell", "terminal", "command"],
		icon: SquareTerminalIcon,
		running: "Выполняются команды…",
		complete: "Выполнены команды",
	},
	{
		match: ["browser", "web"],
		icon: GlobeIcon,
		running: "Открывается страница…",
		complete: "Просмотрена страница",
	},
	{
		match: ["read", "file", "search"],
		icon: FileSearchIcon,
		running: "Читаются файлы…",
		complete: "Прочитаны файлы",
	},
];

function getToolPresentation(
	toolName: string,
	running: boolean,
): ToolPresentation {
	const normalized = toolName.toLocaleLowerCase("en-US");
	const exact = EXACT_TOOL_PRESENTATIONS[normalized];
	if (exact) {
		return {
			icon: exact.icon,
			label: running ? exact.running : exact.complete,
		};
	}

	const family = TOOL_FAMILIES.find(({ match }) =>
		match.some((keyword) => normalized.includes(keyword)),
	);
	if (family) {
		return {
			icon: family.icon,
			label: running ? family.running : family.complete,
		};
	}

	return {
		icon: WrenchIcon,
		label: running ? "Выполняется действие…" : "Действие выполнено",
	};
}

export function getToolStatusPresentation(
	toolName: string,
	status?: ToolCallMessagePartStatus,
): ToolStatusPresentation {
	const statusType = status?.type ?? "complete";
	const isRunning = statusType === "running";
	const isCancelled =
		status?.type === "incomplete" && status.reason === "cancelled";
	const presentation = getToolPresentation(toolName, isRunning);

	return {
		icon:
			statusType === "running"
				? LoaderIcon
				: statusType === "incomplete"
					? XCircleIcon
					: statusType === "requires-action"
						? AlertCircleIcon
						: presentation.icon,
		label: isCancelled ? "Действие отменено" : presentation.label,
		isCancelled,
		isRunning,
	};
}
