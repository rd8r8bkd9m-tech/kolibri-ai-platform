"use client";

import {
	ArrowLeft,
	ArrowRight,
	FileCheck2,
	FileText,
} from "lucide-react";
import { useRef, useState } from "react";
import { Reveal } from "./reveal";

function ChatDemo({ prompt, summary, fileTitle, fileType }: {
	prompt: string;
	summary: string;
	fileTitle: string;
	fileType: string;
}) {
	return (
		<div className="klp-role-demo-body" style={{ padding: "1.25rem" }}>
			<div className="klp-chat">
				<div className="klp-msg klp-msg-user">
					<div className="klp-bubble">{prompt}</div>
				</div>
				<div className="klp-msg">
					<div className="klp-ai-body">
						<strong>{summary}</strong>
						<div className="klp-file-card" style={{ marginTop: "0.8rem" }}>
							<span className="klp-file-icon"><FileText aria-hidden="true" /></span>
							<span className="klp-file-meta">
								<strong>{fileTitle}</strong>
								<span>Документ · {fileType}</span>
							</span>
						</div>
					</div>
				</div>
			</div>
		</div>
	);
}

function DocumentsDemo() {
	const docs = [
		{ title: "Коммерческое предложение", type: "DOCX", state: "готово" },
		{ title: "Договор подряда", type: "DOCX", state: "черновик" },
		{ title: "Счёт на оплату", type: "PDF", state: "в работе" },
	];
	return (
		<div className="klp-role-demo-body" style={{ padding: "1.25rem" }}>
			<div className="klp-chat">
				<div className="klp-msg klp-msg-user">
					<div className="klp-bubble">Сделай пакет документов по версии 3</div>
				</div>
				<div className="klp-msg">
					<div className="klp-ai-body">
						<strong>Готово — все документы из данных проекта.</strong>
						{docs.map((doc, index) => (
							<div className="klp-file-card" key={doc.title} style={{ marginTop: index === 0 ? "0.8rem" : "0.5rem" }}>
								<span className="klp-file-icon"><FileText aria-hidden="true" /></span>
								<span className="klp-file-meta">
									<strong>{doc.title}</strong>
									<span>{doc.type} · {doc.state}</span>
								</span>
							</div>
						))}
					</div>
				</div>
			</div>
		</div>
	);
}

const connectors = [
	{ name: "ФСНБ-2024", meta: "справочник базовых цен", mark: "Ф", bg: "#0F9D58" },
	{ name: "Норм. база", meta: "подбор по ГЭСН/ТЕР/ФЕР", mark: "Н", bg: "#5B6B7A" },
	{ name: "ФГИС ЦС", meta: "официальные цены", mark: "Ц", bg: "#009688" },
	{ name: "Т-Банк", meta: "оплата и доступ", mark: "Т", bg: "#FFDD2D", fg: "#1a1817" },
	{ name: "Excel", meta: "сметы и расчёты", mark: "X", bg: "#107C41" },
	{ name: "Word", meta: "КП и ведомость", mark: "W", bg: "#2B579A" },
	{ name: "PDF", meta: "сметы и пакеты", mark: "P", bg: "#E40F0F" },
	{ name: "Telegram", meta: "результаты и уведомления", mark: "T", bg: "#229ED9" },
];

function NormativesDemo() {
	return (
		<div className="klp-role-demo-body" style={{ padding: "1rem" }}>
			{connectors.map(({ bg, fg, mark, meta, name }) => (
				<div className="klp-connector" key={name}>
					<span
						className="klp-connector-icon is-brand"
						style={{ background: bg, color: fg ?? "#ffffff" }}
						aria-hidden="true"
					>
						{mark}
					</span>
					<span className="klp-connector-meta">
						<strong>{name}</strong>
						<span><i /> {meta}</span>
					</span>
				</div>
			))}
		</div>
	);
}

function VersionsDemo() {
	const steps = [
		["Поменял материал стен на версии 3", "2s"],
		["Пересчитал 18 позиций сметы", "4s"],
		["Сохранил причину изменения", "1s"],
		["Собрал версию 4 и документы", "3s"],
	] as const;
	return (
		<div className="klp-role-demo-body" style={{ padding: "1.25rem" }}>
			<ul className="klp-timeline">
				{steps.map(([text, time]) => (
					<li key={text}><span>{text}<i>{time}</i></span></li>
				))}
			</ul>
		</div>
	);
}

function ExportDemo() {
	const formats = [
		{ title: "Смета · версия 3", type: "XLSX" },
		{ title: "Коммерческое предложение", type: "PDF" },
		{ title: "Пакет документов", type: "DOCX" },
	];
	return (
		<div className="klp-role-demo-body" style={{ padding: "1.25rem" }}>
			<div className="klp-chat">
				<div className="klp-msg klp-msg-user">
					<div className="klp-bubble">Выгрузи смету и документы клиенту</div>
				</div>
				<div className="klp-msg">
					<div className="klp-ai-body">
						<strong>Готово — три файла в нужных форматах.</strong>
						{formats.map((file, index) => (
							<div className="klp-file-card" key={file.title} style={{ marginTop: index === 0 ? "0.8rem" : "0.5rem" }}>
								<span className="klp-file-icon"><FileCheck2 aria-hidden="true" /></span>
								<span className="klp-file-meta">
									<strong>{file.title}</strong>
									<span>Файл · {file.type}</span>
								</span>
							</div>
						))}
					</div>
				</div>
			</div>
		</div>
	);
}

const roles = [
	{
		title: "Сметы",
		text: "Опишите объект, объёмы и регион — агент соберёт работы, материалы, количества и цены в версионный расчёт.",
		demo: <ChatDemo prompt="Собери смету на каркасный дом 38 м²" summary="Смета готова — 68 позиций, версия 3." fileTitle="Смета · версия 3" fileType="XLSX" />,
	},
	{
		title: "Документы",
		text: "КП, счёт и ведомость по шаблонам компании: реквизиты подставляются из проекта, результат — готовым файлом.",
		demo: <DocumentsDemo />,
	},
	{
		title: "Цены и нормативы",
		text: "ФСНБ-2024 и официальные цены ФГИС ЦС: каждая строка сметы связана с источником.",
		demo: <NormativesDemo />,
	},
	{
		title: "Версии",
		text: "Любое изменение создаёт новую версию сметы. Предыдущий расчёт и причина правки не теряются.",
		demo: <VersionsDemo />,
	},
	{
		title: "Экспорт",
		text: "Сметы и документы выгружаются в XLSX, PDF и DOCX — там, где вы работаете с клиентом.",
		demo: <ExportDemo />,
	},
];

export function RolesSection() {
	const track = useRef<HTMLDivElement>(null);
	const [progress, setProgress] = useState(0);
	const dragState = useRef({ active: false, startX: 0, scrollLeft: 0 });

	const updateProgress = () => {
		const node = track.current;
		if (!node) return;
		const max = node.scrollWidth - node.clientWidth;
		setProgress(max > 0 ? Math.min(100, (node.scrollLeft / max) * 100) : 0);
	};

	const scrollBy = (direction: 1 | -1) => {
		track.current?.scrollBy({ left: direction * 320, behavior: "smooth" });
	};

	return (
		<section className="klp-roles" id="roles" aria-labelledby="roles-title">
			<div>
				<div className="klp-roles-head">
					<h2 id="roles-title">Один агент — для смет, документов и всего между ними</h2>
				</div>
				<div className="klp-roles-arrows">
					<button className="klp-arrow" type="button" aria-label="Предыдущие возможности" onClick={() => scrollBy(-1)}>
						<ArrowLeft aria-hidden="true" />
					</button>
					<button className="klp-arrow" type="button" aria-label="Следующие возможности" onClick={() => scrollBy(1)}>
						<ArrowRight aria-hidden="true" />
					</button>
				</div>
				<span className="klp-roles-progress" aria-hidden="true">
					<i style={{ width: `${progress}%` }} />
				</span>
			</div>
			<div
				className="klp-roles-track"
				ref={track}
				onScroll={updateProgress}
				onPointerDown={(event) => {
					dragState.current = {
						active: true,
						startX: event.clientX,
						scrollLeft: track.current?.scrollLeft ?? 0,
					};
				}}
				onPointerMove={(event) => {
					if (!dragState.current.active) return;
					const node = track.current;
					if (!node) return;
					node.scrollLeft = dragState.current.scrollLeft - (event.clientX - dragState.current.startX);
				}}
				onPointerUp={() => {
					dragState.current.active = false;
				}}
				onPointerLeave={() => {
					dragState.current.active = false;
				}}
			>
				{roles.map((role, index) => (
					<Reveal delay={index * 80} key={role.title}>
						<article className="klp-role-card">
							<header className="klp-role-card-head">
								<h3>{role.title}</h3>
								<p>{role.text}</p>
							</header>
							<div className="klp-role-demo">
								<div className="klp-role-demo-panel">
									<div className="klp-role-demo-bar">
										<strong><i /> {role.title}</strong>
										<span>проект · версия 3</span>
									</div>
									{role.demo}
								</div>
							</div>
						</article>
					</Reveal>
				))}
			</div>
		</section>
	);
}
