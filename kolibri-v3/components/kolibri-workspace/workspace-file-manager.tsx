"use client";

import { useAssistantContext } from "@assistant-ui/react";
import {
	AlertCircle,
	ArrowLeft,
	RefreshCw,
	Search,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
	Tooltip,
	TooltipContent,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import type { WorkspaceCatalogLoadState } from "@/lib/workspace-documents";
import type {
	WorkspaceFile,
	WorkspaceFileCategory,
	WorkspaceFileKind,
} from "@/lib/workspace-types";
import {
	CatalogError,
	CatalogLoading,
	FileList,
} from "./workspace-file-manager-states";

export type { WorkspaceFile, WorkspaceFileCategory, WorkspaceFileKind };

const FILE_CATEGORIES: readonly {
	id: WorkspaceFileCategory;
	label: string;
}[] = [
	{ id: "all", label: "Все файлы" },
	{ id: "documents", label: "Документы" },
	{ id: "contracts", label: "Договоры" },
	{ id: "estimates", label: "Сметы" },
	{ id: "drawings", label: "Чертежи" },
	{ id: "attachments", label: "Вложения" },
];

export function WorkspaceFileManager({
	backLabel = "Назад к инструментам",
	catalogState = "ready",
	initialCategory = "all",
	files = [],
	onBack,
	onOpenFile,
	onRetry,
	projectLabel,
	title = "Файлы",
}: {
	backLabel?: string;
	catalogState?: WorkspaceCatalogLoadState;
	files?: readonly WorkspaceFile[];
	initialCategory?: WorkspaceFileCategory;
	onBack?: () => void;
	onOpenFile: (file: WorkspaceFile) => void;
	onRetry?: () => void;
	projectLabel: string;
	title?: string;
}) {
	const [activeCategory, setActiveCategory] =
		useState<WorkspaceFileCategory>(initialCategory);
	const [query, setQuery] = useState("");

	useEffect(() => {
		setActiveCategory(initialCategory);
	}, [initialCategory]);

	const categoryCounts = useMemo(
		() =>
			Object.fromEntries(
				FILE_CATEGORIES.map(({ id }) => [
					id,
					id === "all"
						? files.length
						: files.filter((file) => file.category === id).length,
				]),
			) as Record<WorkspaceFileCategory, number>,
		[files],
	);

	const visibleFiles = useMemo(() => {
		const normalizedQuery = query.trim().toLocaleLowerCase("ru-RU");

		return files.filter((file) => {
			const inCategory =
				activeCategory === "all" || file.category === activeCategory;
			const matchesQuery =
				!normalizedQuery ||
				file.name.toLocaleLowerCase("ru-RU").includes(normalizedQuery);
			return inCategory && matchesQuery;
		});
	}, [activeCategory, files, query]);
	const activeCategoryLabel =
		FILE_CATEGORIES.find(({ id }) => id === activeCategory)?.label ??
		"Все файлы";

	useAssistantContext({
		getContext: () =>
			[
				`Open project file manager: ${projectLabel}.`,
				`Active category: ${activeCategory}.`,
				`Search query: ${query.trim() || "none"}.`,
				`Visible artifacts: ${
					visibleFiles
						.map((file) => `${file.name} [${file.status}]`)
						.join("; ") || "none"
				}.`,
			].join("\n"),
	});

	return (
		<section
			data-slot="workspace-file-manager"
			className="relative flex min-h-0 flex-1 flex-col"
			aria-labelledby="workspace-files-title"
		>
			<h2 id="workspace-files-title" className="sr-only">
				{title}
			</h2>

			<header className="border-border/80 flex h-11 shrink-0 items-center gap-1.5 border-b px-2">
				{onBack ? (
					<Tooltip>
						<TooltipTrigger asChild>
							<Button
								type="button"
								variant="ghost"
								size="icon-xs"
								className="size-7 rounded-lg"
								onClick={onBack}
								aria-label={backLabel}
							>
								<ArrowLeft className="size-4" aria-hidden="true" />
							</Button>
						</TooltipTrigger>
						<TooltipContent side="bottom" sideOffset={6}>
							{backLabel}
						</TooltipContent>
					</Tooltip>
				) : null}

				<label className="shrink-0">
					<span className="sr-only">Категория файлов</span>
					<select
						value={activeCategory}
						onChange={(event) =>
							setActiveCategory(event.target.value as WorkspaceFileCategory)
						}
						className="border-input bg-background text-foreground focus-visible:ring-ring h-7 max-w-36 rounded-lg border px-2 text-xs outline-none focus-visible:ring-2"
					>
						{FILE_CATEGORIES.map(({ id, label }) => (
							<option key={id} value={id}>
								{label} · {categoryCounts[id]}
							</option>
						))}
					</select>
				</label>

				<div className="relative ml-auto min-w-0 flex-1 @min-[520px]:max-w-64">
					<Search
						className="text-muted-foreground pointer-events-none absolute top-1/2 left-2 size-4 -translate-y-1/2"
						aria-hidden="true"
					/>
					<Input
						value={query}
						onChange={(event) => setQuery(event.target.value)}
						className="h-7 rounded-lg pl-7 text-xs shadow-none"
						placeholder="Поиск файлов"
						aria-label="Поиск файлов"
					/>
				</div>
			</header>

			{catalogState === "error" && files.length > 0 ? (
				<div
					role="alert"
					className="border-border flex shrink-0 items-center gap-2 border-b px-3 py-2 text-xs"
				>
					<AlertCircle
						className="text-destructive size-4 shrink-0"
						aria-hidden="true"
					/>
					<span className="min-w-0 flex-1">
						Не удалось обновить файлы. Показана последняя сохранённая версия.
					</span>
					{onRetry ? (
						<Button type="button" variant="ghost" size="xs" onClick={onRetry}>
							<RefreshCw aria-hidden="true" className="size-3.5" />
							Повторить
						</Button>
					) : null}
				</div>
			) : null}

			<div className="min-h-0 flex-1 overflow-auto">
					{catalogState === "loading" && files.length === 0 ? (
						<CatalogLoading />
					) : catalogState === "error" && files.length === 0 ? (
						<CatalogError onRetry={onRetry} />
					) : (
						<FileList
							activeCategoryLabel={activeCategoryLabel}
							files={visibleFiles}
							hasQuery={query.trim().length > 0}
							onOpenFile={onOpenFile}
							totalFileCount={files.length}
						/>
					)}
				</div>
			</section>
		);
}
