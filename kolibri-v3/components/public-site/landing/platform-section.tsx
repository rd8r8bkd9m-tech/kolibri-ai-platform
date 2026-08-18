import { ArrowRight, Braces, Database, FileSpreadsheet, FileText, Landmark, MessageSquare, MonitorCheck, Receipt, Scale } from "lucide-react";
import { Reveal } from "./reveal";

type IntegrationRow = {
	icon: typeof Database;
	mark: string;
	name: string;
	meta: string;
	status: "ready" | "accent" | "soon";
	chip: string;
};

const rows: IntegrationRow[] = [
	{ icon: Scale, mark: "Ф", name: "ФСНБ‑2024", meta: "справочник базовых цен", status: "ready", chip: "проверка цен" },
	{ icon: Braces, mark: "Н", name: "Норм. база", meta: "подбор по ГЭСН, ТЕР, ФЕР, СП", status: "accent", chip: "поиск норм" },
	{ icon: Database, mark: "Ц", name: "ФГИС ЦС", meta: "официальные цены материалов", status: "ready", chip: "цены" },
	{ icon: FileSpreadsheet, mark: "X", name: "Excel", meta: "сметы и расчёты", status: "ready", chip: "экспорт XLSX" },
	{ icon: FileText, mark: "W", name: "Word", meta: "КП и ведомость", status: "ready", chip: "экспорт DOCX" },
	{ icon: FileText, mark: "P", name: "PDF", meta: "сметы и пакеты документов", status: "ready", chip: "экспорт PDF" },
	{ icon: Landmark, mark: "Т", name: "Т‑Банк", meta: "оплата тарифа и подписка", status: "ready", chip: "оплата" },
	{ icon: MessageSquare, mark: "T", name: "Telegram", meta: "уведомления и файлы", status: "soon", chip: "скоро" },
	{ icon: MonitorCheck, mark: "AI", name: "AI‑модели", meta: "OpenAI, Claude, DeepSeek, Gemini, Qwen, MiMo", status: "accent", chip: "выбор модели" },
	{ icon: Receipt, mark: "1С", name: "1С и CRM", meta: "данные проектов и контрагентов", status: "soon", chip: "скоро" },
];

export function IntegrationsSection() {
	return (
		<section className="klp-integrations" id="integrations" aria-labelledby="integrations-title">
			<div className="klp-integrations-inner">
				<Reveal>
					<header className="klp-integrations-head">
						<p className="klp-eyebrow"><span /> Интеграции</p>
						<h2 id="integrations-title">Источники данных и сервисы — внутри агента</h2>
						<p>
							КолИ подключает нормативы, файлы, модели и платёжные сервисы:
							<span className="klp-int-flow">
								<b>Источник</b> <ArrowRight aria-hidden="true" /> <b>Kolibri Agent</b> <ArrowRight aria-hidden="true" /> <b>Результат</b>
							</span>
						</p>
					</header>
				</Reveal>
				<div className="klp-int-grid">
					{rows.map(({ chip, icon: Icon, mark, meta, name, status }, index) => (
						<Reveal delay={Math.min(index * 60, 240)} key={name}>
							<div className="klp-int-row">
								<span className="klp-int-icon" aria-hidden="true"><Icon /></span>
								<span className="klp-int-meta">
									<strong>{name}</strong>
									<span>{meta}</span>
								</span>
								<span className={`klp-int-status is-${status}`}>
									<i aria-hidden="true" /> {chip}
								</span>
							</div>
						</Reveal>
					))}
				</div>
			</div>
		</section>
	);
}
