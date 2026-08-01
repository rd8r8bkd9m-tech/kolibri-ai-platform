import { FilePenLine, FileSpreadsheet, Files, FileText, type LucideIcon } from "lucide-react";
import type { ComponentType } from "react";
import { createCanvasSurfaceRegistry, DEFAULT_CANVAS_CAPABILITIES } from "@/lib/workspace-canvas";
import { EditorView, FilesView } from "./canvas-editor-views";
import { DocumentView, EstimateView, type CanvasDefaultViewProps } from "./canvas-preview-views";

export const CANVAS_VIEW_ALLOWLIST = ["estimate", "document", "editor", "files"] as const;
export type CanvasMode = (typeof CANVAS_VIEW_ALLOWLIST)[number];

type CanvasViewDefinition = {
	icon: LucideIcon;
	component: ComponentType<CanvasDefaultViewProps>;
	description: string;
};

export function isCanvasMode(value: unknown): value is CanvasMode {
	return CANVAS_VIEW_ALLOWLIST.includes(value as CanvasMode);
}

export const CANVAS_VIEW_REGISTRY = createCanvasSurfaceRegistry<CanvasViewDefinition>([
	{
		id: "estimate",
		label: "Смета",
		capabilities: DEFAULT_CANVAS_CAPABILITIES,
		payload: { description: "Табличный расчёт", icon: FileSpreadsheet, component: EstimateView },
	},
	{
		id: "document",
		label: "Документ",
		capabilities: DEFAULT_CANVAS_CAPABILITIES,
		payload: { description: "Лист предпросмотра", icon: FileText, component: DocumentView },
	},
	{
		id: "editor",
		label: "Редактор",
		capabilities: DEFAULT_CANVAS_CAPABILITIES,
		payload: { description: "Типизированные блоки", icon: FilePenLine, component: EditorView },
	},
	{
		id: "files",
		label: "Файлы",
		capabilities: DEFAULT_CANVAS_CAPABILITIES,
		payload: { description: "Версии и вложения", icon: Files, component: FilesView },
	},
]);
