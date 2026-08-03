"use client";

import { useMemo, useState } from "react";
import {
	CheckCircle2Icon,
	ChevronDownIcon,
	FileCheck2Icon,
	LoaderCircleIcon,
	TriangleAlertIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { withCsrfHeader } from "@/lib/csrf";
import { kolibriGenerativeUIComponentSchemas } from "@/lib/generative-ui/schema";
import type { z } from "zod";

type Preview = NonNullable<
	z.infer<typeof kolibriGenerativeUIComponentSchemas.EstimateDocumentPack>["preview"]
>;

type Pack = z.infer<
	typeof kolibriGenerativeUIComponentSchemas.EstimateDocumentPack
>;

const money = (value: string) => {
	const match = /^(\d+)(?:\.(\d{2}))?$/.exec(value);
	if (!match) return value;
	const integer = match[1].replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0");
	return `${integer},${match[2] ?? "00"}`;
};

const statusLabel = (status: Pack["status"]) =>
	({
		needs_input: "Нужны данные",
		failed: "Не удалось сформировать",
		preliminary: "Предварительный просмотр",
		issued: "Официальный выпуск",
		revoked: "Отозван",
		})[status];

function MetaTable({ preview }: { preview: Preview }) {
	return (
		<div className="estimate-preview-meta">
			<div><b>Исполнитель</b><span>{preview.contractorName ?? "Не назначен"}</span></div>
			<div><b>Заказчик</b><span>{preview.customerName ?? "Не назначен"}</span></div>
			<div><b>Объект</b><span>{preview.objectName}</span></div>
			<div><b>Регион</b><span>{preview.region}</span></div>
			<div><b>Дата</b><span>{preview.date}</span></div>
			<div><b>Статус</b><span>{preview.mode === "preliminary" ? "PRELIMINARY" : "ISSUED"}</span></div>
		</div>
	);
}

function PageHeading({ title, subtitle }: { title: string; subtitle: string }) {
	return (
		<div className="estimate-preview-heading">
			<h3>{title}</h3>
			<p>{subtitle}</p>
		</div>
	);
}

function SummaryPage({ preview }: { preview: Preview }) {
	return (
		<section className="estimate-preview-page">
			<PageHeading title="КОММЕРЧЕСКАЯ СМЕТА" subtitle={`Срок действия: до ${preview.validUntil}`} />
			<MetaTable preview={preview} />
			<h4>Сводный расчёт стоимости</h4>
			<div className="estimate-preview-table-wrap">
				<table><thead><tr><th>№</th><th>Раздел</th><th>Итого</th></tr></thead><tbody>
					{preview.sections.map((section, index) => <tr key={`${section.name}-${index}`}><td>{index + 1}</td><td>{section.name}</td><td>{money(section.total)} руб.</td></tr>)}
				</tbody></table>
			</div>
			<div className="estimate-preview-totals">
				<div><span>Прямые затраты</span><b>{money(preview.directTotal)} руб.</b></div>
				<div><span>Резерв</span><b>{money(preview.reserve)} руб.</b></div>
				<div className="is-total"><span>Итого к оплате</span><b>{money(preview.total)} руб.</b></div>
			</div>
			<div className="estimate-preview-facts">
				<div><b>Сметная стоимость</b><span>{money(preview.total)} руб.</span></div>
				<div><b>Сумма прописью</b><span>{preview.totalWords}</span></div>
				<div><b>Налоговый режим</b><span>{preview.taxMode}</span></div>
			</div>
			<h4>Условия и границы расчёта</h4>
			<ol>{(preview.conditions.length ? preview.conditions : ["Исходные данные и цены требуют проверки перед заключением договора."]).map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ol>
		</section>
	);
}

function LinesPage({ preview, title, resource }: { preview: Preview; title: string; resource?: boolean }) {
	return (
		<section className="estimate-preview-page">
			<PageHeading title={title} subtitle="По составу и стоимости работ/затрат" />
			<MetaTable preview={preview} />
			<div className="estimate-preview-table-wrap">
				<table className="estimate-preview-lines"><thead><tr>
					<th>№</th><th>{resource ? "Код" : "Раздел"}</th><th>{resource ? "Наименование ресурса" : "Наименование работ и затрат"}</th><th>Ед.</th><th>Кол-во</th><th>Цена, руб.</th><th>Стоимость, руб.</th>
				</tr></thead><tbody>
					{preview.lines.map((line) => <tr key={`${line.position}-${line.description}`}>
						<td>{line.position}</td><td>{resource ? `RES-${String(line.position).padStart(3, "0")}` : line.section}</td><td>{line.description}</td><td>{line.unit}</td><td className="is-number">{line.quantity}</td><td className="is-number">{money(line.unitPrice)}</td><td className="is-number">{money(line.lineTotal)}</td>
					</tr>)}
				</tbody></table>
			</div>
			{preview.truncated ? <p className="estimate-preview-note">Показаны первые {preview.lines.length} из {preview.totalLines} строк. Полный состав доступен в скачиваемом комплекте.</p> : null}
			<div className="estimate-preview-total-line"><span>Итого</span><b>{money(preview.directTotal)} руб.</b></div>
		</section>
	);
}

function AnalysisPage({ preview }: { preview: Preview }) {
	return (
		<section className="estimate-preview-page">
			<PageHeading title="КОНЪЮНКТУРНЫЙ АНАЛИЗ" subtitle="Сведения о применённых ценах и их качестве" />
			<MetaTable preview={preview} />
			<div className="estimate-preview-table-wrap">
				<table><thead><tr><th>№</th><th>Ресурс</th><th>Цена, руб.</th><th>Статус</th></tr></thead><tbody>
					{preview.lines.map((line) => <tr key={`analysis-${line.position}`}><td>{line.position}</td><td>{line.description}</td><td className="is-number">{money(line.unitPrice)}</td><td>{line.confidence || "Требует проверки"}</td></tr>)}
				</tbody></table>
			</div>
			<p className="estimate-preview-note">{preview.mode === "preliminary" ? "PRELIMINARY — цены требуют подтверждения перед официальным выпуском." : "ISSUED — документ выпущен по зафиксированной версии сметы."}</p>
		</section>
	);
}

function AppendixPage({ preview }: { preview: Preview }) {
	return (
		<section className="estimate-preview-page">
			<PageHeading title="ПРИЛОЖЕНИЕ № 1" subtitle="График платежей и условия/границы расчёта" />
			<MetaTable preview={preview} />
			<h4>1. График этапов и платежей</h4>
			<div className="estimate-preview-table-wrap"><table><thead><tr><th>№</th><th>Этап</th><th>Доля, %</th></tr></thead><tbody>
				{preview.paymentSchedule.map((item, index) => <tr key={`${index}-${item.label}`}><td>{index + 1}</td><td>{item.label}</td><td>{item.percent}</td></tr>)}
			</tbody></table></div>
			<div className="estimate-preview-columns"><div><h4>2. Принято в расчёте</h4><ul>{(preview.conditions.length ? preview.conditions : ["Не указано"]).map((item) => <li key={item}>{item}</li>)}</ul></div><div><h4>Не включено в расчёт</h4><ul>{(preview.exclusions.length ? preview.exclusions : ["Работы и поставки, не перечисленные в строках сметы."]).map((item) => <li key={item}>{item}</li>)}</ul></div></div>
			<h4>3. Порядок уточнения</h4>
			<p className="estimate-preview-note">Изменение исходных данных оформляется новой версией сметы и не меняет этот просмотр.</p>
		</section>
	);
}

export function EstimateDocumentPreview({
	initial,
}: {
	initial: Pack;
}) {
	const [open, setOpen] = useState(true);
	const [pack, setPack] = useState(initial);
	const [issuing, setIssuing] = useState(false);
	const [issueError, setIssueError] = useState("");
	const preview = pack.preview;
	const canIssue = pack.status === "preliminary" && Boolean(preview);
	const issueLabel = useMemo(() => (pack.status === "issued" ? "Официальный выпуск готов" : "Выпустить официальный"), [pack.status]);

	async function issueOfficial() {
		if (!preview || !canIssue || issuing) return;
		setIssuing(true);
		setIssueError("");
		try {
			const response = await fetch(`/api/v3/projects/${encodeURIComponent(pack.projectId)}/estimate/document-pack`, {
				method: "POST",
				credentials: "same-origin",
				cache: "no-store",
				headers: withCsrfHeader({
					Accept: "application/json",
					"Content-Type": "application/json",
					"Idempotency-Key": `document-pack-ui-${crypto.randomUUID()}`,
				}),
				body: JSON.stringify({ estimateVersion: pack.estimateVersion, requestedKinds: ["pack"], mode: "issue" }),
			});
			const value = (await response.json()) as unknown;
			if (!response.ok) {
				const message = typeof value === "object" && value !== null && "message" in value && typeof value.message === "string" ? value.message : "Официальный выпуск пока недоступен.";
				throw new Error(message);
			}
			const parsed = kolibriGenerativeUIComponentSchemas.EstimateDocumentPack.safeParse(value);
			if (!parsed.success) throw new Error("Сервер вернул неполный выпуск документа.");
			setPack(parsed.data);
		} catch (error) {
			setIssueError(error instanceof Error ? error.message : "Официальный выпуск пока недоступен.");
		} finally {
			setIssuing(false);
		}
	}

	return (
		<section className="estimate-document-preview-shell" data-slot="estimate-document-preview">
			<header className="estimate-document-preview-toolbar">
				<div><p className="text-sm font-semibold">Предпросмотр документа</p><p className="text-xs text-muted-foreground">{pack.documentNumber ? `№ ${pack.documentNumber} · ` : ""}версия сметы {pack.estimateVersion}</p></div>
				<div className="flex flex-wrap items-center gap-2">
					<span className={`estimate-preview-status ${pack.status}`}>{statusLabel(pack.status)}</span>
					{canIssue ? <Button type="button" size="sm" onClick={issueOfficial} disabled={issuing}>{issuing ? <LoaderCircleIcon className="size-4 animate-spin" aria-hidden="true" /> : <FileCheck2Icon className="size-4" aria-hidden="true" />}{issuing ? "Выпускаю…" : "Выпустить официальный"}</Button> : null}
					<Button type="button" size="sm" variant="ghost" onClick={() => setOpen((value) => !value)} aria-expanded={open}><ChevronDownIcon className={`size-4 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true" />{open ? "Свернуть" : "Открыть"}</Button>
				</div>
			</header>
			{issueError ? <div className="estimate-preview-error"><TriangleAlertIcon className="size-4 shrink-0" aria-hidden="true" />{issueError}</div> : null}
			{pack.status === "issued" ? <div className="estimate-preview-success"><CheckCircle2Icon className="size-4" aria-hidden="true" />Документ зафиксирован. Скачивание доступно в карточке выпуска.</div> : null}
			{open && preview ? <div className="estimate-document-preview-pages"><SummaryPage preview={preview} /><LinesPage preview={preview} title="ЛОКАЛЬНЫЙ СМЕТНЫЙ РАСЧЁТ" /><LinesPage preview={preview} title="РЕСУРСНАЯ ВЕДОМОСТЬ" resource /><AnalysisPage preview={preview} /><AppendixPage preview={preview} /></div> : null}
		</section>
	);
}
