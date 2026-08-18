"use client";

import {
	ClipboardList,
	FileCheck2,
	FileText,
	Send,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { LandingPet } from "./landing-pet";

const chips = ["ФСНБ-2024", "ФГИС ЦС"];

type Scene = {
	id: string;
	label: string;
	user: ReactNode;
	ai: ReactNode;
};

const scenes: Scene[] = [
	{
		id: "estimate",
		label: "Смета",
		user: (
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
		),
		ai: (
			<div className="klp-msg klp-msg-ai">
				<LandingPet interactive width={30} className="klp-chat-pet" />
				<div className="klp-ai-body">
					<div className="klp-exec-chips" aria-label="Ход выполнения">
						<span className="is-done"><i aria-hidden="true" /> План составлен</span>
						<span className="is-done"><i aria-hidden="true" /> Цены проверены по ФГИС ЦС</span>
						<span className="is-done"><i aria-hidden="true" /> Расчёт завершён</span>
					</div>
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
		),
	},
	{
		id: "documents",
		label: "Документы",
		user: (
			<div className="klp-msg klp-msg-user">
				<div className="klp-bubble">
					Сделай КП, счёт и ведомость по версии 3 сметы
				</div>
			</div>
		),
		ai: (
			<div className="klp-msg klp-msg-ai">
				<LandingPet interactive width={30} className="klp-chat-pet" />
				<div className="klp-ai-body">
					<strong>Готово — реквизиты и сроки взяты из проекта.</strong>
					{[
						{ title: "Коммерческое предложение", type: "DOCX", state: "готово" },
						{ title: "Договор подряда", type: "DOCX", state: "черновик" },
						{ title: "Счёт на оплату", type: "PDF", state: "в работе" },
					].map((doc, index) => (
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
		),
	},
	{
		id: "dev",
		label: "Разработка",
		user: (
			<div className="klp-msg klp-msg-user">
				<div className="klp-bubble">
					Подключи ФГИС ЦС и проверь цены по 48 позициям сметы
				</div>
			</div>
		),
		ai: (
			<div className="klp-msg klp-msg-ai">
				<LandingPet interactive width={30} className="klp-chat-pet" />
				<div className="klp-ai-body">
					<strong>Готово — цены проверены, версия 4 собрана.</strong>
					<ul className="klp-timeline" style={{ marginTop: "0.7rem" }}>
						{[
							["Проверил 48 позиций по официальным ценам", "4s"],
							["Сопоставил позиции с ценами ФГИС ЦС", "3s"],
							["Обновил версию сметы и основания", "3s"],
							["Сохранил изменения — правку можно откатить", "2s"],
						].map(([text, time]) => (
							<li key={text}><span>{text}<i>{time}</i></span></li>
						))}
					</ul>
				</div>
			</div>
		),
	},
];

type Phase = "hidden" | "user" | "typing" | "done";

export function HeroStage() {
	const [index, setIndex] = useState(0);
	const [paused, setPaused] = useState(false);
	const [phase, setPhase] = useState<Phase>("hidden");

	useEffect(() => {
		setPhase("hidden");
		const timers = [
			window.setTimeout(() => setPhase("user"), 300),
			window.setTimeout(() => setPhase("typing"), 850),
			window.setTimeout(() => setPhase("done"), 2000),
		];
		return () => timers.forEach(window.clearTimeout);
	}, [index]);

	useEffect(() => {
		if (paused) return;
		const timer = window.setInterval(() => {
			setIndex((current) => (current + 1) % scenes.length);
		}, 8500);
		return () => window.clearInterval(timer);
	}, [paused]);

	const scene = scenes[index];

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
							{scenes.map((item, sceneIndex) => (
								<button
									className={sceneIndex === index ? "is-active" : ""}
									key={item.id}
									type="button"
									role="tab"
									aria-selected={sceneIndex === index}
									onClick={() => setIndex(sceneIndex)}
								>
									{item.label}
								</button>
							))}
						</div>
						<span className="klp-stage-status">
							<LandingPet interactive width={26} className="klp-topbar-pet" />
							<i /> {phase === "typing" || phase === "hidden" ? "агент думает" : "агент в сети"}
						</span>
					</div>
					<div
						className={`klp-scene-progress${paused ? " is-paused" : ""}`}
						key={`progress-${scene.id}`}
						aria-hidden="true"
					>
						<i />
					</div>
					<div className="klp-chat klp-chat-scene" key={scene.id}>
						{phase === "hidden" ? null : scene.user}
						{phase === "typing" ? (
							<div className="klp-msg klp-msg-ai">
								<LandingPet width={30} className="klp-chat-pet" />
								<span className="klp-typing" aria-label="Агент выполняет задачу">
									<i />
									<i />
									<i />
								</span>
								<span className="klp-exec-pill is-working">
									<i aria-hidden="true" /> выполняю: анализирую, считаю, проверяю
								</span>
							</div>
						) : null}
						{phase === "done" ? scene.ai : null}
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
				<p>КП готов<small>счёт и ведомость</small></p>
			</div>
			<div className="klp-float-pill klp-pill-c">
				<span><FileCheck2 aria-hidden="true" /></span>
				<p>Счёт на оплату<small>в работе</small></p>
			</div>
		</div>
	);
}
