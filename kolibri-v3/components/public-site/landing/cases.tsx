import Link from "next/link";
import { ArrowUpRight, Calculator, FileStack, History } from "lucide-react";
import { Reveal } from "./reveal";

const cases = [
	{
		accent: "is-mint",
		icon: Calculator,
		title: "Смета за минуты",
		text: "Опишите объект, объёмы и регион — работы, материалы и цены собираются в версионный расчёт без ручного пересчёта.",
		chip: "Разбор",
		time: "5 мин",
		href: "/#work",
	},
	{
		accent: "is-sky",
		icon: FileStack,
		title: "Документы из проекта",
		text: "КП, счёт и ведомость используют согласованные данные проекта вместо разрозненных копий и повторного ввода.",
		chip: "Гайд",
		time: "12 мин",
		href: "/#roles",
	},
	{
		accent: "is-peach",
		icon: History,
		title: "Версии и основания",
		text: "Каждая правка — новая версия сметы с причиной изменения и источником цены, которую можно проверить.",
		chip: "Кейс",
		time: "8 мин",
		href: "/#roles",
	},
];

export function CasesSection() {
	return (
		<section className="klp-cases" aria-labelledby="cases-title">
			<div className="klp-cases-inner">
				<header className="klp-cases-head">
					<h2 id="cases-title">Кейсы и гайды</h2>
					<p>Как строительные компании передают сметы и документы агенту: разборы и готовые сценарии.</p>
				</header>
				<div className="klp-cases-grid">
					{cases.map(({ accent, chip, href, icon: Icon, text, time, title }, index) => (
						<Reveal delay={index * 90} key={title}>
							<Link className={`klp-case-card ${accent}`} href={href}>
								<span className="klp-case-icon" aria-hidden="true">
									<Icon />
								</span>
								<h3>{title}</h3>
								<p>{text}</p>
								<div className="klp-case-meta">
									<span className="klp-case-chip">{chip} · {time}</span>
									<span className="klp-case-link">Читать <ArrowUpRight aria-hidden="true" /></span>
								</div>
							</Link>
						</Reveal>
					))}
				</div>
			</div>
		</section>
	);
}
