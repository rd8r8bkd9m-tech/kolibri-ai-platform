"use client";

import Image from "next/image";
import { DownloadIcon, ExternalLinkIcon, FileArchiveIcon, FileTextIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { kolibriGenerativeUIComponentSchemas } from "@/lib/generative-ui/schema";
import type { z } from "zod";
import { EstimateDocumentPreview } from "./estimate-document-preview";

type EstimateDocumentPackProps = z.infer<
	typeof kolibriGenerativeUIComponentSchemas.EstimateDocumentPack
>;

const statusLabel: Record<EstimateDocumentPackProps["status"], string> = {
	needs_input: "Нужны данные",
	failed: "Не удалось сформировать",
	preliminary: "Предварительный комплект",
	issued: "Официальный выпуск",
	revoked: "Отозван",
};

function fileLabel(kind: EstimateDocumentPackProps["files"][number]["kind"]) {
	return { pdf: "PDF", zip: "ZIP", xlsx: "Excel", docx: "Word" }[kind];
}

export function EstimateDocumentPackWidget(
	initial: EstimateDocumentPackProps,
) {
	const { $type: _type, ...rawProps } = initial as EstimateDocumentPackProps & {
		$type?: string;
	};
	void _type;
	const parsed = kolibriGenerativeUIComponentSchemas.EstimateDocumentPack.safeParse(
		rawProps,
	);
	if (!parsed.success) {
		return (
			<section className="rounded-2xl border border-border bg-card p-4" aria-label="Комплект документов">
				<p className="text-sm text-muted-foreground">Комплект документов пока недоступен.</p>
			</section>
		);
	}
	const pack = parsed.data;
	const pdf = pack.files.find((file) => file.kind === "pdf");
	const zip = pack.files.find((file) => file.kind === "zip");

	return (
		<section
			className="overflow-hidden rounded-2xl border border-border bg-card"
			aria-label="Комплект официальных сметных документов"
			data-document-pack-status={pack.status}
		>
			<div className="flex items-start gap-3 p-4">
				<Image
					alt=""
					aria-hidden="true"
					className="size-10 shrink-0 rounded-xl object-cover"
					height={40}
					src="/pets/masters/kolibri-v1.png"
					width={40}
				/>
				<div className="min-w-0 flex-1">
					<div className="flex flex-wrap items-center gap-2">
						<h3 className="text-sm font-semibold">Комплект сметных документов</h3>
						<span className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground">
							{statusLabel[pack.status]}
						</span>
					</div>
					<p className="mt-1 text-xs text-muted-foreground">
						{pack.documentNumber ? `№ ${pack.documentNumber} · ` : ""}версия сметы {pack.estimateVersion} · {pack.rendererVersion}
					</p>
				</div>
			</div>

			{pack.preview ? <EstimateDocumentPreview initial={pack} /> : null}

			{pack.requiredFields.length > 0 ? (
				<div className="border-t border-border bg-muted/20 px-4 py-3">
					<p className="text-sm font-medium">Заполните, чтобы продолжить:</p>
					<ul className="mt-1 list-disc pl-5 text-sm text-muted-foreground">
						{pack.requiredFields.map((field) => <li key={field}>{field}</li>)}
					</ul>
				</div>
			) : null}

			{pack.files.length > 0 ? (
				<div className="flex flex-wrap gap-2 border-t border-border p-4">
					{pdf ? (
						<Button asChild size="sm" variant="default">
							<a href={pdf.downloadUrl} target="_blank" rel="noreferrer" aria-label="Открыть PDF комплекта">
								<ExternalLinkIcon aria-hidden="true" /> Открыть PDF
							</a>
						</Button>
					) : null}
					{pdf ? (
						<Button asChild size="sm" variant="outline">
							<a href={pdf.downloadUrl} download={pdf.filename} aria-label="Скачать PDF комплекта">
								<DownloadIcon aria-hidden="true" /> Скачать PDF
							</a>
						</Button>
					) : null}
					{zip ? (
						<Button asChild size="sm" variant="outline">
							<a href={zip.downloadUrl} download={zip.filename} aria-label="Скачать ZIP комплекта">
								<FileArchiveIcon aria-hidden="true" /> Скачать ZIP
							</a>
						</Button>
					) : null}
					{pack.files.filter((file) => file.kind !== "pdf" && file.kind !== "zip").map((file) => (
						<Button key={file.artifactId} asChild size="sm" variant="ghost">
							<a href={file.downloadUrl} download={file.filename} aria-label={`Скачать ${fileLabel(file.kind)}`}>
								<DownloadIcon aria-hidden="true" /> {fileLabel(file.kind)}
							</a>
						</Button>
					))}
				</div>
			) : (
				<div className="border-t border-border px-4 py-3 text-sm text-muted-foreground">
					<FileTextIcon aria-hidden="true" className="mr-2 inline size-4" /> Файлы появятся после заполнения обязательных данных.
				</div>
			)}
		</section>
	);
}
