import { Reveal } from "./reveal";

const steps = [
	{
		title: "План",
		text: "Разбивает задачу на шаги и показывает условия расчёта",
		status: "done" as const,
		chip: "готово",
	},
	{
		title: "Инструменты",
		text: "Подключает ФСНБ‑2024 и цены ФГИС ЦС",
		status: "done" as const,
		chip: "готово",
	},
	{
		title: "Действия",
		text: "Собирает работы, материалы и количества в смету",
		status: "running" as const,
		chip: "выполняется",
	},
	{
		title: "Проверка",
		text: "Сверяет цены с официальными источниками и основаниями",
		status: "queued" as const,
		chip: "в очереди",
	},
	{
		title: "Результат",
		text: "Выпускает смету, КП, счёт и ведомость с версиями",
		status: "queued" as const,
		chip: "в очереди",
	},
];

const logLines = [
	{ time: "09:41", text: "проверяю 214 позиций по ФГИС ЦС", running: false },
	{ time: "09:42", text: "сопоставляю позиции с ценами ФСНБ‑2024", running: false },
	{ time: "09:43", text: "собираю версию 3 · работы и материалы", running: true },
	{ time: "09:44", text: "экспорт XLSX · документы из проекта", running: false },
];

export function AgentTraceSection() {
	return (
		<section className="klp-agent" id="agent" aria-labelledby="agent-title">
			<div className="klp-agent-inner">
				<Reveal>
					<header className="klp-agent-head">
						<p className="klp-eyebrow"><span /> Kolibri Agent</p>
						<h2 id="agent-title">Как агент работает над сметой</h2>
						<p>
							Не «чёрный ящик», а исполнитель с контролем: каждый шаг виден,
							каждую правку можно проверить и откатить.
						</p>
					</header>
				</Reveal>
				<div className="klp-agent-grid">
					<ol className="klp-trace">
						{steps.map((step, index) => (
							<li
								className={`klp-trace-step is-${step.status}`}
								key={step.title}
							>
								<span className="klp-trace-dot" aria-hidden="true">
									{String(index + 1).padStart(2, "0")}
								</span>
								<div>
									<h3>{step.title}</h3>
									<p>{step.text}</p>
								</div>
								<span className={`klp-trace-chip is-${step.status}`}>
									<i aria-hidden="true" /> {step.chip}
								</span>
							</li>
						))}
					</ol>
					<div className="klp-agent-log" aria-label="Живой лог выполнения">
						<p className="klp-agent-log-title">Живой лог выполнения</p>
						<ul>
							{logLines.map((line) => (
								<li className={line.running ? "is-running" : ""} key={line.text}>
									<i>{line.time}</i>
									<span>{line.text}</span>
								</li>
							))}
						</ul>
					</div>
				</div>
			</div>
		</section>
	);
}
