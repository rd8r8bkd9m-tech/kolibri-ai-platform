"use client";

import {
	FileClock,
	FileCheck2,
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
	const feed = [
		{
			icon: ReceiptText,
			title: "Утренняя сводка — смета версии 4",
			text: "Изменения по 18 позициям за вчера, причины сохранены.",
			time: "09:00",
		},
		{
			icon: FileCheck2,
			title: "КП и договор готовы",
			text: "Реквизиты и сроки из проекта, два черновика на согласование.",
			time: "10:15",
		},
		{
			icon: FileClock,
			title: "Просрочка по документам",
			text: "Акт за прошлый месяц не подписан — напоминание готово к отправке.",
			time: "11:30",
		},
	];
	return (
		<div className="klp-chat">
			<div className="klp-msg klp-msg-user">
				<div className="klp-bubble">
					Настрой регулярные сводки и документы по проекту
				</div>
			</div>
			<div className="klp-msg">
				<div className="klp-ai-body">
					<strong>Задачи созданы — первая сводка придёт завтра в 9:00.</strong>
					<div className="klp-feed" style={{ marginTop: "0.8rem" }}>
						{feed.map(({ icon: Icon, text, time, title }) => (
							<div className="klp-feed-item" key={title}>
								<span className="klp-feed-icon"><Icon aria-hidden="true" /></span>
								<span className="klp-feed-meta">
									<strong>{title}</strong>
									<span>{text}</span>
								</span>
								<span className="klp-feed-time">{time}</span>
							</div>
						))}
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
			<div className="klp-role-demo-body" style={{ padding: "1rem" }}>
				<div className="klp-chat">
					<div className="klp-msg klp-msg-user">
						<div className="klp-bubble">
							Подключи ФГИС ЦС и проверь цены по 48 позициям
						</div>
					</div>
					<div className="klp-msg">
						<div className="klp-ai-body">
							<strong>Готово — цены проверены, версия 4 собрана.</strong>
							<div className="klp-diff" style={{ marginTop: "0.8rem" }}>
								<div className="klp-diff-bar">
									<strong>main ← prices-check</strong>
									<i>+48</i>
									<span>M estimate_rows.py</span>
								</div>
								<code>
									<span className="is-num">@@ 1,7 +1,7 @@</span>
									<span className="is-ctx"> app = estimate()</span>
									<span className="is-ctx"> rows = load("version_3.xlsx")</span>
									<span className="is-add">+prices = fgis.check(rows, region="МО")</span>
									<span className="is-add">+estimate.update(rows, prices)</span>
									<span className="is-ctx"> save("version_4.xlsx")</span>
								</code>
							</div>
						</div>
					</div>
				</div>
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
