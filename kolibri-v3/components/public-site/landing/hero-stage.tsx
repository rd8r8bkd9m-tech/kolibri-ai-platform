"use client";

import {
	ClipboardList,
	FileCheck2,
	FileText,
	Send,
} from "lucide-react";
import { useEffect, useState } from "react";
import { LandingPet } from "./landing-pet";

const chips = ["ФСНБ-2022", "ГЭСН", "ФГИС ЦС"];

function EstimateScene() {
	return (
		<>
			<div className="klp-msg klp-msg-user">
				<div className="klp-bubble">
					Загляни в{" "}
					{chips.map((chip) => (
						<span className="klp-chip" key={chip}>
							<span className="klp-chip-dot" aria-hidden="true" />
							{chip}
						</span>
					))}{" "}
					и собери смету на каркасный дом 38 м² в Москве
				</div>
			</div>
			<div className="klp-msg">
				<div className="klp-ai-body">
					<strong>
						Смета готова — 2 840 000 ₽. Это версия 3, предыдущие расчёты сохранены.
					</strong>
					<ul>
						<li><strong>Работы</strong> — 1 420 000 ₽</li>
						<li><strong>Материалы</strong> — 1 130 000 ₽</li>
						<li><strong>Накладные и резерв</strong> — 290 000 ₽</li>
					</ul>
					<p>Полный расчёт приложил. Разложить по разделам?</p>
					<div className="klp-file-card" style={{ marginTop: "0.8rem" }}>
						<span className="klp-file-icon"><FileText aria-hidden="true" /></span>
						<span className="klp-file-meta">
							<strong>Смета · версия 3</strong>
							<span>Документ · XLSX</span>
						</span>
					</div>
				</div>
			</div>
		</>
	);
}

function DocumentsScene() {
	const docs = [
		{ title: "Коммерческое предложение", type: "DOCX", state: "готово" },
		{ title: "Договор подряда", type: "DOCX", state: "черновик" },
		{ title: "Акт выполненных работ", type: "PDF", state: "в работе" },
	];
	return (
		<>
			<div className="klp-msg klp-msg-user">
				<div className="klp-bubble">
					Сделай КП, договор и акт по версии 3 сметы
				</div>
			</div>
			<div className="klp-msg">
				<div className="klp-ai-body">
					<strong>Готово — реквизиты и сроки взяты из проекта.</strong>
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
		</>
	);
}

function DevScene() {
	const steps = [
		["Проверил 48 позиций по официальным ценам", "4s"],
		["Сопоставил позиции со справочником ГЭСН", "3s"],
		["Обновил версию сметы и основания", "3s"],
		["Сохранил изменения — правку можно откатить", "2s"],
	] as const;
	return (
		<>
			<div className="klp-msg klp-msg-user">
				<div className="klp-bubble">
					Подключи ФГИС ЦС и проверь цены по 48 позициям сметы
				</div>
			</div>
			<div className="klp-msg">
				<div className="klp-ai-body">
					<strong>Готово — цены проверены, версия 4 собрана.</strong>
					<ul className="klp-timeline" style={{ marginTop: "0.7rem" }}>
						{steps.map(([text, time]) => (
							<li key={text}><span>{text}<i>{time}</i></span></li>
						))}
					</ul>
				</div>
			</div>
		</>
	);
}

const scenes = [
	{ id: "estimate", label: "Смета", node: <EstimateScene /> },
	{ id: "documents", label: "Документы", node: <DocumentsScene /> },
	{ id: "dev", label: "Разработка", node: <DevScene /> },
];

export function HeroStage() {
	const [index, setIndex] = useState(0);
	const [paused, setPaused] = useState(false);

	useEffect(() => {
		if (paused) return;
		const timer = window.setInterval(() => {
			setIndex((current) => (current + 1) % scenes.length);
		}, 7000);
		return () => window.clearInterval(timer);
	}, [paused]);

	return (
		<div
			className="klp-hero-stage"
			aria-label="Демонстрация работы агента КолИ"
			onMouseEnter={() => setPaused(true)}
			onMouseLeave={() => setPaused(false)}
		>
			<div className="klp-stage">
				<div className="klp-stage-content">
					<div className="klp-stage-topbar">
						<div className="klp-stage-dots" aria-hidden="true">
							<i />
							<i />
							<i />
						</div>
						<div className="klp-scene-switch" role="tablist" aria-label="Сценарии демонстрации">
							{scenes.map((scene, sceneIndex) => (
								<button
									className={sceneIndex === index ? "is-active" : ""}
									key={scene.id}
									type="button"
									role="tab"
									aria-selected={sceneIndex === index}
									onClick={() => setIndex(sceneIndex)}
								>
									{scene.label}
								</button>
							))}
						</div>
						<span className="klp-stage-status">
							<LandingPet interactive width={26} className="klp-topbar-pet" />
							<i /> агент в сети
						</span>
					</div>
					<div
						className={`klp-scene-progress${paused ? " is-paused" : ""}`}
						key={`progress-${scenes[index].id}`}
						aria-hidden="true"
					>
						<i />
					</div>
					<div className="klp-chat klp-chat-scene" key={scenes[index].id}>
						{scenes[index].node}
					</div>
					<div className="klp-composer">
						<input aria-label="Вопрос агенту" placeholder="Спросите про смету, документы или нормативы…" />
						<button className="klp-send" type="button" aria-label="Отправить">
							<Send aria-hidden="true" />
						</button>
					</div>
				</div>
			</div>
			<div className="klp-float-pill klp-pill-a">
				<span><ClipboardList aria-hidden="true" /></span>
				<p>Смета создана<small>каждое изменение — версия</small></p>
			</div>
			<div className="klp-float-pill klp-pill-b">
				<span><FileText aria-hidden="true" /></span>
				<p>КП готов<small>черновик договора</small></p>
			</div>
			<div className="klp-float-pill klp-pill-c">
				<span><FileCheck2 aria-hidden="true" /></span>
				<p>Акт выполненных работ<small>в работе</small></p>
			</div>
		</div>
	);
}
