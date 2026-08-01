import {
	AlertCircle,
	FileArchive,
	FileImage,
	FileSignature,
	FileSpreadsheet,
	Files,
	FileText,
	LoaderCircle,
	type LucideIcon,
	RefreshCw,
	Search,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { WorkspaceFile, WorkspaceFileKind } from "@/lib/workspace-types";

const FILE_KIND_ICON: Record<WorkspaceFileKind, LucideIcon> = {
	document: FileText,
	contract: FileSignature,
	estimate: FileSpreadsheet,
	drawing: FileImage,
	attachment: FileArchive,
};

export function CatalogLoading() {
	return (
		<div role="status" aria-label="Загружаю файлы">
			<div
				data-slot="workspace-file-loading-grid"
				className="grid grid-cols-2 gap-3 px-4 pt-1 min-[960px]:hidden"
			>
				{Array.from({ length: 6 }, (_, index) => (
					<div
						key={index}
						className="border-border bg-muted/55 h-[10.75rem] animate-pulse rounded-[1.75rem] border"
					/>
				))}
			</div>
			<div className="text-muted-foreground hidden min-h-56 flex-col items-center justify-center px-5 text-center min-[960px]:flex">
				<LoaderCircle className="mb-3 size-5 animate-spin" aria-hidden="true" />
				<p className="text-foreground text-xs font-medium">Загружаю файлы</p>
				<p className="mt-1 max-w-sm text-[10px] leading-4">
					Kolibri восстанавливает каталог документов проекта.
				</p>
			</div>
		</div>
	);
}

export function CatalogError({ onRetry }: { onRetry?: () => void }) {
	return (
		<div
			role="alert"
			className="text-muted-foreground flex min-h-56 flex-col items-center justify-center px-5 text-center"
		>
			<AlertCircle className="text-destructive mb-3 size-5" aria-hidden="true" />
			<p className="text-foreground text-xs font-medium">
				Не удалось загрузить файлы
			</p>
			<p className="mt-1 max-w-sm text-[10px] leading-4">
				Данные не потеряны. Проверьте соединение и повторите загрузку.
			</p>
			{onRetry ? (
				<Button
					type="button"
					variant="outline"
					size="sm"
					className="mt-4"
					onClick={onRetry}
				>
					<RefreshCw aria-hidden="true" className="size-3.5" />
					Повторить
				</Button>
			) : null}
		</div>
	);
}

export function FileList({
	activeCategoryLabel,
	files,
	hasQuery,
	onOpenFile,
	totalFileCount,
}: {
	activeCategoryLabel: string;
	files: readonly WorkspaceFile[];
	hasQuery: boolean;
	onOpenFile: (file: WorkspaceFile) => void;
	totalFileCount: number;
}) {
	if (files.length === 0) {
		return (
			<NoFiles
				activeCategoryLabel={activeCategoryLabel}
				hasQuery={hasQuery}
				totalFileCount={totalFileCount}
			/>
		);
	}

	return (
		<div aria-label="Файлы проекта">
			<div
				aria-hidden="true"
				className="border-border/80 text-muted-foreground hidden h-8 grid-cols-[minmax(180px,1fr)_110px_86px_90px] items-center border-b px-3 text-[10px] font-medium @min-[760px]:grid"
			>
				<span>Имя</span>
				<span>Изменён</span>
				<span>Размер</span>
				<span>Статус</span>
			</div>
			{files.map((file) => {
				const Icon = FILE_KIND_ICON[file.kind];
				return (
					<button
						key={file.id}
						type="button"
						aria-label={`Открыть файл «${file.name}»`}
						onClick={() => onOpenFile(file)}
						className="border-border/65 hover:bg-muted/45 focus-visible:bg-muted/45 focus-visible:ring-ring grid min-h-12 w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b px-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-inset @min-[760px]:grid-cols-[minmax(180px,1fr)_110px_86px_90px]"
					>
						<span className="flex min-w-0 items-center gap-2.5">
							<span className="bg-muted text-muted-foreground grid size-7 shrink-0 place-items-center rounded-md">
								<Icon className="size-4" aria-hidden="true" />
							</span>
							<span className="min-w-0">
								<span className="block truncate text-xs font-medium">
									{file.name}
								</span>
								<span className="text-muted-foreground mt-0.5 block truncate text-[10px]">
									{file.projectName ? `${file.projectName} · ` : ""}
									{file.modifiedAt} · {file.size}
								</span>
							</span>
						</span>
						<span className="text-muted-foreground hidden text-[10px] @min-[760px]:block">
							{file.modifiedAt}
						</span>
						<span className="text-muted-foreground hidden text-[10px] @min-[760px]:block">
							{file.size}
						</span>
						<span className="text-muted-foreground text-[10px]">
							{file.status}
						</span>
					</button>
				);
			})}
		</div>
	);
}

function NoFiles({
	activeCategoryLabel,
	hasQuery,
	totalFileCount,
}: {
	activeCategoryLabel: string;
	hasQuery: boolean;
	totalFileCount: number;
}) {
	const categoryEmpty = !hasQuery && totalFileCount > 0;
	return (
		<div className="text-muted-foreground flex min-h-64 flex-col items-center justify-center px-5 text-center">
			{hasQuery ? (
				<Search className="mb-3 size-5" aria-hidden="true" />
			) : (
				<Files className="mb-3 size-5" aria-hidden="true" />
			)}
			<p className="text-foreground text-xs font-medium">
				{hasQuery
					? "Ничего не найдено"
					: categoryEmpty
						? `В разделе «${activeCategoryLabel}» пока пусто`
						: "В проекте пока нет файлов"}
			</p>
			<p className="mt-1 max-w-64 text-[10px] leading-relaxed">
				{hasQuery
					? "Измените категорию или поисковый запрос."
					: categoryEmpty
						? "Выберите «Все файлы», чтобы увидеть документы из других разделов."
						: "Документы, сметы, договоры и вложения появятся здесь после создания или загрузки."}
			</p>
		</div>
	);
}
