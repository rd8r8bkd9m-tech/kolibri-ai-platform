import {
	Braces,
	CheckCircle2,
	FilePenLine,
	FolderOpen,
	LayoutList,
	ShieldCheck,
	Table2,
} from "lucide-react";
import type { CanvasDefaultViewProps } from "./canvas-preview-views";

const ALLOWED_BLOCKS = [
	{ label: "Заголовок", icon: FilePenLine },
	{ label: "Текст", icon: LayoutList },
	{ label: "Таблица", icon: Table2 },
	{ label: "Доказательство", icon: ShieldCheck },
	{ label: "Ссылка на файл", icon: FolderOpen },
] as const;

export function EditorView({ projectLabel }: CanvasDefaultViewProps) {
	return (
		<div className="grid min-h-0 flex-1 grid-cols-1 @min-[960px]:grid-cols-[192px_minmax(0,1fr)_204px]">
			<aside className="border-border/80 bg-muted/20 hidden min-h-0 border-r p-3 @min-[960px]:block">
				<div className="text-muted-foreground mb-3 flex items-center gap-2 px-2 text-[11px] font-semibold tracking-wide uppercase">
					<Braces className="size-4" aria-hidden="true" />
					Разрешённые блоки
				</div>
				<ul className="space-y-1" aria-label="Разрешённые компоненты редактора">
					{ALLOWED_BLOCKS.map(({ label, icon: Icon }) => (
						<li key={label} className="border-border/70 bg-background text-muted-foreground flex items-center gap-2 rounded-md border px-2.5 py-2 text-xs">
							<Icon className="size-4" aria-hidden="true" />
							{label}
						</li>
					))}
				</ul>
			</aside>

			<section className="min-h-0 overflow-auto bg-[linear-gradient(to_right,rgba(120,120,120,0.055)_1px,transparent_1px),linear-gradient(to_bottom,rgba(120,120,120,0.055)_1px,transparent_1px)] bg-[size:24px_24px] p-3 @min-[560px]:p-5" aria-labelledby="editor-preview-title">
				<div className="border-border/80 bg-card mx-auto flex min-h-[520px] w-full max-w-3xl flex-col rounded-xl border shadow-[0_18px_50px_-36px_rgba(15,23,42,0.55)]">
					<header className="border-border/70 border-b px-4 py-3">
						<p className="text-muted-foreground text-[11px]">{projectLabel}</p>
						<h2 id="editor-preview-title" className="mt-0.5 text-sm font-semibold">Декларативный редактор</h2>
					</header>
					<div className="flex flex-1 items-center justify-center p-5">
						<div className="border-border text-muted-foreground flex w-full max-w-md flex-col items-center rounded-xl border border-dashed px-6 py-12 text-center">
							<FilePenLine className="mb-3 size-6" aria-hidden="true" />
							<p className="text-foreground text-sm font-medium">Полотно пусто</p>
							<p className="mt-1.5 text-xs leading-relaxed">
								Компоненты появятся после получения типизированного дерева. Произвольные разметка и сценарии не принимаются.
							</p>
						</div>
					</div>
					<footer className="border-border/70 text-muted-foreground flex flex-wrap items-center gap-x-4 gap-y-2 border-t px-4 py-2.5 text-[10px]">
						<span className="flex items-center gap-1.5">
							<CheckCircle2 className="size-4 text-teal-600" aria-hidden="true" />
							Только компоненты из разрешённого набора
						</span>
						<span>Схема не загружена</span>
					</footer>
				</div>
			</section>

			<aside className="border-border/80 bg-muted/20 hidden min-h-0 border-l p-3 @min-[960px]:block">
				<div className="text-muted-foreground mb-3 text-[11px] font-semibold tracking-wide uppercase">Свойства</div>
				<div className="border-border text-muted-foreground rounded-lg border border-dashed px-3 py-5 text-center text-[11px] leading-relaxed">
					Выберите разрешённый блок, чтобы увидеть его типизированные свойства
				</div>
			</aside>
		</div>
	);
}

export function FilesView({ projectLabel }: CanvasDefaultViewProps) {
	return (
		<section className="flex min-h-0 flex-1 flex-col" aria-labelledby="files-preview-title">
			<header className="border-border/70 bg-muted/15 flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3">
				<div className="min-w-0">
					<p className="text-muted-foreground truncate text-[11px]">{projectLabel} / Файлы проекта</p>
					<h2 id="files-preview-title" className="mt-0.5 text-sm font-semibold">Файловый менеджер</h2>
				</div>
			</header>
			<div className="border-border/70 text-muted-foreground hidden grid-cols-[minmax(0,1fr)_120px_120px] border-b px-4 py-2 text-[11px] font-medium @min-[560px]:grid">
				<span>Имя</span><span>Версия</span><span>Статус</span>
			</div>
			<div className="flex flex-1 items-center justify-center p-6">
				<div className="max-w-sm text-center">
					<span className="bg-muted text-muted-foreground mx-auto mb-4 grid size-12 place-items-center rounded-xl">
						<FolderOpen className="size-5" aria-hidden="true" />
					</span>
					<p className="text-sm font-medium">Файлы не загружены</p>
					<p className="text-muted-foreground mt-1.5 text-xs leading-relaxed">
						Проверенные вложения, документы и их версии появятся здесь после получения данных проекта.
					</p>
					<div className="border-border bg-muted/20 text-muted-foreground mt-4 rounded-lg border px-3 py-2.5 text-[11px]">
						Пустое состояние — это не утверждение об артефактах проекта
					</div>
				</div>
			</div>
		</section>
	);
}
