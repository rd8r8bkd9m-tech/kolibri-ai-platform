import {
	FileStack,
	History,
	ListChecks,
	ShieldCheck,
} from "lucide-react";

const features = [
	{
		icon: ListChecks,
		title: "Смета из исходных данных",
		text: "Опишите объект, объёмы, регион и требования. КолИ собирает структуру расчёта и отмечает, каких данных не хватает.",
		accent: "mint",
	},
	{
		icon: History,
		title: "Управляемый пересчёт",
		text: "Изменение материала или объёма создаёт новую версию сметы. Предыдущий расчёт и причины изменений не теряются.",
		accent: "sky",
	},
	{
		icon: FileStack,
		title: "Документы из проекта",
		text: "Коммерческое предложение, договор и акты используют согласованные данные проекта вместо разрозненных копий.",
		accent: "warm",
	},
	{
		icon: ShieldCheck,
		title: "Проверяемый результат",
		text: "Источники цен, условия расчёта и статусы готовности остаются рядом с результатом, который видит пользователь.",
		accent: "coral",
	},
] as const;

export function FeatureGrid() {
	return (
		<section className="kp-feature-section kp-section" id="features" aria-labelledby="features-title">
			<div className="kp-container">
				<div className="kp-section-heading">
					<p className="kp-eyebrow kp-eyebrow-dark"><span /> Возможности</p>
					<h2 id="features-title">Рабочий контур проекта, а не набор отдельных генераций.</h2>
					<p>Каждый следующий документ продолжает уже согласованную работу.</p>
				</div>
				<div className="kp-feature-grid">
					{features.map(({ accent, icon: Icon, text, title }, index) => (
						<article className={`kp-feature-card is-${accent}`} key={title}>
							<div className="kp-feature-card-top">
								<span>{String(index + 1).padStart(2, "0")}</span>
								<Icon aria-hidden="true" />
							</div>
							<h3>{title}</h3>
							<p>{text}</p>
						</article>
					))}
				</div>
			</div>
		</section>
	);
}
