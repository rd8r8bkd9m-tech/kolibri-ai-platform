"use client";

import {
	FileCheck2,
	FileText,
	ReceiptText,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";

type PillarId = "work" | "routine" | "dev";

const pillars = [
	{
		id: "work" as const,
		title: "Работа",
		subtitle: "Для смет от начала до конца.",
		description:
			"Опишите объект — агент соберёт работы, материалы, количества и цены в версионный расчёт.",
	},
	{
		id: "routine" as const,
		title: "Рутина",
		subtitle: "Для документов, которые не хочется готовить руками.",
		description:
			"КП, договоры и акты формируются из согласованных данных проекта и приходят готовыми файлами.",
	},
	{
		id: "dev" as const,
		title: "Разработка",
		subtitle: "Для нормативов и интеграций, которых не хватает.",
		description:
			"Подключение справочников и проверка цен по официальным источникам — словами, без программиста.",
	},
] as const;

function WorkDemo() {
	return (
		<>
			<div className="klp-chat">
				<div className="klp-msg klp-msg-user">
					<div className="klp-bubble">
						Собери смету на фундамент, стены и кровлю для дома 38 м²
					</div>
				</div>
				<div className="klp-msg">
					<div className="klp-ai-body">
						<strong>Смета собрана: 68 позиций, 4 раздела, версия 1.</strong>
						<ul>
							<li><strong>Фундамент</strong> — 640 000 ₽</li>
							<li><strong>Стены</strong> — 1 180 000 ₽</li>
							<li><strong>Кровля</strong> — 540 000 ₽</li>
						</ul>
						<div className="klp-file-card" style={{ marginTop: "0.8rem" }}>
							<span className="klp-file-icon"><ReceiptText aria-hidden="true" /></span>
							<span className="klp-file-meta">
								<strong>Смета · версия 1</strong>
								<span>Документ · XLSX</span>
							</span>
						</div>
					</div>
				</div>
			</div>
		</>
	);
}

function RoutineDemo() {
	return (
		<div className="klp-chat">
			<div className="klp-msg klp-msg-user">
				<div className="klp-bubble">
					Сделай КП, договор и акт по версии 3 сметы
				</div>
			</div>
			<div className="klp-msg">
				<div className="klp-ai-body">
					<strong>Готово — реквизиты и сроки взяты из проекта.</strong>
					<div className="klp-file-card" style={{ marginTop: "0.8rem" }}>
						<span className="klp-file-icon"><FileText aria-hidden="true" /></span>
						<span className="klp-file-meta">
							<strong>Коммерческое предложение</strong>
							<span>Файл · DOCX · готово</span>
						</span>
					</div>
					<div className="klp-file-card" style={{ marginTop: "0.5rem" }}>
						<span className="klp-file-icon"><FileText aria-hidden="true" /></span>
						<span className="klp-file-meta">
							<strong>Договор подряда</strong>
							<span>Файл · DOCX · черновик</span>
						</span>
					</div>
					<div className="klp-file-card" style={{ marginTop: "0.5rem" }}>
						<span className="klp-file-icon"><FileCheck2 aria-hidden="true" /></span>
						<span className="klp-file-meta">
							<strong>Акт выполненных работ</strong>
							<span>Файл · PDF · в работе</span>
						</span>
					</div>
				</div>
			</div>
		</div>
	);
}

function DevDemo() {
	return (
		<>
			<div className="klp-role-demo-bar">
				<strong><i /> Интеграция · ФГИС ЦС</strong>
				<span>нормативы и цены</span>
			</div>
			<div className="klp-role-demo-body">
				<ul className="klp-timeline">
					<li><span>Проверил 48 позиций по официальным ценам<i>4s</i></span></li>
					<li><span>Сопоставил позиции со справочником ГЭСН<i>3s</i></span></li>
					<li><span>Обновил версию сметы и основания<i>3s</i></span></li>
					<li><span>Сохранил изменения — любую правку можно откатить<i>2s</i></span></li>
				</ul>
			</div>
		</>
	);
}

const demos: Record<PillarId, () => ReactElement> = {
	work: WorkDemo,
	routine: RoutineDemo,
	dev: DevDemo,
};

export function PillarsSection() {
	const [active, setActive] = useState<PillarId>("work");
	const sectionRef = useRef<HTMLElement>(null);
	const navRef = useRef<HTMLDivElement>(null);
	const Demo = demos[active];

	useEffect(() => {
		const section = sectionRef.current;
		if (!section) return;

		const update = () => {
			if (window.innerWidth <= 900) return;
			const rect = section.getBoundingClientRect();
			const total = section.offsetHeight - window.innerHeight;
			const progress = total > 0 ? Math.min(1, Math.max(0, -rect.top / total)) : 0;
			const step = 1 / 3;
			const index = progress < step ? 0 : progress < step * 2 ? 1 : 2;
			setActive(pillars[index].id);

			const buttons = navRef.current?.querySelectorAll<HTMLButtonElement>(".klp-pillar-btn");
			buttons?.forEach((button, i) => {
				const fill = Math.min(1, Math.max(0, (progress - i * step) / step));
				button.style.setProperty("--progress", String(fill));
			});
		};

		update();
		window.addEventListener("scroll", update, { passive: true });
		window.addEventListener("resize", update);
		return () => {
			window.removeEventListener("scroll", update);
			window.removeEventListener("resize", update);
		};
	}, []);

	const scrollToPillar = (index: number) => {
		const section = sectionRef.current;
		if (!section) return;
		if (window.innerWidth <= 900) {
			setActive(pillars[index].id);
			return;
		}
		const total = section.offsetHeight - window.innerHeight;
		const target = Math.max(0, window.scrollY + section.getBoundingClientRect().top + ((index + 0.5) / 3) * total);
		window.scrollTo({ top: target, behavior: "smooth" });
	};

	return (
		<section className="klp-pillars" id="work" ref={sectionRef} aria-labelledby="pillars-title">
			<div className="klp-pillars-grid">
				<div className="klp-pillar-nav" ref={navRef}>
					<h2 className="sr-only" id="pillars-title">Три режима работы агента</h2>
					{pillars.map((pillar, index) => (
						<button
							className={`klp-pillar-btn${active === pillar.id ? " is-active" : ""}`}
							key={pillar.id}
							type="button"
							onClick={() => scrollToPillar(index)}
						>
							<span className="klp-pillar-title">{pillar.title}</span>
							<span className="klp-pillar-desc">
								<strong>{pillar.subtitle}</strong>
								{" "}{pillar.description}
							</span>
						</button>
					))}
				</div>
				<div className="klp-pillar-stage klp-stage">
					<div className="klp-stage-content">
						<div className="klp-stage-topbar">
							<div className="klp-stage-dots" aria-hidden="true">
								<i />
								<i />
								<i />
							</div>
							<span className="klp-stage-status">
								<i /> {active === "dev" ? "выполнение" : "агент в сети"}
							</span>
						</div>
						<Demo />
					</div>
				</div>
			</div>
		</section>
	);
}
