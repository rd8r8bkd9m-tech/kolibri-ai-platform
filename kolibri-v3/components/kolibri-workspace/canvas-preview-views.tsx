import { FileText, Table2 } from "lucide-react";

export type CanvasDefaultViewProps = {
	projectLabel: string;
};

export function EstimateView({ projectLabel }: CanvasDefaultViewProps) {
	return (
		<section
			className="bg-background flex min-h-0 flex-1 flex-col"
			aria-labelledby="estimate-preview-title"
		>
			<header className="border-border/80 flex min-h-12 items-center justify-between gap-3 border-b px-3 @min-[560px]:px-4">
				<div className="min-w-0">
					<h2 id="estimate-preview-title" className="truncate text-sm font-medium">
						Черновик сметы
					</h2>
					<p className="text-muted-foreground truncate text-[11px]">
						{projectLabel}
					</p>
				</div>
			</header>

			<div className="min-h-0 flex-1 overflow-auto">
				<table className="h-full w-full min-w-[680px] border-collapse text-left text-xs">
					<caption className="sr-only">Редактор сметы без позиций</caption>
					<thead>
						<tr className="border-border text-muted-foreground border-b">
							<th className="w-12 px-3 py-2.5 font-medium" scope="col">№</th>
							<th className="min-w-60 px-3 py-2.5 font-medium" scope="col">
								Наименование
							</th>
							<th className="w-24 px-3 py-2.5 font-medium" scope="col">
								Ед. изм.
							</th>
							<th className="w-28 px-3 py-2.5 text-right font-medium" scope="col">
								Количество
							</th>
							<th className="w-28 px-3 py-2.5 text-right font-medium" scope="col">
								Цена
							</th>
							<th className="w-32 px-3 py-2.5 text-right font-medium" scope="col">
								Стоимость
							</th>
						</tr>
					</thead>
					<tbody>
						<tr>
							<td colSpan={6} className="h-full px-6 py-16 text-center">
								<div className="text-muted-foreground mx-auto flex max-w-xs flex-col items-center">
									<Table2 className="mb-3 size-5" aria-hidden="true" />
									<p className="text-foreground text-sm font-medium">Пока нет позиций</p>
									<p className="mt-1 text-xs">Добавьте исходные данные в диалоге.</p>
								</div>
							</td>
						</tr>
					</tbody>
				</table>
			</div>

			<footer className="border-border/80 text-muted-foreground flex min-h-9 items-center justify-between gap-3 border-t px-3 text-[11px] @min-[560px]:px-4">
				<span>Нет расчётной версии</span>
				<span className="text-foreground font-medium tabular-nums">Итого —</span>
			</footer>
		</section>
	);
}

export function DocumentView({ projectLabel }: CanvasDefaultViewProps) {
	return (
		<div className="grid min-h-0 flex-1 grid-cols-1 @min-[760px]:grid-cols-[184px_minmax(0,1fr)]">
			<aside className="border-border/80 bg-muted/20 hidden border-r p-3 @min-[760px]:block">
				<div className="text-muted-foreground mb-3 px-2 text-[11px] font-semibold tracking-wide uppercase">
					Оглавление
				</div>
				<div className="border-border text-muted-foreground rounded-lg border border-dashed px-3 py-5 text-center text-[11px] leading-relaxed">
					Разделы документа ещё не созданы
				</div>
			</aside>

			<section
				className="min-h-0 overflow-auto bg-stone-100/70 p-3 dark:bg-black/15 @min-[540px]:p-5 @min-[820px]:p-8"
				aria-labelledby="document-preview-title"
			>
				<article className="border-border/80 bg-card mx-auto min-h-[680px] w-full max-w-[760px] rounded-sm border px-6 py-8 shadow-[0_18px_50px_-34px_rgba(15,23,42,0.55)] @min-[560px]:px-12 @min-[560px]:py-12">
					<div className="border-border/70 text-muted-foreground flex flex-wrap items-center justify-between gap-2 border-b pb-4 text-[10px] tracking-wide uppercase">
						<span>{projectLabel}</span>
						<span>Предпросмотр документа</span>
					</div>
					<div className="mx-auto flex min-h-[520px] max-w-xl flex-col items-center justify-center text-center">
						<span className="bg-muted text-muted-foreground mb-5 grid size-12 place-items-center rounded-xl">
							<FileText className="size-5" aria-hidden="true" />
						</span>
						<p className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
							Черновик без версии
						</p>
						<h2 id="document-preview-title" className="text-2xl font-semibold tracking-tight @min-[560px]:text-3xl">
							Документ ещё не сформирован
						</h2>
						<p className="text-muted-foreground mt-3 max-w-md text-sm leading-6">
							Заголовок, реквизиты и содержание появятся после выбора проверенного шаблона и подтверждения входных данных.
						</p>
						<div className="mt-8 w-full space-y-3" aria-hidden="true">
							<div className="bg-muted/70 mx-auto h-2 w-4/5 rounded-full" />
							<div className="bg-muted/70 mx-auto h-2 w-full rounded-full" />
							<div className="bg-muted/70 mx-auto h-2 w-11/12 rounded-full" />
							<div className="bg-muted/70 mx-auto h-2 w-3/5 rounded-full" />
						</div>
					</div>
					<div className="border-border/70 text-muted-foreground flex items-center justify-between border-t pt-4 text-[10px]">
						<span>Предпросмотр, не выпуск</span>
						<span>Версия —</span>
					</div>
				</article>
			</section>
		</div>
	);
}
