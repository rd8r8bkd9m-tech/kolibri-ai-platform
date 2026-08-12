import { Calculator, FileStack, History } from "lucide-react";

const cases = [
	{
		icon: Calculator,
		title: "Смета за минуты",
		text: "Опишите объект, объёмы и регион — работы, материалы и цены собираются в версионный расчёт без ручного пересчёта.",
	},
	{
		icon: FileStack,
		title: "Документы из проекта",
		text: "КП, договор и акты используют согласованные данные проекта вместо разрозненных копий и повторного ввода.",
	},
	{
		icon: History,
		title: "Версии и основания",
		text: "Каждая правка — новая версия сметы с причиной изменения и источником цены, которую можно проверить.",
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
					{cases.map(({ icon: Icon, text, title }) => (
						<article className="klp-case-card" key={title}>
							<Icon aria-hidden="true" />
							<h3>{title}</h3>
							<p>{text}</p>
						</article>
					))}
				</div>
			</div>
		</section>
	);
}
