import { Bot, FileCheck2, MessagesSquare, ReceiptText } from "lucide-react";

const steps = [
	{
		icon: MessagesSquare,
		title: "Опишите объект",
		text: "Передайте задачу, регион, объёмы и требования обычным текстом или приложите исходные данные.",
	},
	{
		icon: Bot,
		title: "Уточните недостающее",
		text: "Агент структурирует вводные, показывает условия расчёта и задаёт вопросы до расчёта.",
	},
	{
		icon: ReceiptText,
		title: "Получите версию сметы",
		text: "Работы, материалы, количества, цены и основания собираются в редактируемый документ.",
	},
	{
		icon: FileCheck2,
		title: "Выпускайте документы",
		text: "Из согласованных данных проекта формируются КП, договоры и закрывающие документы.",
	},
] as const;

export function WorkflowSection() {
	return (
		<section className="kp-workflow kp-section" id="workflow" aria-labelledby="workflow-title">
			<div className="kp-container">
				<div className="kp-section-heading kp-section-heading-light">
					<p className="kp-eyebrow"><span /> Как работает</p>
					<h2 id="workflow-title">Один проект проходит путь от запроса до документов.</h2>
				</div>
				<ol className="kp-workflow-grid">
					{steps.map(({ icon: Icon, text, title }, index) => (
						<li key={title}>
							<div className="kp-step-top">
								<span>{index + 1}</span>
								<Icon aria-hidden="true" />
							</div>
							<h3>{title}</h3>
							<p>{text}</p>
						</li>
					))}
				</ol>
			</div>
		</section>
	);
}
